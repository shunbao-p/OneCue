#!/usr/bin/env python3
"""计划 04 视觉评分表的最小校验与汇总工具。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CASES = ("portrait", "architecture", "landscape")
METRICS = (
    "subject_identity", "edges", "background_geometry",
    "motion", "temporal_stability", "benefit",
)


def validate_scorecard(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("scorecard schema_version 必须为 1")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries 必须是数组")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entries[{index}] 必须是对象")
        if entry.get("case") not in CASES:
            raise ValueError(f"entries[{index}].case 非法")
        scores = entry.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(METRICS):
            raise ValueError(f"entries[{index}].scores 指标不完整")
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3 for value in scores.values()):
            raise ValueError(f"entries[{index}].scores 必须为 0–3 整数")
    return payload


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_scorecard(payload)
    entries = []
    for entry in validated["entries"]:
        entries.append({
            "provider": entry.get("provider"),
            "case": entry["case"],
            "total": sum(entry["scores"].values()),
            "hard_failures": list(entry.get("hard_failures", [])),
        })
    return {"entry_count": len(entries), "entries": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    args = parser.parse_args()
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    print(json.dumps(summarize(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
