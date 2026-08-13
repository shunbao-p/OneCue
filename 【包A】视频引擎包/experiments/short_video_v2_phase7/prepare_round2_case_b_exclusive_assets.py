from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops


# Front-most independently moving artwork owns shared source pixels first.
# The static stem is the residual owner so every visible subject pixel belongs
# to exactly one layer and no old-position duplicate can remain behind a tween.
OWNERSHIP_PRIORITY = (
    "foreground",
    "leaf-left",
    "leaf-top",
    "leaf-right",
)
OUTPUT_LAYERS = (
    "stem-base",
    "leaf-right",
    "leaf-top",
    "leaf-left",
    "foreground",
)
VALIDATION_THRESHOLDS = tuple(range(256))
EXPECTED_INPUT_SHA256 = {
    "background-clean": "0b39c25141235462b85723ede5a0be1aac0f59e8e8d89adc6253d22d72327dc7",
    "subject-cutout": "65fdab0cd3987e5058448202e235b7ece1f707aeaf38ff0723d49709b0d19225",
    "foreground": "a9b4df4d9a37503a15b4b2924ce6bdd806e4313f8f389be637c50053bdd88654",
    "leaf-left": "00d90a04c867a430e975048efa4a79c3712f9b48f0bd80b05997d1f2fc63f585",
    "leaf-top": "3d92c748dcd93d2a0d6249346563d37914f90b0a6b951ec4da28bd5e4c4618ce",
    "leaf-right": "da2a722b721e08b227dc6059cbe9eda2d5bfa26e6b9c33896dce79edba83aef0",
}


def load_rgba(root: Path, name: str) -> Image.Image:
    return Image.open(root / f"{name}.png").convert("RGBA")


def binary_alpha(image: Image.Image, threshold: int) -> Image.Image:
    return image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    )


def nonzero_count(image: Image.Image) -> int:
    return sum(image.histogram()[1:])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_owned_layer(
    subject: Image.Image,
    assignment: Image.Image,
) -> Image.Image:
    transparent = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    result = Image.composite(subject, transparent, assignment)
    result.putalpha(ImageChops.multiply(subject.getchannel("A"), assignment))
    return result


