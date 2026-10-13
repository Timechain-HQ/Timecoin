"""Post-quantum signatures and key encapsulation through OpenSSL.

ML-DSA-44 is FIPS 204. ML-KEM-768 is FIPS 203. OpenSSL 3.5 implements both.
This module does not reimplement the lattice math.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ML_DSA = "ML-DSA-44"
ML_KEM = "ML-KEM-768"


class PqError(RuntimeError):
    """OpenSSL rejected a key, signature, or encapsulation."""


def _openssl(args: list[str]) -> None:
    proc = subprocess.run(["openssl", *args], capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise PqError(detail or f"openssl {' '.join(args)} failed")


def generate(algorithm: str) -> tuple[bytes, bytes]:
    """Return ``(private_der, public_der)`` for an OpenSSL PQ algorithm."""
    with tempfile.TemporaryDirectory() as tmp:
        private_path = Path(tmp) / "private.der"
        public_path = Path(tmp) / "public.der"
        _openssl(
            [
                "genpkey",
                "-algorithm",
                algorithm,
                "-outform",
                "DER",
                "-out",
                str(private_path),
            ]
        )
        _openssl(
            [
                "pkey",
                "-inform",
                "DER",
                "-in",
                str(private_path),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(public_path),
            ]
        )
        return private_path.read_bytes(), public_path.read_bytes()


def sign(private_der: bytes, message: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        private_path = Path(tmp) / "private.der"
        message_path = Path(tmp) / "message"
        signature_path = Path(tmp) / "signature"
        private_path.write_bytes(private_der)
        message_path.write_bytes(message)
        _openssl(
            [
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_path),
                "-keyform",
                "DER",
                "-rawin",
                "-in",
                str(message_path),
                "-out",
                str(signature_path),
            ]
        )
        return signature_path.read_bytes()


def verify(public_der: bytes, message: bytes, signature: bytes) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        public_path = Path(tmp) / "public.der"
        message_path = Path(tmp) / "message"
        signature_path = Path(tmp) / "signature"
        public_path.write_bytes(public_der)
        message_path.write_bytes(message)
        signature_path.write_bytes(signature)
        proc = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_path),
                "-keyform",
                "DER",
                "-rawin",
                "-in",
                str(message_path),
                "-sigfile",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
        )
        return proc.returncode == 0


def encapsulate(public_der: bytes) -> tuple[bytes, bytes]:
    """Return ``(ciphertext, shared_secret)`` for an ML-KEM public key."""
    with tempfile.TemporaryDirectory() as tmp:
        public_path = Path(tmp) / "public.der"
        cipher_path = Path(tmp) / "cipher"
        secret_path = Path(tmp) / "secret"
        public_path.write_bytes(public_der)
        _openssl(
            [
                "pkeyutl",
                "-encap",
                "-pubin",
                "-inkey",
                str(public_path),
                "-keyform",
                "DER",
                "-out",
                str(cipher_path),
                "-secret",
                str(secret_path),
            ]
        )
        return cipher_path.read_bytes(), secret_path.read_bytes()


def decapsulate(private_der: bytes, ciphertext: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        private_path = Path(tmp) / "private.der"
        cipher_path = Path(tmp) / "cipher"
        secret_path = Path(tmp) / "secret"
        private_path.write_bytes(private_der)
        cipher_path.write_bytes(ciphertext)
        _openssl(
            [
                "pkeyutl",
                "-decap",
                "-inkey",
                str(private_path),
                "-keyform",
                "DER",
                "-in",
                str(cipher_path),
                "-out",
                str(secret_path),
            ]
        )
        return secret_path.read_bytes()
