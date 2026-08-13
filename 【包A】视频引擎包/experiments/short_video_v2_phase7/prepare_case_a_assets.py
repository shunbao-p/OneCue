"""计划 07 案例 A 的确定性资产切分与静态姿态证明。

本脚本只处理已冻结的本地 PNG，不下载模型、不连网、不渲染视频，
也不实现新的动画引擎。输出用于 HyperFrames 父子层和批次 2 静态硬门。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


CANVAS = (1080, 1920)
SOURCE_SIZE = (941, 1672)


def _scaled_point(x: float, y: float) -> tuple[int, int]:
    return round(x * CANVAS[0] / SOURCE_SIZE[0]), round(y * CANVAS[1] / SOURCE_SIZE[1])


def _scaled_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0 = _scaled_point(box[0], box[1])
    x1, y1 = _scaled_point(box[2], box[3])
    return x0, y0, x1, y1


def _resize_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA").resize(CANVAS, Image.Resampling.LANCZOS)


def _replace_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image:
    output = image.copy()
    output.putalpha(alpha)
    return output


def _vertical_mask(*, start: int, end: int, invert: bool = False) -> Image.Image:
    mask = Image.new("L", CANVAS, 0)
    pixels = mask.load()
    for y in range(CANVAS[1]):
        if y <= start:
            value = 0
        elif y >= end:
            value = 255
        else:
            value = round(255 * (y - start) / (end - start))
        if invert:
            value = 255 - value
        for x in range(CANVAS[0]):
            pixels[x, y] = value
    return mask


def _polygon_layer(image: Image.Image, polygons: list[list[tuple[int, int]]]) -> Image.Image:
    shape = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(shape)
    for polygon in polygons:
        draw.polygon(polygon, fill=255)
    shape = shape.filter(ImageFilter.GaussianBlur(1.2))
    return _replace_alpha(image, shape)


def _closed_eye_layer(closed: Image.Image) -> Image.Image:
    alpha = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(alpha)
    draw.ellipse(_scaled_box((348, 584, 449, 682)), fill=255)
    draw.ellipse(_scaled_box((493, 584, 606, 682)), fill=255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(5.0))
    return _replace_alpha(closed, alpha)


def _pose_head_layer(pose_subject: Image.Image) -> Image.Image:
    """Keep only the alternate head and upper neck for the Round 2 pose state.

    The source is a locally chroma-keyed full-body edit.  The fade is intentionally
    narrower than the Round 1 head/body overlap so the stable body remains the
    identity anchor while the actual head geometry can change.
    """

    pose_alpha = pose_subject.getchannel("A")
    head_mask = _vertical_mask(start=940, end=1050, invert=True)
    return _replace_alpha(pose_subject, ImageChops.multiply(pose_alpha, head_mask))


def _checkerboard(size: tuple[int, int], cell: int = 48) -> Image.Image:
    image = Image.new("RGBA", size, (236, 236, 231, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(55, 60, 64, 255))
    return image


def _labeled_panel(image: Image.Image, label: str) -> Image.Image:
    panel = image.resize((270, 480), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (270, 530), (24, 27, 29, 255))
    canvas.alpha_composite(panel, (0, 50))
    ImageDraw.Draw(canvas).text((14, 14), label, fill=(242, 238, 224, 255))
    return canvas


def prepare(
    source_root: Path,
    layer_root: Path,
    proof_root: Path,
    pose_source: Path | None = None,
    pose_layer_output: Path | None = None,
    pose_proof_output: Path | None = None,
) -> None:
    source_root = source_root.resolve(strict=True)
    layer_root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    master = _resize_rgba(source_root / "master.png")
    background = _resize_rgba(source_root / "background-clean.png")
    closed = _resize_rgba(source_root / "eyes-closed-source.png")
    subject = _resize_rgba(layer_root / "subject-cutout.png")

    subject_alpha = subject.getchannel("A")
    head_mask = _vertical_mask(start=1010, end=1110, invert=True)
    body_mask = _vertical_mask(start=960, end=1045)
    head = _replace_alpha(subject, ImageChops.multiply(subject_alpha, head_mask))
    body = _replace_alpha(subject, ImageChops.multiply(subject_alpha, body_mask))

    neck_mask = Image.new("L", CANVAS, 0)
    neck_draw = ImageDraw.Draw(neck_mask)
    neck_draw.ellipse(_scaled_box((372, 842, 576, 978)), fill=255)
    neck_mask = neck_mask.filter(ImageFilter.GaussianBlur(7.0))
    neck_cover = _replace_alpha(subject, ImageChops.multiply(subject_alpha, neck_mask))
    eyes_closed = _closed_eye_layer(closed)
    pose_head = None
    if pose_source is not None:
        pose_head = _pose_head_layer(_resize_rgba(pose_source))

    # 前景只从同源 master 的已有草叶取样；多边形贴合可识别的叶片，
    # 不使用方形贴片，避免位移时暴露背景块。
    left_polygons = [
        [_scaled_point(0, 1672), _scaled_point(0, 1260), _scaled_point(28, 1360), _scaled_point(58, 1672)],
        [_scaled_point(38, 1672), _scaled_point(91, 1402), _scaled_point(106, 1416), _scaled_point(82, 1672)],
        [_scaled_point(70, 1672), _scaled_point(155, 1434), _scaled_point(168, 1452), _scaled_point(118, 1672)],
    ]
    right_polygons = [
        [_scaled_point(941, 1672), _scaled_point(941, 1218), _scaled_point(904, 1338), _scaled_point(879, 1672)],
        [_scaled_point(908, 1672), _scaled_point(846, 1376), _scaled_point(830, 1390), _scaled_point(858, 1672)],
        [_scaled_point(862, 1672), _scaled_point(786, 1468), _scaled_point(774, 1482), _scaled_point(813, 1672)],
    ]
    foreground_left = _polygon_layer(master, left_polygons)
    foreground_right = _polygon_layer(master, right_polygons)

    master.save(layer_root / "master.png")
    background.save(layer_root / "background-clean.png")
    subject.save(layer_root / "subject-cutout.png")
    body.save(layer_root / "body.png")
    head.save(layer_root / "head.png")
    neck_cover.save(layer_root / "neck-cover.png")
    eyes_closed.save(layer_root / "eyes-closed.png")
    if pose_head is not None:
        pose_layer_output = pose_layer_output or layer_root / "head-nod.png"
        pose_layer_output.parent.mkdir(parents=True, exist_ok=True)
        pose_head.save(pose_layer_output)
    foreground_left.save(layer_root / "foreground-left.png")
    foreground_right.save(layer_root / "foreground-right.png")

    hero = background.copy()
    hero.alpha_composite(body)
    hero.alpha_composite(head)
    hero.alpha_composite(neck_cover)
    hero.alpha_composite(foreground_left)
    hero.alpha_composite(foreground_right)
    hero.save(proof_root / "hero-recomposition.png")

    pivot = _scaled_point(482, 938)
    rotated_head = head.rotate(
        -2.6,
        resample=Image.Resampling.BICUBIC,
        center=pivot,
        translate=(0, 6),
    )
    subject_peak = background.copy()
    subject_peak.alpha_composite(body)
    subject_peak.alpha_composite(rotated_head)
    subject_peak.alpha_composite(neck_cover)
    subject_peak.alpha_composite(foreground_left)
    subject_peak.alpha_composite(foreground_right)
    subject_peak.save(proof_root / "subject-peak.png")

    closed_proof = hero.copy()
    closed_proof.alpha_composite(eyes_closed)
    closed_proof.save(proof_root / "eyes-closed-proof.png")

    if pose_head is not None:
        nod_proof = background.copy()
        nod_proof.alpha_composite(body)
        nod_proof.alpha_composite(pose_head)
        nod_proof.alpha_composite(neck_cover)
        nod_proof.alpha_composite(foreground_left)
        nod_proof.alpha_composite(foreground_right)
        pose_proof_output = pose_proof_output or proof_root / "head-nod-proof.png"
        pose_proof_output.parent.mkdir(parents=True, exist_ok=True)
        nod_proof.save(pose_proof_output)

    for name, color in (("alpha-light", (241, 238, 224, 255)), ("alpha-dark", (18, 23, 28, 255))):
        base = Image.new("RGBA", CANVAS, color)
        base.alpha_composite(subject)
        base.save(proof_root / f"{name}.png")

    checker = _checkerboard(CANVAS)
    checker.alpha_composite(subject)
    panels = [
        _labeled_panel(master, "MASTER"),
        _labeled_panel(background, "CLEAN BACKGROUND"),
        _labeled_panel(hero, "STATIC RECOMPOSITION"),
        _labeled_panel(subject_peak, "HEAD PEAK"),
        _labeled_panel(closed_proof, "EYES CLOSED"),
        _labeled_panel(checker, "ALPHA CHECK"),
    ]
    sheet = Image.new("RGBA", (810, 1060), (12, 15, 17, 255))
    for index, panel in enumerate(panels):
        sheet.alpha_composite(panel, ((index % 3) * 270, (index // 3) * 530))
    sheet.save(proof_root / "contact-sheet.png")


if __name__ == "__main__":
    case_root = Path(
        "/Users/yuh/Desktop/项目/文本视音屏生成器/"
        "【包A】视频引擎包/成片/短视频V2样片/phase7-hyperframes-micro-motion/"
        "case-a-controlled"
    )
    round2_root = case_root.parent / "round2-reopen" / "case-a"
    prepare(
        case_root / "assets" / "source",
        case_root / "assets" / "layers",
        case_root / "proofs",
        round2_root / "assets" / "source" / "head-nod-subject.png",
        round2_root / "assets" / "layers" / "head-nod.png",
        round2_root / "proofs" / "head-nod-proof.png",
    )
