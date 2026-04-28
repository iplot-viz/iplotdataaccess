# Description: Unit tests for the pure string/parse helpers in imasUtils.

import pytest

# Pure helpers still require the imas module to import the file (top-level imports).
pytest.importorskip("imas", reason="imas/imaspy package required")

from iplotDataAccess.imasUtils import (
    parse_idspath,
    parse_slice_from_string,
    parse_string_to_dict,
)


class TestParseIDSPath:

    def test_only_ids_name(self):
        assert parse_idspath("core_profiles") == {
            "occurrence": None,
            "ids_name": "core_profiles",
            "ids_path": None,
        }

    def test_ids_name_with_path(self):
        assert parse_idspath("core_profiles/te/data") == {
            "occurrence": None,
            "ids_name": "core_profiles",
            "ids_path": "te/data",
        }

    def test_ids_name_with_occurrence_only(self):
        assert parse_idspath("core_profiles:0") == {
            "occurrence": 0,
            "ids_name": "core_profiles",
            "ids_path": None,
        }

    def test_ids_name_with_occurrence_and_path(self):
        assert parse_idspath("core_profiles:0/te/data") == {
            "occurrence": 0,
            "ids_name": "core_profiles",
            "ids_path": "te/data",
        }

    def test_non_numeric_after_colon_keeps_occurrence_none(self):
        assert parse_idspath("core_profiles:abc/te") == {
            "occurrence": None,
            "ids_name": "core_profiles",
            "ids_path": "te",
        }


class TestParseSliceFromString:

    def test_full_slice_with_step(self):
        assert parse_slice_from_string("foo[1:10:2]") == slice(1, 10, 2)

    def test_open_start_and_end(self):
        assert parse_slice_from_string("foo[:5]") == slice(None, 5, None)

    def test_open_end(self):
        assert parse_slice_from_string("foo[3:]") == slice(3, None, None)

    def test_step_only(self):
        assert parse_slice_from_string("foo[::2]") == slice(None, None, 2)

    def test_negative_indices(self):
        assert parse_slice_from_string("foo[-3:-1]") == slice(-3, -1, None)

    def test_no_match_returns_empty_slice(self):
        assert parse_slice_from_string("foo") == slice(None, None, None)


class TestParseStringToDict:

    def test_simple_pairs(self):
        assert parse_string_to_dict("a=1,b=2") == {"a": "1", "b": "2"}

    def test_value_with_equals_sign_is_kept_as_value(self):
        assert parse_string_to_dict("formula=x=y+1") == {"formula": "x=y+1"}

    def test_single_pair(self):
        assert parse_string_to_dict("only=one") == {"only": "one"}
