"""Build deterministic in-between head poses from Apple Vision optical flow.

The flow is computed outside this script by the local macOS Vision framework.
No model or package is downloaded.  This script only remaps the two frozen RGBA
pose layers and blends their warped pixels at fixed fractions.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def read_flow(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        width, height, row_bytes = map(int, handle.readline().split())
        payload = handle.read()
    rows = np.frombuffer(payload, dtype=np.uint8).reshape(height, row_bytes)
    return rows[:, : width * 8].copy().view(np.float32).reshape(height, width, 2)


def resize_flow(flow: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize a coarse flow field and preserve its displacement in full-res pixels."""

    source_height, source_width = flow.shape[:2]
    if (source_width, source_height) == (width, height):
        return flow
    x = np.asarray(
        Image.fromarray(flow[..., 0], mode="F").resize((width, height), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) * (width / source_width)
    y = np.asarray(
        Image.fromarray(flow[..., 1], mode="F").resize((width, height), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) * (height / source_height)
    return np.stack((x, y), axis=2)


def bilinear(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    height, width, _ = image.shape
    x = np.clip(x, 0, width - 1)
    y = np.clip(y, 0, height - 1)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = (x - x0)[..., None]
    wy = (y - y0)[..., None]
    top = image[y0, x0] * (1 - wx) + image[y0, x1] * wx
    bottom = image[y1, x0] * (1 - wx) + image[y1, x1] * wx
    return top * (1 - wy) + bottom * wy


def warp(image: np.ndarray, flow: np.ndarray, fraction: float) -> np.ndarray:
    height, width, _ = image.shape
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    return bilinear(image, xx - flow[..., 0] * fraction, yy - flow[..., 1] * fraction)


def premultiply(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3:4] / 255.0
    return np.concatenate((rgba[..., :3] * alpha, alpha * 255.0), axis=2)


def unpremultiply(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3:4] / 255.0
    rgb = np.divide(rgba[..., :3], alpha, out=np.zeros_like(rgba[..., :3]), where=alpha > 1e-5)
    return np.concatenate((rgb, rgba[..., 3:4]), axis=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--neutral", type=Path, required=True)
    parser.add_argument("--nod", type=Path, required=True)
    parser.add_argument("--forward-flow", type=Path, required=True)
    parser.add_argument("--backward-flow", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fractions", default="0.2,0.4,0.6,0.8")
    parser.add_argument(
        "--flow-scale",
        type=float,
        default=1.0,
        help="Diagnostic gain applied to Vision's pixel displacement vectors.",
    )
    args = parser.parse_args()

    neutral = np.asarray(Image.open(args.neutral).convert("RGBA"), dtype=np.float32)
    nod = np.asarray(Image.open(args.nod).convert("RGBA"), dtype=np.float32)
    if neutral.shape != nod.shape:
        raise SystemExit(f"pose dimensions differ: {neutral.shape} != {nod.shape}")
    height, width = neutral.shape[:2]
    forward = resize_flow(read_flow(args.forward_flow), width, height) * args.flow_scale
    backward = resize_flow(read_flow(args.backward_flow), width, height) * args.flow_scale

    neutral_p = premultiply(neutral)
    nod_p = premultiply(nod)
    args.output.mkdir(parents=True, exist_ok=True)
    for fraction in [float(value) for value in args.fractions.split(",")]:
        if not 0 < fraction < 1:
            raise SystemExit(f"invalid fraction: {fraction}")
        start = warp(neutral_p, forward, fraction)
        end = warp(nod_p, backward, 1.0 - fraction)
        mixed = unpremultiply(start * (1.0 - fraction) + end * fraction)
        name = f"head-flow-{round(fraction * 100):02d}.png"
        Image.fromarray(np.clip(mixed, 0, 255).astype(np.uint8), "RGBA").save(args.output / name)


if __name__ == "__main__":
    main()