def union_masks(masks: list[Image.Image], size: tuple[int, int]) -> Image.Image:
    result = Image.new("L", size, 0)
    for mask in masks:
        result = ImageChops.lighter(result, mask)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create Round 2 case-B layers with one-and-only-one alpha owner "
            "for every visible subject pixel."
        )
    )
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--proof", type=Path)
    args = parser.parse_args()

    input_paths = {
        name: args.input_root / f"{name}.png"
        for name in EXPECTED_INPUT_SHA256
    }
    input_report = {
        name: {
            "path": str(path),
            "sha256": sha256(path),
            "expected_sha256": EXPECTED_INPUT_SHA256[name],
            "match": sha256(path) == EXPECTED_INPUT_SHA256[name],
        }
        for name, path in input_paths.items()
    }
    frozen_inputs_match = all(
        item["match"] for item in input_report.values()
    )
    if not frozen_inputs_match:
        raise SystemExit("case-B frozen input hash gate failed")

    subject = load_rgba(args.input_root, "subject-cutout")
    background = load_rgba(args.input_root, "background-clean")
    candidates = {
        name: load_rgba(args.input_root, name)
        for name in OWNERSHIP_PRIORITY
    }
    if any(image.size != subject.size for image in candidates.values()):
        raise SystemExit("case-B layer dimensions do not match subject-cutout")
    if background.size != subject.size:
        raise SystemExit("case-B background dimensions do not match subject-cutout")

    subject_support = binary_alpha(subject, 0)
    owned = Image.new("L", subject.size, 0)
    assignments: dict[str, Image.Image] = {}
    for name in OWNERSHIP_PRIORITY:
        candidate_support = binary_alpha(candidates[name], 0)
        available = ImageChops.subtract(subject_support, owned)
        assignment = ImageChops.multiply(candidate_support, available)
        assignments[name] = assignment
        owned = ImageChops.lighter(owned, assignment)

    assignments["stem-base"] = ImageChops.subtract(subject_support, owned)
    layers = {
        name: make_owned_layer(subject, assignments[name])
        for name in OUTPUT_LAYERS
    }

    args.output_root.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}
    for name, image in layers.items():
        output_path = args.output_root / f"{name}.png"
        image.save(output_path, optimize=True)
        output_paths[name] = output_path

    # Keep a zero-byte-ownership compatibility asset for diagnostics only.
    seam_path = args.output_root / "seam-covers.png"
    Image.new("RGBA", subject.size, (0, 0, 0, 0)).save(
        seam_path, optimize=True
    )
    output_paths["seam-covers"] = seam_path

    # All hard gates operate on the files reloaded from disk, not on the
    # pre-save Pillow objects, so the report proves the actual frozen outputs.
    layers = {
        name: Image.open(output_paths[name]).convert("RGBA")
        for name in OUTPUT_LAYERS
    }

    reconstructed = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    for name in OUTPUT_LAYERS:
        reconstructed.paste(layers[name], (0, 0), assignments[name])
    normalized_subject = subject.copy()
    normalized_subject.paste(
        (0, 0, 0, 0),
        mask=ImageChops.invert(subject_support),
    )
    identity_difference = ImageChops.difference(
        reconstructed, normalized_subject
    )
    identity_max_error = max(
        maximum for _, maximum in identity_difference.getextrema()
    )

    expected_zero_pose = Image.alpha_composite(background, normalized_subject)
    actual_zero_pose = Image.alpha_composite(background, reconstructed)
    zero_pose_difference = ImageChops.difference(
        actual_zero_pose, expected_zero_pose
    )
    zero_pose_max_error = max(
        maximum for _, maximum in zero_pose_difference.getextrema()
    )
    if args.proof:
        args.proof.parent.mkdir(parents=True, exist_ok=True)
        actual_zero_pose.convert("RGB").save(args.proof, optimize=True)

    threshold_reports: dict[str, object] = {}
    threshold_gate_passed = True
    for threshold in VALIDATION_THRESHOLDS:
        subject_mask = binary_alpha(subject, threshold)
        layer_masks = {
            name: binary_alpha(layers[name], threshold)
            for name in OUTPUT_LAYERS
        }
        output_union = union_masks(list(layer_masks.values()), subject.size)
        holes = ImageChops.subtract(subject_mask, output_union)
        extras = ImageChops.subtract(output_union, subject_mask)
        overlaps: dict[str, int] = {}
        for left_name, right_name in combinations(OUTPUT_LAYERS, 2):
            overlap = ImageChops.multiply(
                layer_masks[left_name], layer_masks[right_name]
            )
            overlaps[f"{left_name}:{right_name}"] = nonzero_count(overlap)
        threshold_passed = (
            nonzero_count(holes) == 0
            and nonzero_count(extras) == 0
            and all(count == 0 for count in overlaps.values())
        )
        threshold_gate_passed = threshold_gate_passed and threshold_passed
        threshold_reports[str(threshold)] = {
            "holes": nonzero_count(holes),
            "extras": nonzero_count(extras),
            "pairwise_overlap": overlaps,
            "passed": threshold_passed,
        }

    report: dict[str, object] = {
        "schema": "short-video-v2.phase7.case-b-exclusive-alpha-report.v2",
        "ownership_threshold": 0,
        "ownership_priority": list(OWNERSHIP_PRIORITY),
        "residual_owner": "stem-base",
        "runtime_layers": list(OUTPUT_LAYERS),
        "removed_runtime_layer": "seam-covers",
        "inputs": input_report,
        "validation_threshold_count": len(VALIDATION_THRESHOLDS),
        "thresholds": threshold_reports,
        "identity": {
            "normalized_rgba_max_error": identity_max_error,
            "zero_pose_background_composite_max_error": zero_pose_max_error,
        },
        "outputs": {
            name: {
                "path": str(path),
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "alpha_bbox": Image.open(path).convert("RGBA").getchannel("A").getbbox(),
                "alpha_nonzero_pixels": nonzero_count(
                    Image.open(path).convert("RGBA").getchannel("A")
                ),
            }
            for name, path in output_paths.items()
        },
        "hard_gate": {
            "frozen_inputs_match": frozen_inputs_match,
            "multi_threshold_unique_ownership": threshold_gate_passed,
            "normalized_rgba_identity": identity_max_error == 0,
            "zero_pose_identity": zero_pose_max_error == 0,
            "passed": (
                frozen_inputs_match
                and threshold_gate_passed
                and identity_max_error == 0
                and zero_pose_max_error == 0
            ),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not report["hard_gate"]["passed"]:
        raise SystemExit("exclusive alpha ownership gate failed")


if __name__ == "__main__":
    main()
