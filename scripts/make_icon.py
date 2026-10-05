"""Generate assets/icon.ico (run once; the result is committed).

Usage: python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "icon.ico"


def render(size: int) -> bytes:
    """Draw the icon (a rising bar chart on a blue tile) and return PNG bytes."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.scale(size / 64, size / 64)

    gradient = QLinearGradient(0, 0, 0, 64)
    gradient.setColorAt(0, QColor("#4C8DF6"))
    gradient.setColorAt(1, QColor("#1F56C9"))
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)

    painter.setBrush(QColor("#FFFFFF"))
    for x, height in ((14, 14), (27, 24), (40, 34)):
        painter.drawRoundedRect(QRectF(x, 50 - height, 10, height), 2.5, 2.5)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for painting
    images = [render(size) for size in SIZES]

    # ICO layout: 6-byte header, one 16-byte entry per image, then the PNG data.
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, png in zip(SIZES, images):
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset
        )
        offset += len(png)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(header + entries + b"".join(images))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
