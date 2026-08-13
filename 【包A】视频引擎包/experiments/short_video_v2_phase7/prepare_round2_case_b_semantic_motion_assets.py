from __future__ import annotations

import argparse
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops


FROZEN_INPUT_SHA256 = {
    "background-clean": (
        "0b39c25141235462b85723ede5a0be1aac0f59e8e8d89adc6253d22d72327dc7"
    ),
    "subject-cutout": (
        "65fdab0cd3987e5058448202e235b7ece1f707aeaf38ff0723d49709b0d19225"
    ),
}
EXCLUSIVE_INPUT_SHA256 = {
    "stem-base": (
        "647c73665da1627321f703cf2be88f977328144e8909020315bbc6105ad637d7"
    ),
    "leaf-right": (
        "a1909ea4b7b1dc4bdb0ced9397383266c17f0fd8529c69efd5c72d74d05c8942"
    ),
    "leaf-top": (
        "b8be4165f23c7505c1ef1e8f17b423b87c0167cf4b5b9c80cdd156bf9636b99a"
    ),
    "leaf-left": (
        "776373648871e7424363482acf612724c7ef4898389c873eb8af77a90dbd81fe"
    ),
    "foreground": (
        "a79026e169483b3578be85a8a86d22ed1d0e492bee01fc79b91ed25735340eaa"
    ),
}
SOURCE_LAYERS = tuple(EXCLUSIVE_INPUT_SHA256)
OUTPUT_LAYERS = (
    "stem-base",
    "static-residual",
    "leaf-right",
    "leaf-top",
    "leaf-left",
    "foreground-plant",
)
DYNAMIC_LAYERS = (
    "leaf-top",
    "leaf-left",
    "foreground-plant",
)
VALIDATION_THRESHOLDS = tuple(range(256))
CONNECTIVITY = 8
ROOT_BAND_RATIO = 0.12
PIVOT_HINTS = {
    "leaf-top": {
        "anchor_px": [390, 680],
        "semantics": "narrow lower stem attachment",
    },
    "leaf-left": {
        "anchor_px": [330, 626],
        "semantics": (
            "right-side stem attachment; do not infer the pivot from the "
            "lower edge of the left blade"
        ),
    },
    "foreground-plant": {
        "anchor_px": [916, 1148],
        "semantics": "lower stem attachment of the right-side plant",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def binary_alpha(image: Image.Image, threshold: int) -> Image.Image:
    return image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    )


def nonzero_count(image: Image.Image) -> int:
    return sum(image.histogram()[1:])


def maximum_channel_error(left: Image.Image, right: Image.Image) -> int:
    difference = ImageChops.difference(left, right)
    return max(maximum for _, maximum in difference.getextrema())


def connected_components(
    alpha: Image.Image,
    *,
    retain_pixels: bool = False,
) -> list[dict[str, object]]:
    width, height = alpha.size
    values = alpha.tobytes()
    seen = bytearray(width * height)
    components: list[dict[str, object]] = []

    for seed, seed_alpha in enumerate(values):
        if seed_alpha == 0 or seen[seed]:
            continue
        seen[seed] = 1
        stack = [seed]
        pixels: list[int] | None = [] if retain_pixels else None
        count = 0
        alpha_sum = 0
        alpha_max = 0
        min_x = width
        min_y = height
        max_x = -1
        max_y = -1

        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            value = values[index]
            count += 1
            alpha_sum += value
            alpha_max = max(alpha_max, value)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            if pixels is not None:
                pixels.append(index)

            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                row_start = neighbor_y * width
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row_start + neighbor_x
                    if neighbor == index:
                        continue
                    if values[neighbor] and not seen[neighbor]:
                        seen[neighbor] = 1
                        stack.append(neighbor)

        component: dict[str, object] = {
            "alpha_nonzero_pixels": count,
            "alpha_sum": alpha_sum,
            "alpha_max": alpha_max,
            "alpha_bbox": [min_x, min_y, max_x + 1, max_y + 1],
            "touches_canvas_edge": (
                min_x == 0
                or min_y == 0
                or max_x == width - 1
                or max_y == height - 1
            ),
        }
        if pixels is not None:
            component["pixels"] = pixels
        components.append(component)

    components.sort(
        key=lambda component: (
            int(component["alpha_nonzero_pixels"]),
            int(component["alpha_sum"]),
        ),
        reverse=True,
    )
    return components


def public_component_stats(
    components: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            key: value
            for key, value in component.items()
            if key != "pixels"
        }
        for component in components
    ]


