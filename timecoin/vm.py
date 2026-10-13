"""A small gas-metered stack machine for Timecoin contracts.

The machine is sequential and deterministic, in the same role as the EVM:
every node runs the bytecode and must reach the same storage. It has no
external calls, so a contract cannot re-enter another contract.
"""

from __future__ import annotations

Instruction = tuple[str, int]

# Vault: arg0 = 1 deposits callvalue (which must equal arg1) into slot 0.
# arg0 = 2 withdraws arg1 to the transaction payout. Any other arg0 reverts.
# JUMPI 27 lands on the deposit path; the withdraw path stops at index 26.
VAULT: list[Instruction] = [
    ("ARG", 0),
    ("PUSH", 1),
    ("EQ",),
    ("JUMPI", 27),
    ("ARG", 0),
    ("PUSH", 2),
    ("EQ",),
    ("ASSERT",),
    ("CALLVALUE",),
    ("PUSH", 0),
    ("EQ",),
    ("ASSERT",),
    ("PUSH", 0),
    ("SLOAD",),
    ("ARG", 1),
    ("GE",),
    ("ASSERT",),
    ("PUSH", 0),
    ("SLOAD",),
    ("ARG", 1),
    ("SUB",),
    ("PUSH", 0),
    ("SWAP",),
    ("SSTORE",),
    ("ARG", 1),
    ("PAYOUT",),
    ("STOP",),
    ("CALLVALUE",),
    ("ARG", 1),
    ("EQ",),
    ("ASSERT",),
    ("PUSH", 0),
    ("SLOAD",),
    ("ARG", 1),
    ("ADD",),
    ("PUSH", 0),
    ("SWAP",),
    ("SSTORE",),
    ("PUSH", 0),
    ("PAYOUT",),
    ("STOP",),
]


class VmError(Exception):
    """A contract stopped because it reverted, overflowed, or ran out of gas."""


def run(
    code: list[Instruction],
    storage: dict[int, int],
    args: list[int],
    callvalue: int,
    gas_limit: int = 10_000,
) -> tuple[dict[int, int], int, int]:
    """Execute ``code`` and return ``(storage, payout, gas_used)``."""
    memory = dict(storage)
    stack: list[int] = []
    gas = gas_limit
    payout = 0
    pc = 0

    def burn(cost: int = 1) -> None:
        nonlocal gas
        gas -= cost
        if gas < 0:
            raise VmError("out of gas")

    while pc < len(code):
        op, arg = _decode(code[pc])
        if op == "PUSH":
            burn()
            stack.append(_require_int(arg))
        elif op == "ADD":
            burn()
            right, left = _pop2(stack)
            stack.append(left + right)
        elif op == "SUB":
            burn()
            right, left = _pop2(stack)
            if left < right:
                raise VmError("underflow")
            stack.append(left - right)
        elif op == "EQ":
            burn()
            right, left = _pop2(stack)
            stack.append(1 if left == right else 0)
        elif op == "GE":
            burn()
            right, left = _pop2(stack)
            stack.append(1 if left >= right else 0)
        elif op == "ASSERT":
            burn()
            if _pop(stack) == 0:
                raise VmError("assert")
        elif op == "ARG":
            burn()
            index = _require_int(arg)
            if index < 0 or index >= len(args):
                raise VmError("argument")
            stack.append(args[index])
        elif op == "CALLVALUE":
            burn()
            stack.append(callvalue)
        elif op == "SLOAD":
            burn()
            stack.append(memory.get(_pop(stack), 0))
        elif op == "SSTORE":
            burn(5)
            value = _pop(stack)
            key = _pop(stack)
            if value < 0:
                raise VmError("negative storage")
            memory[key] = value
        elif op == "PAYOUT":
            burn()
            payout = _pop(stack)
            if payout < 0:
                raise VmError("negative payout")
        elif op == "SWAP":
            burn()
            right, left = _pop2(stack)
            stack.append(right)
            stack.append(left)
        elif op == "JUMPI":
            burn()
            condition = _pop(stack)
            if condition:
                pc = _jump(code, arg)
                continue
        elif op == "JUMP":
            burn()
            pc = _jump(code, arg)
            continue
        elif op == "STOP":
            break
        else:
            raise VmError(f"unknown opcode {op}")
        pc += 1
    return memory, payout, gas_limit - gas


def _decode(instruction: Instruction) -> tuple[str, int | None]:
    if len(instruction) == 1:
        return instruction[0], None
    return instruction[0], instruction[1]


def _require_int(value: int | None) -> int:
    if value is None:
        raise VmError("missing operand")
    return value


def _pop(stack: list[int]) -> int:
    if not stack:
        raise VmError("stack underflow")
    return stack.pop()


def _pop2(stack: list[int]) -> tuple[int, int]:
    right = _pop(stack)
    left = _pop(stack)
    return right, left


def _jump(code: list[Instruction], target: int | None) -> int:
    if target is None or target < 0 or target >= len(code):
        raise VmError("bad jump")
    return target
