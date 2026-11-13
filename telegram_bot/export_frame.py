"""Generate the front-frame overlay from the approved source without altering it.

Run from repository root: python -m telegram_bot.export_frame
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from PIL import Image, ImageDraw
from .tryon import DATA
import json

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
    diagnostics = json.loads((DATA / 'mask.json').read_text(encoding='utf-8'))
    guide = Image.open(source).convert('RGB')
    drawer = ImageDraw.Draw(guide)
    for polygon in diagnostics['outer']:
        drawer.line(polygon + [polygon[0]], fill=(255, 25, 25), width=5)
    for polygon in diagnostics['holes']:
        drawer.line(polygon + [polygon[0]], fill=(0, 140, 255), width=5)
    drawer.line(diagnostics['bridge']+[diagnostics['bridge'][0]],fill=(0,255,40), width=4)
    guide.save(ROOT/'qa-mask-contours.jpg', quality=85)
    preview = Image.new('RGB', frame.size, (198, 155, 131))
    preview.paste(frame, (0, 0), frame)
    preview.save(ROOT/'qa-overlay-preview.jpg',quality=90)
    destination = ROOT / 'dacchi-34355-front.png'
    frame.save(destination, format='PNG', optimize=True)
    fingerprint_after = sha256(source.read_bytes()).hexdigest()
    if fingerprint_before != fingerprint_after:
        raise SystemExit('Ошибка: исходное изображение изменилось!')
    print(f'Source SHA256: {fingerprint_after}; Overlay {frame.size}; {destination.name}: {destination.stat().st_size} bytes')


if __name__ == '__main__':
    main()