def mask_from_pixels(
    size: tuple[int, int], pixels: list[int]
) -> Image.Image:
    mask = bytearray(size[0] * size[1])
    for index in pixels:
        mask[index] = 255
    return Image.frombytes("L", size, bytes(mask))


def split_largest_component(
    image: Image.Image,
) -> tuple[Image.Image, Image.Image, list[dict[str, object]]]:
    components = connected_components(
        image.getchannel("A"), retain_pixels=True
    )
    if not components:
        raise SystemExit("semantic source layer has no visible alpha component")
    selected_pixels = components[0]["pixels"]
    if not isinstance(selected_pixels, list):
        raise AssertionError("component pixel retention failed")
    selected_mask = mask_from_pixels(image.size, selected_pixels)
    transparent = Image.new("RGBA", image.size, (0, 0, 0, 0))
    selected = Image.composite(image, transparent, selected_mask)
    residual = Image.composite(transparent, image, selected_mask)
    return selected, residual, components


def merge_disjoint(images: list[Image.Image]) -> Image.Image:
    if not images:
        raise ValueError("at least one image is required")
    result = Image.new("RGBA", images[0].size, (0, 0, 0, 0))
    for image in images:
        support = binary_alpha(image, 0)
        result = Image.composite(image, result, support)
    return result


def root_band_report(image: Image.Image) -> dict[str, object]:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("dynamic layer has no alpha bbox")
    x0, y0, x1, y1 = bbox
    band_height = max(1, math.ceil((y1 - y0) * ROOT_BAND_RATIO))
    band_y0 = y1 - band_height
    band = alpha.crop((x0, band_y0, x1, y1))
    band_bbox = band.getbbox()
    absolute_band_bbox = None
    weighted_x = 0
    weighted_y = 0
    alpha_sum = 0
    if band_bbox is not None:
        bx0, by0, bx1, by1 = band_bbox
        absolute_band_bbox = [
            x0 + bx0,
            band_y0 + by0,
            x0 + bx1,
            band_y0 + by1,
        ]
        band_values = band.load()
        for local_y in range(band.height):
            for local_x in range(band.width):
                value = band_values[local_x, local_y]
                if value:
                    weighted_x += (x0 + local_x) * value
                    weighted_y += (band_y0 + local_y) * value
                    alpha_sum += value
    centroid = (
        [round(weighted_x / alpha_sum, 3), round(weighted_y / alpha_sum, 3)]
        if alpha_sum
        else None
    )
    return {
        "definition": "bottom 12% of the selected alpha bbox; morphology hint only",
        "ratio": ROOT_BAND_RATIO,
        "y_range": [band_y0, y1],
        "alpha_bbox": absolute_band_bbox,
        "alpha_nonzero_pixels": nonzero_count(band),
        "alpha_weighted_centroid_px": centroid,
    }


