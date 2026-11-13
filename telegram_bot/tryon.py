"""Photo try-on engine. Never modifies the approved source image on disk."""
from __future__ import annotations

from io import BytesIO
from json import loads
from math import atan2, degrees, hypot
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 15_000_000


class TryOnError(ValueError):
    """Expected error for an invalid photo or missing face."""


def catalog() -> list[dict]:
    return loads((DATA / 'catalog.json').read_text(encoding='utf-8'))


def source_cutout(source: Image.Image, mask_data: dict | None = None) -> Image.Image:
    """Extract *existing pixels* of the photographed front; erase background, temples and labels.

    The contours are approximate manual masks for a single SKU; not a claim of 3D accuracy.
    """
    if mask_data is None:
        mask_data = loads((DATA / 'mask.json').read_text(encoding='utf-8'))
    rgb = source.convert('RGB')
    expected = (mask_data['source_width'], mask_data['source_height'])
    if rgb.size != expected:
        raise TryOnError(f'Размер изображения оправы {rgb.size} не совпадает с шаблоном {expected}')
    m = Image.new('L', rgb.size, 0)
    painter = ImageDraw.Draw(m)
    for points in mask_data['outer']:
        painter.polygon([tuple(p) for p in points], fill=255)
    painter.polygon([tuple(p) for p in mask_data['bridge']], fill=255)
    for points in mask_data['holes']:
        painter.polygon([tuple(p) for p in points], fill=0)
    # Original was shot on white; convert its white matte to translucency without new frame geometry.
    gray = ImageOps.grayscale(rgb)
    # Suppress the off-white photo backdrop and faint floor shadows while retaining
    # the photographed rim tones. 240 is the verified white-matte cutoff for this SKU.
    opacity = gray.point(lambda lum: max(0, min(255, round((240 - lum) * 3.8))))
    alpha = ImageChops.multiply(m, opacity)
    rgba = rgb.convert('RGBA')
    rgba.putalpha(alpha)
    bbox = rgba.getbbox()
    if not bbox:
        raise TryOnError('Не удалось выделить оправу')
    return rgba.crop(bbox)


def frame_overlay() -> Image.Image:
    return source_cutout(Image.open(ROOT / 'dacchi-34355.png'))


def anchor_from_landmarks(landmarks, width: int, height: int) -> tuple[float, float, float, float]:
    if len(landmarks) <= 263:
        raise TryOnError('Недостаточно ориентиров лица')
    left, right = landmarks[33], landmarks[263]
    x1, y1 = left.x * width, left.y * height
    x2, y2 = right.x * width, right.y * height
    eye_distance = hypot(x2 - x1, y2 - y1)
    if eye_distance < min(width, height) * .04:
        raise TryOnError('Расстояние между глазами определено неверно')
    # PIL image rotations are counterclockwise; Canvas positive angle is clockwise.
    return (x1 + x2) / 2, (y1 + y2) / 2, eye_distance, degrees(atan2(y2 - y1, x2 - x1))


def composite_on_photo(photo: Image.Image, frame: Image.Image,
                       anchor: tuple[float, float, float, float],
                       scale: float = 1, dx: float = 0, dy: float = 0,
                       rotation: float = 0) -> Image.Image:
    if not 0.6 <= scale <= 1.6 or not -30 <= rotation <= 30:
        raise TryOnError('Некорректная настройка оправы')
    target = ImageOps.exif_transpose(photo).convert('RGBA')
    model = catalog()[0]
    x, y, eye_dist, angle = anchor
    width_px = max(1, round(eye_dist * model['width_to_eye_distance'] * scale))
    height_px = max(1, round(width_px * frame.height / frame.width))
    resized = frame.resize((width_px, height_px), Image.Resampling.LANCZOS)
    turned = resized.rotate(-(angle + rotation), resample=Image.Resampling.BICUBIC, expand=True)
    center_x = x + dx * target.width / 1000
    center_y = y + width_px * model['eye_line_offset_ratio'] + dy * target.height / 1000
    px, py = round(center_x - turned.width / 2), round(center_y - turned.height / 2)
    layer = Image.new('RGBA', target.size, (0, 0, 0, 0))
    layer.paste(turned, (px, py))
    return Image.alpha_composite(target, layer).convert('RGB')


def render_photo_bytes(photo_bytes: bytes, model_path: Path | None = None) -> bytes:
    """Process a Telegram photo only in RAM. Requires MediaPipe Tasks installed."""
    if not photo_bytes or len(photo_bytes) > MAX_BYTES:
        raise TryOnError('Максимальный размер фотографии — 8 МБ')
    try:
        with Image.open(BytesIO(photo_bytes)) as raw:
            raw.load()
            source = ImageOps.exif_transpose(raw).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise TryOnError('Пришлите корректное изображение JPG или PNG') from exc
    if min(source.size) < 160:
        raise TryOnError('Фотография слишком маленькая')
    if max(source.size) > 1600:
        source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    import numpy as np
    import mediapipe as mp

    path = model_path or ROOT / 'face_landmarker.task'
    if not path.is_file():
        raise RuntimeError('Файл face_landmarker.task отсутствует')
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_faces=1,
    )
    with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                          data=np.asarray(source)))
    if len(result.face_landmarks) != 1:
        raise TryOnError('Не удалось найти одно лицо. Загрузите селфи анфас с хорошим светом')
    anchor = anchor_from_landmarks(result.face_landmarks[0], *source.size)
    result_image = composite_on_photo(source, frame_overlay(), anchor)
    buffer = BytesIO()
    result_image.save(buffer, format='JPEG', quality=91, optimize=True)
    return buffer.getvalue()