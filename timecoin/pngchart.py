"""PNG charts drawn with the standard library.

GitHub renders PNG files in a repository README. These charts are bitmaps so
the pictures stay exact: every bar is a number the caller measured.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (247, 245, 240)
INK = (28, 25, 21)
MUTED = (92, 86, 76)
GRID = (214, 208, 196)
PAPER = (255, 253, 248)
GREEN = (15, 110, 86)
BLUE = (29, 78, 137)
RUST = (154, 52, 18)
GOLD = (133, 77, 14)
PURPLE = (88, 28, 135)
SLATE = (52, 78, 110)
SERIES = (GREEN, BLUE, RUST, GOLD, PURPLE, SLATE)

# 5x7 glyphs, top row first. Missing characters are skipped.
_GLYPHS = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00110", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"],
    "%": ["11001", "11010", "00100", "00100", "01011", "10011", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


def _glyph(char: str) -> list[str]:
    if char in _GLYPHS:
        return _GLYPHS[char]
    upper = char.upper()
    if upper in _GLYPHS:
        return _GLYPHS[upper]
    return ["11111", "10001", "10001", "10001", "10001", "10001", "11111"]


class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, int, int] = BG) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(color * width * height)

    def _set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            index = (y * self.width + x) * 3
            self.pixels[index : index + 3] = bytes(color)

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        for row in range(int(y), int(y + height)):
            for column in range(int(x), int(x + width)):
                self._set(column, row, color)

    def frame(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int], thick: int = 1) -> None:
        for offset in range(thick):
            self.line(x + offset, y + offset, x + width - 1 - offset, y + offset, color)
            self.line(x + offset, y + height - 1 - offset, x + width - 1 - offset, y + height - 1 - offset, color)
            self.line(x + offset, y + offset, x + offset, y + height - 1 - offset, color)
            self.line(x + width - 1 - offset, y + offset, x + width - 1 - offset, y + height - 1 - offset, color)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: tuple[int, int, int]) -> None:
        x0i, y0i, x1i, y1i = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx = abs(x1i - x0i)
        dy = -abs(y1i - y0i)
        sx = 1 if x0i < x1i else -1
        sy = 1 if y0i < y1i else -1
        err = dx + dy
        while True:
            self._set(x0i, y0i, color)
            if x0i == x1i and y0i == y1i:
                break
            twice = 2 * err
            if twice >= dy:
                err += dy
                x0i += sx
            if twice <= dx:
                err += dx
                y0i += sy

    def text(self, x: int, y: int, message: str, color: tuple[int, int, int] = INK, scale: int = 2) -> None:
        cursor = x
        for char in message:
            rows = _glyph(char)
            for row, bits in enumerate(rows):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        self.rect(cursor + column * scale, y + row * scale, scale, scale, color)
            cursor += 6 * scale

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        stride = self.width * 3
        for y in range(self.height):
            start = y * stride
            rows.append(b"\x00" + bytes(self.pixels[start : start + stride]))
        compressed = zlib.compress(b"".join(rows), 9)
        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")
        )


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    if abs(value) >= 100:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    step = 1.0
    while step < value:
        step *= 10.0
    step /= 10.0
    for multiplier in (1, 2, 2.5, 5, 10):
        if multiplier * step + 1e-9 >= value:
            return multiplier * step
    return step * 10.0


def _blank(title: str, width: int = 960, height: int = 540) -> tuple[Canvas, int, int, int, int]:
    canvas = Canvas(width, height)
    canvas.text(24, 18, title.upper(), INK, 2)
    left, top, right, bottom = 78, 64, width - 28, height - 72
    canvas.rect(left, top, right - left, bottom - top, PAPER)
    canvas.frame(left, top, right - left, bottom - top, GRID)
    return canvas, left, top, right, bottom


def _legend(canvas: Canvas, names: list[str], colors: list[tuple[int, int, int]]) -> None:
    x = 24
    y = canvas.height - 36
    for name, color in zip(names, colors):
        canvas.rect(x, y + 2, 14, 14, color)
        canvas.text(x + 20, y, name.upper(), INK, 2)
        x += 20 + len(name) * 12 + 28


def line_chart(
    path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    series: list[tuple[str, list[tuple[float, float]]]],
) -> None:
    canvas, left, top, right, bottom = _blank(title)
    canvas.text(24, 44, ylabel.upper(), MUTED, 1)
    points = [point for _name, data in series for point in data]
    if not points:
        canvas.save(path)
        return
    xmin = min(point[0] for point in points)
    xmax = max(point[0] for point in points)
    ymax = _nice_max(max(point[1] for point in points))
    if xmax == xmin:
        xmax = xmin + 1

    def xpos(value: float) -> float:
        return left + (value - xmin) / (xmax - xmin) * (right - left)

    def ypos(value: float) -> float:
        return bottom - (value / ymax) * (bottom - top)

    for tick in range(5):
        value = ymax * tick / 4
        y = ypos(value)
        canvas.line(left, y, right, y, GRID)
        canvas.text(8, int(y) - 4, _fmt(value), MUTED, 1)
    canvas.text((left + right) // 2 - len(xlabel) * 6, canvas.height - 58, xlabel.upper(), MUTED, 2)
    colors = [SERIES[index % len(SERIES)] for index in range(len(series))]
    for (name, data), color in zip(series, colors):
        ordered = sorted(data)
        for start, end in zip(ordered, ordered[1:]):
            canvas.line(xpos(start[0]), ypos(start[1]), xpos(end[0]), ypos(end[1]), color)
        for x_value, y_value in ordered:
            cx, cy = int(xpos(x_value)), int(ypos(y_value))
            canvas.rect(cx - 3, cy - 3, 7, 7, color)
        del name
    _legend(canvas, [name for name, _data in series], colors)
    canvas.save(path)


def bar_chart(
    path: Path,
    title: str,
    xlabel: str,
    categories: list[str],
    series: list[tuple[str, list[float]]],
) -> None:
    canvas, left, top, right, bottom = _blank(title)
    canvas.text(24, 44, xlabel.upper(), MUTED, 1)
    peak = 0.0
    for _name, values in series:
        peak = max(peak, max(values) if values else 0)
    ymax = _nice_max(peak)
    plot_width = right - left
    group = plot_width / max(len(categories), 1)
    bar_width = max(group * 0.7 / max(len(series), 1), 4)
    colors = [SERIES[index % len(SERIES)] for index in range(len(series))]
    for tick in range(5):
        value = ymax * tick / 4
        y = bottom - (value / ymax) * (bottom - top)
        canvas.line(left, y, right, y, GRID)
        canvas.text(8, int(y) - 4, _fmt(value), MUTED, 1)
    for index, category in enumerate(categories):
        center = left + group * index + group / 2
        label = category.upper()
        canvas.text(int(center - len(label) * 3), bottom + 8, label, MUTED, 1)
        for series_index, (_name, values) in enumerate(series):
            value = values[index] if index < len(values) else 0
            height = 0 if ymax == 0 else (value / ymax) * (bottom - top)
            x = center - (len(series) * bar_width) / 2 + series_index * bar_width
            canvas.rect(int(x), int(bottom - height), max(int(bar_width) - 2, 1), int(height), colors[series_index])
    _legend(canvas, [name for name, _values in series], colors)
    canvas.save(path)


def stacked_bar(
    path: Path,
    title: str,
    categories: list[str],
    series: list[tuple[str, list[float]]],
) -> None:
    canvas, left, top, right, bottom = _blank(title)
    totals = []
    for index in range(len(categories)):
        totals.append(sum(values[index] if index < len(values) else 0 for _name, values in series))
    ymax = _nice_max(max(totals) if totals else 0)
    group = (right - left) / max(len(categories), 1)
    bar_width = max(group * 0.45, 8)
    colors = [SERIES[index % len(SERIES)] for index in range(len(series))]
    for tick in range(5):
        value = ymax * tick / 4
        y = bottom - (value / ymax) * (bottom - top) if ymax else bottom
        canvas.line(left, y, right, y, GRID)
        canvas.text(8, int(y) - 4, _fmt(value), MUTED, 1)
    for index, category in enumerate(categories):
        center = left + group * index + group / 2
        canvas.text(int(center - len(category) * 3), bottom + 8, category.upper(), MUTED, 1)
        y = float(bottom)
        for series_index, (_name, values) in enumerate(series):
            value = values[index] if index < len(values) else 0
            height = 0 if ymax == 0 else (value / ymax) * (bottom - top)
            y -= height
            canvas.rect(int(center - bar_width / 2), int(y), int(bar_width), max(int(height), 0), colors[series_index])
    _legend(canvas, [name for name, _values in series], colors)
    canvas.save(path)


def composition_chart(path: Path, title: str, parts: list[tuple[str, int]]) -> None:
    """One horizontal bar split by measured byte lengths."""
    canvas = Canvas(960, 180 + 24 * max(len(parts), 1))
    canvas.text(24, 18, title.upper(), INK, 2)
    total = sum(size for _name, size in parts) or 1
    canvas.text(24, 48, f"TOTAL {total} BYTES", MUTED, 2)
    x = 24
    y = 92
    width = 912
    colors = [SERIES[index % len(SERIES)] for index in range(len(parts))]
    for (_name, size), color in zip(parts, colors):
        span = max(int(round(width * size / total)), 1)
        canvas.rect(x, y, span, 42, color)
        x += span
    canvas.frame(24, y, width, 42, INK)
    label_y = 156
    for (name, size), color in zip(parts, colors):
        canvas.rect(24, label_y + 2, 14, 14, color)
        canvas.text(44, label_y, f"{name.upper()} {size}", INK, 2)
        label_y += 24
    canvas.save(path)


def fork_chart(path: Path, title: str, boxes: list[dict[str, object]]) -> None:
    """Draw a measured fork. Each box has label, column, row, and kind."""
    canvas = Canvas(960, 540)
    canvas.text(24, 18, title.upper(), INK, 2)
    canvas.text(24, 46, "CANONICAL HEIGHT WINS. EQUAL HEIGHT: SMALLER BLOCK ID.", MUTED, 1)
    fills = {
        "canonical": (214, 232, 224),
        "uncle": (244, 224, 214),
        "side": (220, 228, 240),
        "genesis": (232, 228, 216),
    }
    borders = {"canonical": GREEN, "uncle": RUST, "side": BLUE, "genesis": INK}
    placed: dict[tuple[int, int], tuple[int, int]] = {}
    for box in boxes:
        column = int(box["column"])
        row = int(box["row"])
        x = 80 + column * 280
        y = 90 + row * 130
        placed[(column, row)] = (x + 100, y + 36)
        kind = str(box["kind"])
        canvas.rect(x, y, 200, 72, fills.get(kind, PAPER))
        canvas.frame(x, y, 200, 72, borders.get(kind, INK), 2)
        canvas.text(x + 12, y + 16, str(box["label"]).upper(), INK, 2)
        canvas.text(x + 12, y + 42, str(box["detail"]).upper(), MUTED, 1)
    for box in boxes:
        column = int(box["column"])
        row = int(box["row"])
        if (column, row) not in placed:
            continue
        x1, y1 = placed[(column, row)]
        parent = box.get("parent")
        if isinstance(parent, tuple) and parent in placed:
            x0, y0 = placed[parent]
            canvas.line(x0, y0 + 36, x1, y1 - 36, INK)
        uncle = box.get("uncle")
        if isinstance(uncle, tuple) and uncle in placed:
            x0, y0 = placed[uncle]
            canvas.line(x0, y0 + 36, x1, y1 - 36, RUST)
    canvas.save(path)
