"""Prepare bounded Round 2 ear layers for Plan 07 case A.

The input is the already frozen full-canvas RGBA head layer.  No generated
pixels, model, or dependency are introduced: masks divide the two ears from
the stable face/head base, and soft overlap around each ear root keeps the
rotation seam inside existing fur texture.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


CANVAS = (1080, 1920)


def soft_polygon(points: list[tuple[int, int]], blur: float = 4.0) -> Image.Image:
    mask = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def with_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image:
    output = image.copy()
    output.putalpha(alpha)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    head = Image.open(args.head).convert("RGBA")
    if head.size != CANVAS:
        raise SystemExit(f"expected {CANVAS}, got {head.size}")
    alpha = head.getchannel("A")

    # The diagonals cross inside the fur-covered ear roots.  A feathered,
    # intentionally overlapping root gives each child layer a few pixels of
    # safe rotation room while the base retains the face and neck identity.
    left_mask = soft_polygon([(248, 425), (466, 442), (480, 636), (395, 686), (295, 624)])
    right_mask = soft_polygon([(832, 425), (614, 442), (600, 636), (685, 686), (785, 624)])
    left_alpha = ImageChops.multiply(alpha, left_mask)
    right_alpha = ImageChops.multiply(alpha, right_mask)
    union = ImageChops.lighter(left_mask, right_mask)
    base_alpha = ImageChops.multiply(alpha, ImageChops.invert(union))

    args.output.mkdir(parents=True, exist_ok=True)
    with_alpha(head, base_alpha).save(args.output / "head-base.png")
    with_alpha(head, left_alpha).save(args.output / "ear-left.png")
    with_alpha(head, right_alpha).save(args.output / "ear-right.png")

    # Static reconstruction proof must match the input before motion starts.
    proof = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    proof.alpha_composite(with_alpha(head, base_alpha))
    proof.alpha_composite(with_alpha(head, left_alpha))
    proof.alpha_composite(with_alpha(head, right_alpha))
    proof.save(args.output / "head-reconstruction.png")


if __name__ == "__main__":
    main()
