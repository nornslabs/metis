"""The committed case set, and what the loader refuses."""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, Any

import pytest

from evals.cases import BAND_TOTALS, CASES_PATH, CaseFileError, load_cases
from metis.modules.scoring import ScoreBand

if TYPE_CHECKING:
    from pathlib import Path

MIN_CASES, MAX_CASES = 12, 15


def _valid() -> dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8").splitlines()[0])


def _file(tmp_path: Path, *rows: dict[str, Any] | str) -> Path:
    path = tmp_path / "cases.jsonl"
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_committed_set_has_twelve_to_fifteen_cases() -> None:
    assert MIN_CASES <= len(load_cases()) <= MAX_CASES


def test_the_committed_set_covers_every_band_with_a_spread_of_cases() -> None:
    bands = Counter(c.expect.band for c in load_cases())

    assert set(bands) == set(ScoreBand)
    assert all(count >= 3 for count in bands.values())


def test_the_committed_set_has_thin_research_and_a_case_with_no_snapshot() -> None:
    cases = load_cases()

    assert any(c.snapshot is None for c in cases)
    assert any(c.snapshot and any(i.confidence <= 0.35 for i in c.snapshot.items) for c in cases)


def test_every_committed_total_range_sits_inside_its_band() -> None:
    for case in load_cases():
        if case.expect.total is not None:
            low, high = BAND_TOTALS[case.expect.band]
            assert low <= case.expect.total[0] <= case.expect.total[1] <= high


def test_a_line_that_is_not_json_is_refused_with_its_line_number(tmp_path: Path) -> None:
    path = _file(tmp_path, _valid(), "{not json")

    with pytest.raises(CaseFileError, match=r"cases.jsonl:2: not JSON"):
        load_cases(path)


def test_an_unknown_band_is_refused(tmp_path: Path) -> None:
    row = _valid()
    row["expect"]["band"] = "excellent"

    with pytest.raises(CaseFileError, match=r"cases.jsonl:1: expect.band"):
        load_cases(_file(tmp_path, row))


def test_an_unknown_parameter_is_refused(tmp_path: Path) -> None:
    row = _valid()
    row["expect"]["params"] = {"charisma": [1, 2]}

    with pytest.raises(CaseFileError, match=r"cases.jsonl:1"):
        load_cases(_file(tmp_path, row))


@pytest.mark.parametrize("bounds", [[3, 11], [6, 4], [-1, 3]])
def test_a_range_outside_zero_to_ten_or_reversed_is_refused(
    tmp_path: Path, bounds: list[int]
) -> None:
    row = _valid()
    row["expect"]["params"] = {"timing": bounds}

    with pytest.raises(CaseFileError, match=r"cases.jsonl:1"):
        load_cases(_file(tmp_path, row))


def test_a_total_range_outside_the_expected_band_is_refused(tmp_path: Path) -> None:
    row = _valid()
    row["expect"]["band"] = "advise"
    row["expect"]["total"] = [60, 80]

    with pytest.raises(CaseFileError, match="outside the advise band"):
        load_cases(_file(tmp_path, row))


def test_a_sourced_item_without_a_url_is_refused(tmp_path: Path) -> None:
    row = _valid()
    row["snapshot"]["items"][0]["url"] = None

    with pytest.raises(CaseFileError, match="needs a url"):
        load_cases(_file(tmp_path, row))


def test_a_repeated_case_id_is_refused(tmp_path: Path) -> None:
    row = _valid()

    with pytest.raises(CaseFileError, match=r"cases.jsonl:2: duplicate case id"):
        load_cases(_file(tmp_path, row, {**row, "title": "Another title"}))


def test_a_file_without_cases_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CaseFileError, match="no cases"):
        load_cases(_file(tmp_path))
