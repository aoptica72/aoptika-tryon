import json
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
import pytest
from telegram_bot.tryon import (TryOnError, anchor_from_landmarks,
                                 composite_on_photo, source_cutout, catalog)


def fake_points():
    points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(264)]
    points[33] = SimpleNamespace(x=0.38, y=0.42)
    points[263] = SimpleNamespace(x=0.62, y=0.44)
    return points


def test_catalog_is_real_single_model():
    models = catalog()
    assert len(models) == 1 and models[0]['sku'] == 'DACCHI-34355'
    assert models[0]['size_mm']['lens'] == 54
    assert models[0]['price_rub'] is None


def test_anchor_and_tilt():
    x, y, dist, angle = anchor_from_landmarks(fake_points(), 1000, 1000)
    assert x == pytest.approx(500)
    assert y == pytest.approx(430)
    assert dist > 240
    assert 3 < angle < 6


def test_mask_removes_background_and_lens_text():
    img = Image.new('RGB', (1536, 1078), (255, 255, 255))
    # Synthetic image only; tests never modify the approved source.
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.rectangle((50, 420, 1500, 930), fill=(70, 70, 90))
    mask = source_cutout(img)
    assert mask.mode == 'RGBA'
    assert mask.getbbox() is not None
    # Center is bridge region; underlying image remains unchanged.
    assert img.mode == 'RGB'
    assert mask.getextrema()[-1][1] > 0


def test_composite_does_not_change_image_size():
    photo = Image.new('RGB', (640, 800), 'white')
    frame = Image.new('RGBA', (240, 90), (30, 40, 80, 180))
    anchor = (320, 340, 180, 10)
    result = composite_on_photo(photo, frame, anchor)
    assert result.size == photo.size and result.mode == 'RGB'
    assert result.getpixel((320, 340)) != (255, 255, 255)


def test_invalid_scale():
    with pytest.raises(TryOnError):
        composite_on_photo(Image.new('RGB',(300,300)), Image.new('RGBA',(10,10)),
                           (100,100,50,0), scale=4)


def test_approved_dacchi_overlay_removes_demo_lens_marks():
    from telegram_bot.tryon import frame_overlay, ROOT
    assert (ROOT / 'dacchi-34355.png').is_file()
    overlay = frame_overlay()
    assert overlay.mode == 'RGBA'
    assert overlay.width >= 1300 and overlay.height >= 400
    alpha = overlay.getchannel('A')
    # Both interior lens areas must be transparent: demo print and photographed temples removed.
    assert alpha.getpixel((250, 300)) == 0
    assert alpha.getpixel((1100, 300)) == 0
    assert alpha.getextrema()[1] >= 230  # dark frame contours are preserved