def input_record(path: Path, expected_sha256: str) -> dict[str, object]:
    actual_sha256 = sha256(path)
    return {
        "path": str(path),
        "sha256": actual_sha256,
        "expected_sha256": expected_sha256,
        "match": actual_sha256 == expected_sha256,
        "size": path.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split Round 2 case-B exclusive assets into three semantically "
            "connected motion layers plus static residual ownership."
        )
    )
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--exclusive-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--proof", type=Path)
    args = parser.parse_args()

    frozen_paths = {
        name: args.frozen_root / f"{name}.png"
        for name in FROZEN_INPUT_SHA256
    }
    exclusive_paths = {
        name: args.exclusive_root / f"{name}.png"
        for name in EXCLUSIVE_INPUT_SHA256
    }
    input_report = {
        "frozen": {
            name: input_record(path, FROZEN_INPUT_SHA256[name])
            for name, path in frozen_paths.items()
        },
        "exclusive_v2": {
            name: input_record(path, EXCLUSIVE_INPUT_SHA256[name])
            for name, path in exclusive_paths.items()
        },
    }
    frozen_inputs_match = all(
        record["match"]
        for group in input_report.values()
        for record in group.values()
    )
    if not frozen_inputs_match:
        raise SystemExit("case-B frozen/exclusive input hash gate failed")

    background = load_rgba(frozen_paths["background-clean"])
    subject = load_rgba(frozen_paths["subject-cutout"])
    sources = {
        name: load_rgba(path) for name, path in exclusive_paths.items()
    }
    if background.size != subject.size or any(
        image.size != subject.size for image in sources.values()
    ):
        raise SystemExit("case-B semantic input dimensions do not match")

    leaf_top, top_residual, top_components = split_largest_component(
        sources["leaf-top"]
    )
    leaf_left, left_residual, left_components = split_largest_component(
        sources["leaf-left"]
    )
    foreground_plant, foreground_residual, foreground_components = (
        split_largest_component(sources["foreground"])
    )
    static_residual = merge_disjoint(
        [top_residual, left_residual, foreground_residual]
    )
    outputs = {
        "stem-base": sources["stem-base"],
        "static-residual": static_residual,
        "leaf-right": sources["leaf-right"],
        "leaf-top": leaf_top,
        "leaf-left": leaf_left,
        "foreground-plant": foreground_plant,
    }

    args.output_root.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}
    for name in OUTPUT_LAYERS:
        output_path = args.output_root / f"{name}.png"
        outputs[name].save(output_path, optimize=True)
        output_paths[name] = output_path

    # All gates below prove the serialized PNGs, not pre-save Pillow objects.
    outputs = {
        name: load_rgba(output_paths[name]) for name in OUTPUT_LAYERS
    }
    source_reconstruction = merge_disjoint(
        [sources[name] for name in SOURCE_LAYERS]
    )
    output_reconstruction = merge_disjoint(
        [outputs[name] for name in OUTPUT_LAYERS]
    )
    subject_support = binary_alpha(subject, 0)
    normalized_subject = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    normalized_subject = Image.composite(
        subject, normalized_subject, subject_support
    )
    source_to_subject_error = maximum_channel_error(
        source_reconstruction, normalized_subject
    )
    output_to_source_error = maximum_channel_error(
        output_reconstruction, source_reconstruction
    )
    output_to_subject_error = maximum_channel_error(
        output_reconstruction, normalized_subject
    )
    expected_zero_pose = Image.alpha_composite(
        background, normalized_subject
    )
    actual_zero_pose = Image.alpha_composite(
        background, output_reconstruction
    )
    zero_pose_error = maximum_channel_error(
        actual_zero_pose, expected_zero_pose
    )
    if args.proof:
        args.proof.parent.mkdir(parents=True, exist_ok=True)
        actual_zero_pose.convert("RGB").save(args.proof, optimize=True)

    threshold_reports: dict[str, object] = {}
    threshold_gate_passed = True
    for threshold in VALIDATION_THRESHOLDS:
        subject_mask = binary_alpha(subject, threshold)
        output_masks = {
            name: binary_alpha(outputs[name], threshold)
            for name in OUTPUT_LAYERS
        }
        output_union = Image.new("L", subject.size, 0)
        for mask in output_masks.values():
            output_union = ImageChops.lighter(output_union, mask)
        holes = nonzero_count(
            ImageChops.subtract(subject_mask, output_union)
        )
        extras = nonzero_count(
            ImageChops.subtract(output_union, subject_mask)
        )
        overlaps = {
            f"{left}:{right}": nonzero_count(
                ImageChops.multiply(
                    output_masks[left], output_masks[right]
                )
            )
            for left, right in combinations(OUTPUT_LAYERS, 2)
        }
        passed = (
            holes == 0
            and extras == 0
            and all(count == 0 for count in overlaps.values())
        )
        threshold_gate_passed = threshold_gate_passed and passed
        threshold_reports[str(threshold)] = {
            "holes": holes,
            "extras": extras,
            "pairwise_overlap": overlaps,
            "passed": passed,
        }

    output_components = {
        name: connected_components(outputs[name].getchannel("A"))
        for name in OUTPUT_LAYERS
    }
    dynamic_semantic_connected = all(
        len(output_components[name]) == 1 for name in DYNAMIC_LAYERS
    )
    foreground_bbox = outputs["foreground-plant"].getchannel("A").getbbox()
    foreground_is_right_plant = (
        foreground_bbox is not None
        and foreground_bbox[2] == subject.width
        and foreground_bbox[0] > subject.width // 2
    )

    source_split_report = {
        "leaf-top": {
            "selection": "largest 8-connected alpha>0 component",
            "components": public_component_stats(top_components),
            "selected_component_index": 0,
            "residual_component_count": max(0, len(top_components) - 1),
        },
        "leaf-left": {
            "selection": "largest 8-connected alpha>0 component",
            "components": public_component_stats(left_components),
            "selected_component_index": 0,
            "residual_component_count": max(0, len(left_components) - 1),
        },
        "foreground": {
            "selection": (
                "largest 8-connected alpha>0 component; verified as the "
                "right-side plant touching the right canvas edge"
            ),
            "components": public_component_stats(foreground_components),
            "selected_component_index": 0,
            "residual_component_count": max(
                0, len(foreground_components) - 1
            ),
        },
    }
    dynamic_geometry = {
        name: {
            "alpha_bbox": list(
                outputs[name].getchannel("A").getbbox() or ()
            ),
            "root_band_hint": root_band_report(outputs[name]),
            "authored_pivot_hint": PIVOT_HINTS[name],
        }
        for name in DYNAMIC_LAYERS
    }
    report: dict[str, object] = {
        "schema": "short-video-v2.phase7.case-b-semantic-motion-assets.v3",
        "connectivity": CONNECTIVITY,
        "split_threshold": "alpha > 0",
        "inputs": input_report,
        "source_layers": list(SOURCE_LAYERS),
        "output_layers": list(OUTPUT_LAYERS),
        "dynamic_layers": list(DYNAMIC_LAYERS),
        "static_layers": [
            name for name in OUTPUT_LAYERS if name not in DYNAMIC_LAYERS
        ],
        "source_splits": source_split_report,
        "outputs": {
            name: {
                "path": str(output_paths[name]),
                "sha256": sha256(output_paths[name]),
                "size": output_paths[name].stat().st_size,
                "alpha_bbox": list(
                    outputs[name].getchannel("A").getbbox() or ()
                ),
                "alpha_nonzero_pixels": nonzero_count(
                    outputs[name].getchannel("A")
                ),
                "connected_component_count": len(output_components[name]),
                "components": public_component_stats(
                    output_components[name]
                ),
            }
            for name in OUTPUT_LAYERS
        },
        "dynamic_geometry": dynamic_geometry,
        "validation_threshold_count": len(VALIDATION_THRESHOLDS),
        "thresholds": threshold_reports,
        "identity": {
            "source_layers_to_normalized_subject_rgba_max_error": (
                source_to_subject_error
            ),
            "outputs_to_source_layers_rgba_max_error": output_to_source_error,
            "outputs_to_normalized_subject_rgba_max_error": (
                output_to_subject_error
            ),
            "zero_pose_background_composite_rgba_max_error": zero_pose_error,
        },
        "hard_gate": {
            "frozen_inputs_match": frozen_inputs_match,
            "foreground_largest_component_is_right_plant": (
                foreground_is_right_plant
            ),
            "all_dynamic_layers_semantically_connected": (
                dynamic_semantic_connected
            ),
            "multi_threshold_unique_ownership": threshold_gate_passed,
            "source_layers_match_normalized_subject": (
                source_to_subject_error == 0
            ),
            "output_rgba_identity": (
                output_to_source_error == 0 and output_to_subject_error == 0
            ),
            "zero_pose_identity": zero_pose_error == 0,
            "passed": (
                frozen_inputs_match
                and foreground_is_right_plant
                and dynamic_semantic_connected
                and threshold_gate_passed
                and source_to_subject_error == 0
                and output_to_source_error == 0
                and output_to_subject_error == 0
                and zero_pose_error == 0
            ),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not report["hard_gate"]["passed"]:
        raise SystemExit("case-B semantic motion asset gate failed")


if __name__ == "__main__":
    main()
