from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
CASE = (
    ROOT
    / "成片"
    / "短视频V2样片"
    / "phase7-hyperframes-micro-motion"
    / "case-b-project-migration"
)
SOURCE = CASE / "assets" / "source"
LAYERS = CASE / "assets" / "layers"
PROOFS = CASE / "proofs"
SIZE = (1080, 1920)


def fit(path: Path, mode: str = "RGBA") -> Image.Image:
    return Image.open(path).convert(mode).resize(SIZE, Image.Resampling.LANCZOS)


def polygon_mask(points: list[tuple[int, int]], blur: float = 2.0) -> Image.Image:
    mask = Image.new("L", SIZE, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def masked_subject(subject: Image.Image, mask: Image.Image) -> Image.Image:
    result = subject.copy()
    result.putalpha(ImageChops.multiply(subject.getchannel("A"), mask))
    return result


def composite(background: Image.Image, layers: list[Image.Image]) -> Image.Image:
    frame = background.convert("RGBA")
    for layer in layers:
        frame.alpha_composite(layer)
    return frame


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    LAYERS.mkdir(parents=True, exist_ok=True)
    PROOFS.mkdir(parents=True, exist_ok=True)

    master = fit(SOURCE / "master.png")
    background = fit(SOURCE / "background-clean.png")
    subject = fit(SOURCE / "subject-cutout.png")

    leaf_top_mask = polygon_mask(
        [(210, 190), (540, 190), (575, 420), (520, 575), (390, 700), (280, 575), (205, 400)],
        0.0,
    )
    leaf_left_mask = polygon_mask(
        [(0, 405), (295, 405), (380, 505), (345, 645), (175, 690), (0, 620)],
        0.0,
    )
    leaf_right_mask = polygon_mask(
        [(445, 390), (735, 390), (920, 545), (890, 730), (650, 785), (475, 655)],
        0.0,
    )
    foreground_mask = polygon_mask(
        [(775, 710), (1080, 655), (1080, 1120), (875, 1160), (740, 965)],
        0.0,
    )
    seam_cover_mask = polygon_mask(
        [(345, 570), (455, 555), (490, 735), (350, 760)], 3.0
    )
    seam_cover_mask = ImageChops.lighter(
        seam_cover_mask,
        polygon_mask([(235, 545), (420, 555), (455, 705), (245, 725)], 3.0),
    )
    seam_cover_mask = ImageChops.lighter(
        seam_cover_mask,
        polygon_mask([(750, 900), (930, 880), (990, 1170), (770, 1180)], 3.0),
    )

    union = ImageChops.lighter(leaf_top_mask, leaf_left_mask)
    union = ImageChops.lighter(union, leaf_right_mask)
    union = ImageChops.lighter(union, foreground_mask)
    base_mask = ImageChops.invert(union.point(lambda value: 255 if value > 8 else 0))

    layers = {
        "master": master,
        "background-clean": background,
        "subject-cutout": subject,
        "stem-base": masked_subject(subject, base_mask),
        "leaf-top": masked_subject(subject, leaf_top_mask),
        "leaf-left": masked_subject(subject, leaf_left_mask),
        "leaf-right": masked_subject(subject, leaf_right_mask),
        "foreground": masked_subject(subject, foreground_mask),
        "seam-covers": masked_subject(subject, seam_cover_mask),
    }
    for name, image in layers.items():
        image.save(LAYERS / f"{name}.png", optimize=True)

    hero = composite(
        background,
        [
            layers["stem-base"],
            layers["leaf-top"],
            layers["leaf-left"],
            layers["leaf-right"],
            layers["foreground"],
            layers["seam-covers"],
        ],
    )
    hero.save(PROOFS / "hero-recomposition.png", optimize=True)

    peak_layers = [layers["stem-base"]]
    transforms = [
        (layers["leaf-top"], (390, 680), 0.7),
        (layers["leaf-left"], (330, 625), -0.5),
        (layers["leaf-right"], (520, 730), 0.0),
        (layers["foreground"], (820, 1080), -0.45),
    ]
    for layer, pivot, angle in transforms:
        rotated = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=pivot)
        peak_layers.append(rotated)
    peak_layers.append(layers["seam-covers"])
    peak = composite(background, peak_layers)
    peak.save(PROOFS / "leaf-peak.png", optimize=True)

    alpha = subject.getchannel("A")
    for name, color in (("alpha-light", (242, 242, 242, 255)), ("alpha-dark", (22, 24, 28, 255))):
        plate = Image.new("RGBA", SIZE, color)
        plate.alpha_composite(subject)
        plate.save(PROOFS / f"{name}.png", optimize=True)

    thumbs = [master, background, subject, hero, peak]
    sheet = Image.new("RGB", (270 * len(thumbs), 480), "#171717")
    for index, image in enumerate(thumbs):
        sheet.paste(image.convert("RGB").resize((270, 480), Image.Resampling.LANCZOS), (index * 270, 0))
    sheet.save(PROOFS / "contact-sheet.jpg", quality=92)

    diff = ImageChops.difference(hero.convert("RGB"), peak.convert("RGB"))
    print("peak_diff_bbox", diff.getbbox())
    print("alpha_corners", [alpha.getpixel(point) for point in ((0, 0), (1079, 0), (0, 1919), (1079, 1919))])
    for path in sorted((*LAYERS.glob("*.png"), *PROOFS.glob("*"))):
        print(path.relative_to(CASE), sha(path))


if __name__ == "__main__":
    main()
