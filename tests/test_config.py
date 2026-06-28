"""Tests for configuration parsing (env-friendly behaviours)."""

from wrc_pipeline.config import Settings


def test_body_keys_parses_comma_string():
    s = Settings(bodies="labour_court, equality_tribunal ,workplace_relations_commission")
    assert s.body_keys() == [
        "labour_court", "equality_tribunal", "workplace_relations_commission",
    ]


def test_body_keys_empty_means_all():
    assert Settings(bodies="").body_keys() == []


def test_search_url_is_composed():
    s = Settings(base_url="https://example.ie", search_path="/en/search/")
    assert s.search_url == "https://example.ie/en/search/"


def test_partition_size_is_validated():
    import pytest
    from pydantic import ValidationError

    Settings(partition_size="weekly")  # valid
    with pytest.raises(ValidationError):
        Settings(partition_size="fortnightly")  # invalid -> rejected at load
