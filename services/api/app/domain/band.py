from __future__ import annotations

from typing import Any

VERSION = "2.1.3"
SOURCE_NAME = "IELTS scoring in detail"
SOURCE_URL = "https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail"

OFFICIAL_GT_READING_ANCHORS: dict[float, int] = {
    4.0: 15,
    5.0: 23,
    6.0: 30,
    7.0: 35,
}

# Minimum raw mark required for each indicative band, ordered high to low.
INDICATIVE_GT_READING_THRESHOLDS: tuple[tuple[int, float], ...] = (
    (40, 9.0),
    (39, 8.5),
    (38, 8.0),
    (37, 7.5),
    (35, 7.0),
    (33, 6.5),
    (30, 6.0),
    (27, 5.5),
    (23, 5.0),
    (19, 4.5),
    (15, 4.0),
    (12, 3.5),
    (9, 3.0),
    (6, 2.5),
    (5, 2.0),
    (3, 1.5),
    (1, 1.0),
    (0, 0.0),
)


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def estimate_gt_reading_band(raw_score: int) -> float:
    """Convert a 0–40 raw mark to the legacy indicative GT Reading band."""
    score = max(0, min(40, _integer(raw_score)))
    for minimum, band in INDICATIVE_GT_READING_THRESHOLDS:
        if score >= minimum:
            return band
    return 0.0


def minimum_score_for_band(band: float) -> int | None:
    target = float(band)
    for minimum, candidate in INDICATIVE_GT_READING_THRESHOLDS:
        if candidate == target:
            return minimum
    return None


def is_complete_gt_reading_result(result: dict[str, Any]) -> bool:
    return _integer(result.get("total")) == 40


def build_band_estimate(
    raw_score: int,
    *,
    total: int = 40,
    eligible: bool = True,
) -> dict[str, Any]:
    total_value = _integer(total, 40)
    score = max(0, min(total_value, _integer(raw_score)))
    if not eligible or total_value != 40:
        return {
            "eligible": False,
            "raw_score": score,
            "out_of": total_value,
            "reason": "Band estimation is only shown for a 40-question IELTS General Training Reading practice result.",
            "reason_zh": "预计 Band 只适用于完成 40 道题的 IELTS General Training Reading 练习结果。",
            "version": VERSION,
        }

    band = estimate_gt_reading_band(score)
    next_band = round(band + 0.5, 1) if band < 9.0 else None
    next_minimum = minimum_score_for_band(next_band) if next_band is not None else None
    questions_to_next = max(0, next_minimum - score) if next_minimum is not None else 0
    return {
        "eligible": True,
        "raw_score": score,
        "out_of": 40,
        "estimated_band": band,
        "display_band": f"{band:.1f}",
        "next_band": next_band,
        "next_band_minimum_score": next_minimum,
        "questions_to_next_band": questions_to_next,
        "scale": "IELTS General Training Reading",
        "method": "official_anchors_with_indicative_half_bands_v1",
        "official_anchor_points": {
            f"{anchor:.1f}": mark
            for anchor, mark in OFFICIAL_GT_READING_ANCHORS.items()
        },
        "is_official_result": False,
        "notice": (
            "Estimated practice band only. IELTS states that the exact number of "
            "marks needed can vary slightly between test versions."
        ),
        "notice_zh": "这是练习用预计分，不是官方成绩；IELTS 官方说明不同试卷的精确换算可能略有变化。",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "version": VERSION,
    }


def attach_band_estimate(result: dict[str, Any]) -> dict[str, Any]:
    result["band_estimate"] = build_band_estimate(
        _integer(result.get("score")),
        total=_integer(result.get("total")),
        eligible=is_complete_gt_reading_result(result),
    )
    if result["band_estimate"].get("eligible"):
        result["estimated_gt_reading_band"] = result["band_estimate"]["estimated_band"]
    else:
        result.pop("estimated_gt_reading_band", None)
    return result
