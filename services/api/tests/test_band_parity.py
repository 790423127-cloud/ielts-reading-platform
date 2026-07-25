from __future__ import annotations

import pytest

from app.domain.band import (
    attach_band_estimate,
    build_band_estimate,
    estimate_gt_reading_band,
    is_complete_gt_reading_result,
)


@pytest.mark.parametrize(
    ("raw", "band"),
    [
        (40, 9.0), (39, 8.5), (38, 8.0), (37, 7.5), (36, 7.0),
        (35, 7.0), (34, 6.5), (33, 6.5), (32, 6.0), (31, 6.0),
        (30, 6.0), (29, 5.5), (27, 5.5), (26, 5.0), (23, 5.0),
        (22, 4.5), (19, 4.5), (18, 4.0), (15, 4.0), (14, 3.5),
        (12, 3.5), (9, 3.0), (6, 2.5), (5, 2.0), (3, 1.5),
        (1, 1.0), (0, 0.0), (-3, 0.0), (99, 9.0),
    ],
)
def test_legacy_indicative_thresholds(raw: int, band: float) -> None:
    assert estimate_gt_reading_band(raw) == band


def test_complete_40_question_result_gets_same_estimate() -> None:
    result = {"score": 20, "total": 40}
    assert is_complete_gt_reading_result(result)
    attach_band_estimate(result)
    estimate = result["band_estimate"]
    assert estimate["eligible"] is True
    assert estimate["estimated_band"] == 4.5
    assert estimate["next_band"] == 5.0
    assert estimate["next_band_minimum_score"] == 23
    assert estimate["questions_to_next_band"] == 3
    assert estimate["official_anchor_points"] == {
        "4.0": 15,
        "5.0": 23,
        "6.0": 30,
        "7.0": 35,
    }
    assert estimate["is_official_result"] is False
    assert "不是官方成绩" in estimate["notice_zh"]


@pytest.mark.parametrize("total", [1, 8, 13, 39, 41])
def test_non_40_question_result_never_gets_band(total: int) -> None:
    result = {"score": min(total, 7), "total": total}
    attach_band_estimate(result)
    assert result["band_estimate"]["eligible"] is False
    assert "estimated_gt_reading_band" not in result


def test_non_40_scale_is_explicitly_ineligible() -> None:
    estimate = build_band_estimate(7, total=13, eligible=True)
    assert estimate["eligible"] is False
    assert estimate["raw_score"] == 7
    assert estimate["out_of"] == 13
