"""Tests for date-range partitioning."""

from datetime import date

import pytest

from wrc_pipeline.partitioning import iter_partitions


def test_monthly_matches_assignment_example():
    # "monthly partitions between 01-01-2024 and 01-01-2025" -> 12 windows.
    parts = iter_partitions(date(2024, 1, 1), date(2025, 1, 1), "monthly")
    assert len(parts) == 12
    assert parts[0].label == "2024-01"
    assert parts[0].start == date(2024, 1, 1)
    assert parts[0].end == date(2024, 1, 31)
    assert parts[1].end == date(2024, 2, 29)  # 2024 is a leap year
    assert parts[-1].label == "2024-12"
    assert parts[-1].end == date(2024, 12, 31)


def test_site_date_format():
    parts = iter_partitions(date(2024, 1, 1), date(2024, 2, 1), "monthly")
    assert parts[0].from_param == "01/01/2024"
    assert parts[0].to_param == "31/01/2024"


def test_partial_first_and_last_windows_are_clamped():
    parts = iter_partitions(date(2024, 1, 15), date(2024, 3, 10), "monthly")
    assert parts[0].start == date(2024, 1, 15)  # clamped to requested start
    assert parts[0].end == date(2024, 1, 31)
    assert parts[-1].end == date(2024, 3, 9)    # end is exclusive


def test_weekly_and_yearly_sizes():
    weekly = iter_partitions(date(2024, 1, 1), date(2024, 1, 22), "weekly")
    assert len(weekly) == 3
    yearly = iter_partitions(date(2022, 1, 1), date(2024, 1, 1), "yearly")
    assert [p.label for p in yearly] == ["2022", "2023"]


def test_inverted_range_raises():
    with pytest.raises(ValueError):
        iter_partitions(date(2024, 2, 1), date(2024, 1, 1), "monthly")


def test_unknown_size_raises():
    with pytest.raises(ValueError):
        iter_partitions(date(2024, 1, 1), date(2024, 2, 1), "fortnightly")
