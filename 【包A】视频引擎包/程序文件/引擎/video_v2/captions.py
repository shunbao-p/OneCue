"""V2 句群字幕的纯函数实现。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence


CAPTION_IMPLEMENTATION_VERSION = "caption-v2.1"
DEFAULT_STYLE_PRESET = "default_lower_third"
SUPPORTED_CAPTION_MODES = ("speech", "custom", "none")
_SENTENCE_END = frozenset("。！？；!?…;")
_SOFT_BREAK = frozenset("，、：,: ")


@dataclass(frozen=True)
class CaptionCard:
    """一张可见字幕卡；时间均为镜头内秒数。"""

    text: str
    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    def to_dict(self) -> dict[str, float | str]:
        return {
            "text": self.text,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
        }


def select_caption_text(
    captions_enabled: bool,
    caption_mode: str,
    speech_text: str,
    custom_text: str | None,
) -> str | None:
    """依冻结的项目总开关与镜头模式选择可见文本。"""

    if caption_mode not in SUPPORTED_CAPTION_MODES:
        raise ValueError(f"未知字幕模式：{caption_mode}")
    if not captions_enabled or caption_mode == "none":
        return None
    source = speech_text if caption_mode == "speech" else custom_text
    if source is None:
        return None
    normalized = _normalize_text(source)
    return normalized or None


def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("字幕文本必须是字符串")
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def _normalize_card_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("字幕卡文本必须是字符串")
    logical_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line for line in (_normalize_text(value) for value in logical_lines) if line)


def _hard_split(text: str, maximum: int) -> list[str]:
    """从软标点处尽量切分过长句群，无标点时才硬切。"""

    pieces: list[str] = []
    remainder = text
    while len(remainder) > maximum:
        lower = max(1, maximum // 2)
        candidates = [
            index + 1
            for index, character in enumerate(remainder[:maximum])
            if character in _SOFT_BREAK and index + 1 >= lower
        ]
        split_at = candidates[-1] if candidates else maximum
        pieces.append(remainder[:split_at].strip())
        remainder = remainder[split_at:].strip()
    if remainder:
        pieces.append(remainder)
    return pieces


def split_caption_cards(text: str, max_chars: int = 32) -> tuple[str, ...]:
    """优先按句末标点分段，再将句群组合为不超过上限的卡片。"""

    if max_chars < 2:
        raise ValueError("max_chars 必须至少为 2")
    compact = _normalize_text(text)
    if not compact:
        return ()

    sentences: list[str] = []
    start = 0
    for index, character in enumerate(compact):
        if character in _SENTENCE_END:
            sentence = compact[start : index + 1].strip()
            if sentence:
                sentences.extend(_hard_split(sentence, max_chars))
            start = index + 1
    tail = compact[start:].strip()
    if tail:
        sentences.extend(_hard_split(tail, max_chars))

    cards: list[str] = []
    pending = ""
    for sentence in sentences:
        candidate = pending + sentence
        if pending and len(candidate) > max_chars:
            cards.append(pending)
            pending = sentence
        else:
            pending = candidate
    if pending:
        cards.append(pending)
    return tuple(cards)


def wrap_caption_lines(text: str, max_line_chars: int = 16) -> str:
    """插入最多一个真换行，两行均不超过约定上限。"""

    if max_line_chars < 1:
        raise ValueError("max_line_chars 必须为正整数")
    compact = _normalize_text(text)
    if len(compact) <= max_line_chars:
        return compact
    if len(compact) > 2 * max_line_chars:
        raise ValueError("单张字幕超过两行容量")

    minimum = max(1, len(compact) - max_line_chars)
    maximum = min(max_line_chars, len(compact) - 1)
    candidates = [
        index
        for index in range(minimum, maximum + 1)
        if compact[index - 1] in (_SENTENCE_END | _SOFT_BREAK)
    ]
    midpoint = len(compact) / 2
    split_at = min(candidates, key=lambda value: abs(value - midpoint)) if candidates else int(round(midpoint))
    split_at = min(maximum, max(minimum, split_at))
    return compact[:split_at] + "\n" + compact[split_at:]


def _merge_short_cards(cards: Sequence[str], duration_sec: float, minimum_sec: float) -> tuple[str, ...]:
    if not cards:
        return ()
    maximum_count = max(1, int(math.floor((duration_sec + 1e-9) / minimum_sec)))
    merged = list(cards)
    while len(merged) > maximum_count:
        pair_index = min(
            range(len(merged) - 1),
            key=lambda index: len(merged[index]) + len(merged[index + 1]),
        )
        candidate = merged[pair_index] + merged[pair_index + 1]
        if len(candidate) <= 32:
            merged[pair_index : pair_index + 2] = [candidate]
        else:
            # 时间极短且文本很长时，以卡片容量优先；后续分配仍覆盖全区间。
            break
    return tuple(merged)


def allocate_caption_times(
    cards: Sequence[str],
    start_sec: float,
    end_sec: float,
    *,
    min_duration_sec: float = 0.6,
) -> tuple[CaptionCard, ...]:
    """按可见字符数比例分配字幕时间，严格覆盖有效语音区间。"""

    values = (float(start_sec), float(end_sec), float(min_duration_sec))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("字幕时间必须为有限数")
    if start_sec < 0 or end_sec <= start_sec or min_duration_sec <= 0:
        raise ValueError("字幕时间区间不合法")
    normalized_values = tuple(_normalize_card_text(card) for card in cards)
    normalized = tuple(card for card in normalized_values if card)
    if not normalized:
        return ()
    normalized = _merge_short_cards(normalized, end_sec - start_sec, min_duration_sec)
    weights = [max(1, len(re.sub(r"\s+", "", card))) for card in normalized]
    total_weight = sum(weights)
    result: list[CaptionCard] = []
    cursor = float(start_sec)
    duration = float(end_sec - start_sec)
    cumulative = 0
    for index, (card, weight) in enumerate(zip(normalized, weights)):
        cumulative += weight
        card_end = float(end_sec) if index == len(normalized) - 1 else float(start_sec) + duration * cumulative / total_weight
        result.append(CaptionCard(card, cursor, card_end))
        cursor = card_end
    return tuple(result)


def build_caption_cards(
    text: str,
    start_sec: float,
    end_sec: float,
    *,
    max_chars: int = 32,
    max_line_chars: int = 16,
    min_duration_sec: float = 0.6,
) -> tuple[CaptionCard, ...]:
    raw_cards = split_caption_cards(text, max_chars=max_chars)
    allocated = allocate_caption_times(
        raw_cards, start_sec, end_sec, min_duration_sec=min_duration_sec
    )
    return tuple(
        CaptionCard(
            wrap_caption_lines(card.text, max_line_chars=max_line_chars),
            card.start_sec,
            card.end_sec,
        )
        for card in allocated
    )


def ass_time(seconds: float) -> str:
    if not math.isfinite(float(seconds)):
        raise ValueError("ASS 时间必须为有限数")
    centiseconds = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def escape_ass(text: str) -> str:
    """将任务文本安全化，不允许花括号或反斜杠注入 ASS override tag。"""

    if not isinstance(text, str):
        raise TypeError("ASS 文本必须是字符串")
    escaped = text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    return escaped.replace("\r\n", r"\N").replace("\n", r"\N").replace("\r", r"\N")


def build_ass(
    cards: Iterable[CaptionCard],
    *,
    width: int = 1080,
    height: int = 1920,
    style_preset: str = DEFAULT_STYLE_PRESET,
    title: str = "Short Video V2 Captions",
) -> str:
    """生成只包含固定下三分之一样式的 ASS，不消费任务提供的脚本。"""

    if style_preset != DEFAULT_STYLE_PRESET:
        raise ValueError(f"未知字幕样式：{style_preset}")
    if width <= 0 or height <= 0:
        raise ValueError("ASS 画布尺寸必须为正整数")
    safe_title = _normalize_text(title)
    if not safe_title:
        raise ValueError("ASS 标题不得为空")
    font_size = max(18, int(round(height * 62 / 1920)))
    margin_horizontal = max(24, int(round(width * 110 / 1080)))
    margin_vertical = max(40, int(round(height * 235 / 1920)))
    lines = [
        "[Script Info]",
        f"Title: {safe_title}",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,SimHei,{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,2,{margin_horizontal},{margin_horizontal},{margin_vertical},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    previous_end = 0.0
    for card in cards:
        if card.start_sec < 0 or card.end_sec <= card.start_sec or card.start_sec + 1e-9 < previous_end:
            raise ValueError("字幕卡时序不合法")
        lines.append(
            f"Dialogue: 0,{ass_time(card.start_sec)},{ass_time(card.end_sec)},Default,,0,0,0,,{escape_ass(card.text)}"
        )
        previous_end = card.end_sec
    return "\n".join(lines) + "\n"


# 兼容计划 01 命名，便于渲染层窄接入。
render_ass = build_ass
