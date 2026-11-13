"""Generate the front-frame overlay from the approved source without altering it.

Run from repository root: python -m telegram_bot.export_frame
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from PIL import Image

from .tryon import ROOT, frame_overlay


def main() -> None:
    source = ROOT / 'dacchi-34355.png'
    if not source.is_file():
        raise SystemExit('Фотография утверждённой оправы отсутствует')
    fingerprint_before = sha256(source.read_bytes()).hexdigest()
    frame = frame_overlay()
    if frame.mode != 'RGBA' or frame.width < 500 or frame.height < 100:
        raise SystemExit(f'Маска неверна: mode={frame.mode}, size={frame.size}')
    bbox = frame.getchannel('A').getbbox()
    if bbox is None:
        raise SystemExit('Маска пустая')
    destination = ROOT / 'dacchi-34355-front.png'
    frame.save(destination, format='PNG', optimize=True)
    fingerprint_after = sha256(source.read_bytes()).hexdigest()
    if fingerprint_before != fingerprint_after:
        raise SystemExit('Ошибка: исходное изображение изменилось!')
    print(f'Source SHA256: {fingerprint_after}; Overlay {frame.size}; {destination.name}: {destination.stat().st_size} bytes')


if __name__ == '__main__':
    main()