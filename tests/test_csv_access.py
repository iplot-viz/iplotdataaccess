# Description: Unit tests for the CSV data source backend.

import os

import pytest

from iplotDataAccess.csvAccess import CsvAccess


@pytest.fixture
def csv_access(temp_csv_root):
    src = CsvAccess("csv_test", {"path": str(temp_csv_root).replace(os.sep, "/")})
    assert src.connect() is True
    return src


class TestConnectAndIsConnected:

    def test_connect_returns_true_for_existing_folder(self, temp_csv_root):
        src = CsvAccess("csv_test", {"path": str(temp_csv_root)})
        assert src.connect() is True
        assert src.is_connected() is True

    def test_connect_returns_false_for_missing_folder(self, tmp_path):
        src = CsvAccess("csv_test", {"path": str(tmp_path / "missing")})
        assert src.connect() is False


class TestTransformPulseToFilePath:

    def test_translates_pulse_to_csv_path(self, csv_access, temp_csv_root):
        path = csv_access.transform_pulse_to_file_path("ITER:COMM/111")
        expected = f"{str(temp_csv_root).replace(os.sep, '/')}{os.sep}COMM{os.sep}data_111.csv"
        assert path == expected


class TestGetData:

    def test_get_data_returns_full_series(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="VAR_A")
        assert list(d.xdata) == [0.0, 1.0, 2.0, 3.0]
        assert list(d.ydata) == [1.0, 2.0, 3.0, 4.0]
        assert d.xunit == "s"
        assert d.yunit == "V"

    def test_get_data_with_tsS_filters_start(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="VAR_A", tsS=2.0)
        assert list(d.xdata) == [2.0, 3.0]
        assert list(d.ydata) == [3.0, 4.0]

    def test_get_data_with_tsE_filters_end(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="VAR_A", tsE=1.0)
        assert list(d.xdata) == [0.0, 1.0]

    def test_get_data_with_both_bounds(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="VAR_A", tsS=1.0, tsE=2.0)
        assert list(d.xdata) == [1.0, 2.0]

    def test_get_data_no_match_returns_error(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="MISSING_VAR")
        assert d.errcode == -1
        assert "No columns found" in d.errdesc

    def test_get_data_multiple_match_returns_error(self, csv_access):
        d = csv_access.get_data(pulse="ITER:COMM/111", varname="VAR_")
        assert d.errcode == -1
        assert "Multiple columns" in d.errdesc


class TestGetPulsesDF:

    def test_lists_all_csv_files_recursively(self, csv_access):
        df = csv_access.get_pulses_df()
        ids = sorted(df["pulseId"].tolist())
        assert any("COMM/111" in v for v in ids)
        assert any("COMM/112" in v for v in ids)
        assert any("EXP/200" in v for v in ids)
        assert all(s == "completed" for s in df["Status"])

    def test_pattern_filters_results(self, csv_access):
        df = csv_access.get_pulses_df(pattern=".*COMM/111.*")
        assert len(df) == 1
        assert "COMM/111" in df["pulseId"].iloc[0]

    def test_search_pulses_df_delegates_to_pattern(self, csv_access):
        df = csv_access.search_pulses_df(".*EXP.*")
        assert len(df) == 1


class TestGetVarList:

    def test_lists_unique_variable_names(self, csv_access):
        variables = csv_access.get_var_list()
        assert "VAR_A" in variables
        assert "VAR_B" in variables
        assert "TEMP" in variables

    def test_filter_by_pattern(self, csv_access):
        variables = csv_access.get_var_list(patt="VAR_.*")
        assert "TEMP" not in variables
        assert "VAR_A" in variables


class TestNonCsvFilesAreIgnored:

    def test_non_csv_files_are_skipped_in_pulses_walk(self, csv_access):
        df = csv_access.get_pulses_df()
        assert all(".txt" not in v and ".DS_Store" not in v for v in df["pulseId"])

    def test_non_csv_files_are_skipped_in_var_list_walk(self, csv_access):
        variables = csv_access.get_var_list()
        assert "not" not in variables
        assert "metadata" not in variables


class TestCbsAndVarDict:

    def test_get_cbs_dict_builds_nested_structure(self, csv_access):
        d = csv_access.get_cbs_dict()
        assert isinstance(d, dict)
        assert len(d) > 0

    def test_get_var_dict_alias_returns_cbs_dict(self, csv_access):
        assert csv_access.get_var_dict() == csv_access.get_cbs_dict()


class TestMiscMethods:

    def test_clear_cache_is_noop(self, csv_access):
        assert csv_access.clear_cache() is None

    def test_get_envelope_returns_none(self, csv_access):
        assert csv_access.get_envelope() is None

    def test_get_pulse_info_returns_none(self, csv_access):
        assert csv_access.get_pulse_info(pulse="x", run="0") is None
