"""Adversarial probes for the conservative screenshot similarity signals."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ss_dcl.similarity import compute_signals, near_distance


def _screenshot(
    *, accent: tuple[int, int, int] = (190, 55, 45), text_variant: int = 0
) -> Image.Image:
    """Small deterministic app screenshot with broad UI structure and text-like lines."""
    image = Image.new("RGB", (320, 200), (246, 247, 249))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 319, 25), fill=(224, 226, 229))
    draw.rectangle((0, 26, 55, 199), fill=(237, 239, 242))
    draw.rectangle((68, 38, 310, 58), fill=accent)
    for row in range(2):
        top = 70 + row * 61
        draw.rectangle((68, top, 310, top + 51), fill=(255, 255, 255), outline=(215, 218, 222))
        draw.rectangle((76, top + 8, 117, top + 43), fill=(75, 120, 170))
        for line in range(3):
            length = 45 + ((text_variant * 31 + row * 27 + line * 17) % 90)
            draw.rectangle(
                (128, top + 10 + line * 10, 128 + length, top + 14 + line * 10),
                fill=(105, 110, 115),
            )
    return image


def _save_signals(
    tmp_path: Path,
    name: str,
    image: Image.Image,
    *,
    format: str = "PNG",
    quality: int = 78,
):
    path = tmp_path / f"{name}.{format.lower()}"
    options = {"quality": quality} if format == "JPEG" else {}
    image.save(path, format=format, **options)
    return compute_signals(path)


def _hash_distance(a, b) -> int:
    assert a.dhash is not None and b.dhash is not None
    return (int(a.dhash, 16) ^ int(b.dhash, 16)).bit_count()


def _rgb_errors(a, b) -> tuple[float, float]:
    """Return global and worst 4x4-tile MAE in byte levels (0..255)."""
    assert a.rgb is not None and b.rgb is not None
    left, right = bytes.fromhex(a.rgb), bytes.fromhex(b.rgb)
    differences = [abs(x - y) for x, y in zip(left, right, strict=True)]
    regional_means = []
    for row in range(0, 16, 4):
        for col in range(0, 16, 4):
            region = [
                differences[(y * 16 + x) * 3 + channel]
                for y in range(row, row + 4)
                for x in range(col, col + 4)
                for channel in range(3)
            ]
            regional_means.append(sum(region) / len(region))
    return sum(differences) / len(differences), max(regional_means)


def _neutralized(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    gray.putdata([70 + int(value * 0.4) for value in gray.tobytes()])
    return gray.convert("RGB")


def _gray_color_variant(image: Image.Image, *, region: tuple[int, int, int, int] | None = None):
    """Shift RGB while keeping grayscale luminance stable; optionally tint one patch."""
    gray = _neutralized(image)
    if region is None:
        region = (0, 0, gray.width, gray.height)
    left, top, right, bottom = region
    for y in range(top, bottom):
        for x in range(left, right):
            pixel = gray.getpixel((x, y))
            assert isinstance(pixel, tuple)
            red, green, blue = pixel
            gray.putpixel((x, y), (red + 80, green - 40, blue - 4))
    return gray


def test_blank_and_low_contrast_images_are_not_near_matches(tmp_path: Path) -> None:
    blank = Image.new("RGB", (320, 200), (250, 250, 250))
    low_contrast = Image.new("RGB", (320, 200), (250, 250, 250))
    draw = ImageDraw.Draw(low_contrast)
    for x in range(0, 320, 20):
        draw.line((x, 0, x, 199), fill=(251, 251, 251), width=1)

    reference = _save_signals(tmp_path, "reference", _screenshot())
    blank_signals = _save_signals(tmp_path, "blank", blank)
    low_signals = _save_signals(tmp_path, "low-contrast", low_contrast)

    assert blank_signals.contrast == 0
    assert low_signals.contrast < 8
    assert near_distance(reference, blank_signals) is None
    assert near_distance(reference, low_signals) is None


def test_rgb_gate_rejects_luminance_identical_recolor(tmp_path: Path) -> None:
    neutral = _neutralized(_screenshot())
    recolored = _gray_color_variant(_screenshot())
    neutral_signals = _save_signals(tmp_path, "neutral", neutral)
    recolored_signals = _save_signals(tmp_path, "recolored", recolored)
    global_mae, worst_region_mae = _rgb_errors(neutral_signals, recolored_signals)

    # dHash sees identical luminance structure; color-aware comparison catches the collision.
    assert _hash_distance(neutral_signals, recolored_signals) == 0
    assert global_mae > 12
    assert worst_region_mae > 30
    assert near_distance(neutral_signals, recolored_signals) is None


def test_region_gate_catches_local_color_change_below_global_limit(tmp_path: Path) -> None:
    source = _neutralized(_screenshot())
    changed = _gray_color_variant(_screenshot(), region=(160, 100, 240, 150))
    source_signals = _save_signals(tmp_path, "local-source", source)
    changed_signals = _save_signals(tmp_path, "local-change", changed)
    global_mae, worst_region_mae = _rgb_errors(source_signals, changed_signals)

    assert _hash_distance(source_signals, changed_signals) == 0
    assert global_mae <= 12
    assert worst_region_mae > 30
    assert near_distance(source_signals, changed_signals) is None


def test_jpeg_reencode_and_proportional_resize_remain_candidates(tmp_path: Path) -> None:
    original = _screenshot()
    jpeg = tmp_path / "reencoded.jpg"
    original.save(jpeg, format="JPEG", quality=78)
    with Image.open(jpeg) as decoded:
        jpeg_image = decoded.convert("RGB")

    reference = _save_signals(tmp_path, "original", original)
    jpeg_signals = _save_signals(tmp_path, "jpeg", jpeg_image)
    resized_signals = _save_signals(
        tmp_path, "resized", original.resize((240, 150), Image.Resampling.LANCZOS)
    )

    assert near_distance(reference, jpeg_signals) is not None
    assert near_distance(reference, resized_signals) is not None
    assert _hash_distance(reference, jpeg_signals) <= 10
    assert _hash_distance(reference, resized_signals) <= 10


def test_text_changes_can_still_pass_and_distinct_layout_is_rejected(tmp_path: Path) -> None:
    reference_image = _screenshot()
    changed_text = _screenshot(text_variant=9)
    text_reference = _save_signals(tmp_path, "text-reference", reference_image)
    text_changed = _save_signals(tmp_path, "text-changed", changed_text)

    # This is a known limitation: tiny text is not reliable evidence of image identity.
    assert near_distance(text_reference, text_changed) is not None

    distinct = Image.new("RGB", (320, 200), (48, 54, 64))
    draw = ImageDraw.Draw(distinct)
    draw.rectangle((18, 20, 302, 58), fill=(208, 214, 222))
    draw.rectangle((18, 74, 110, 185), fill=(105, 151, 194))
    for x in range(128, 300, 24):
        height = 25 + (x % 61)
        draw.rectangle((x, 175 - height, x + 12, 175), fill=(220, 180, 82))
    distinct_signals = _save_signals(tmp_path, "distinct-layout", distinct)

    assert _hash_distance(text_reference, distinct_signals) > 10
    assert near_distance(text_reference, distinct_signals) is None
