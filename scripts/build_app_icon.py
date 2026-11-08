# -*- coding: utf-8 -*-
"""从矢量源生成 PNG / 多尺寸 Windows ICO，仅写 assets 目录。

运行：python -B scripts/build_app_icon.py
不启动学习主程序，不读取或创建学习记录。
"""
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QByteArray, QBuffer, QIODevice
from PyQt5.QtWidgets import QApplication
from app_icon import ASSET_DIR, ICON_SIZES, render_icon


def png_bytes(pixmap):
    data = QByteArray()
    stream = QBuffer(data)
    if not stream.open(QIODevice.WriteOnly):
        raise RuntimeError("无法创建图标内存缓冲")
    try:
        if not pixmap.save(stream, "PNG"):
            raise RuntimeError("无法编码图标 PNG")
    finally:
        stream.close()
    return bytes(data)


def main():
    app = QApplication.instance() or QApplication([sys.argv[0]])
    assets = Path(ASSET_DIR)
    assets.mkdir(exist_ok=True)
    images = [(side, png_bytes(render_icon(side))) for side in ICON_SIZES]
    offset = 6 + len(images) * 16
    directory = []
    payload = []
    for side, data in images:
        field = side if side < 256 else 0
        directory.append(struct.pack("<BBBBHHII", field, field, 0, 0, 1, 32, len(data), offset))
        payload.append(data)
        offset += len(data)
    ico = struct.pack("<HHH", 0, 1, len(images)) + b"".join(directory) + b"".join(payload)
    (assets / "vocab-card.ico").write_bytes(ico)
    (assets / "vocab-card.png").write_bytes(png_bytes(render_icon(512)))
    print("ICON_SIZES", ",".join(map(str, ICON_SIZES)))
    print("ICO_BYTES", len(ico))
    print("ASSETS", str(assets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
