# Description: Unit tests for the static helpers exposed by UdaAccess.

import numpy as np
import pytest

uc = pytest.importorskip("uda_client_reader.uda_client_reader_python",
                         reason="uda_client_reader package required")

from iplotDataAccess.dataCommon import DataObj, DataType
from iplotDataAccess.udaAccess import UdaAccess, UdaParams


class TestConvertUdaTypes:

    def test_unknown_type_returns_none(self):
        assert UdaAccess.convert_uda_types(utype=None) is None
        assert UdaAccess.convert_uda_types(utype="WHATEVER") is None

    @pytest.mark.parametrize("utype_attr,expected", [
        ("RAW_TYPE_FLOAT", DataType.DA_TYPE_FLOAT),
        ("RAW_TYPE_DOUBLE", DataType.DA_TYPE_DOUBLE),
        ("RAW_TYPE_STRING", DataType.DA_TYPE_STRING),
        ("RAW_TYPE_LONG", DataType.DA_TYPE_LONG),
        ("RAW_TYPE_UNSIGNED_LONG", DataType.DA_TYPE_ULONG),
        ("RAW_TYPE_CHAR", DataType.DA_TYPE_CHAR),
        ("RAW_TYPE_UNSIGNED_CHAR", DataType.DA_TYPE_UCHAR),
        ("RAW_TYPE_SHORT", DataType.DA_TYPE_SHORT),
        ("RAW_TYPE_UNSIGNED_SHORT", DataType.DA_TYPE_USHORT),
        ("RAW_TYPE_INT", DataType.DA_TYPE_INT),
        ("RAW_TYPE_UNSIGNED_INT", DataType.DA_TYPE_UINT),
    ])
    def test_known_uda_types_map_to_data_type(self, utype_attr, expected):
        utype = getattr(uc, utype_attr, None)
        if utype is None:
            pytest.skip(f"uda_client_reader.{utype_attr} not available")
        assert UdaAccess.convert_uda_types(utype=utype) is expected


class TestConvertToNanos:

    def test_non_string_passthrough(self):
        assert UdaAccess.convert_to_nanos(12345) == 12345
        assert UdaAccess.convert_to_nanos(None) is None

    def test_string_without_t_or_dot_passthrough(self):
        assert UdaAccess.convert_to_nanos("1631513472231") == "1631513472231"

    def test_iso_string_is_converted_to_nanoseconds(self):
        out = UdaAccess.convert_to_nanos("2022-05-04T12:30:00.000")
        assert isinstance(out, str)
        assert int(out) > 1_000_000_000_000_000_000

    def test_invalid_iso_returns_minus_one(self):
        out = UdaAccess.convert_to_nanos("not-a-date.T.")
        assert out == -1


class TestUdaParamsContainer:

    def test_set_params_assigns_attributes(self):
        p = UdaParams()
        p.set_params("var", 1000, "raw", "0", "1", "shot/1", "absolute", False, "double")
        assert p.varname == "var"
        assert p.nbps == 1000
        assert p.decType == "raw"
        assert p.startT == "0"
        assert p.endT == "1"
        assert p.pulse == "shot/1"
        assert p.tsFormat == "absolute"
        assert p.extSamples is False
        assert p.retType == "double"


class TestLastValueBefore:
    """Extremities must hold a flat line over intervals that contain no samples of their own."""

    @staticmethod
    def _params(start_t, end_t, dec_type=None):
        p = UdaParams()
        p.set_params("FD", -1, dec_type, start_t, end_t, None, "absolute", True)
        return p

    def test_looks_back_to_startt_and_returns_last_sample(self, monkeypatch):
        access = UdaAccess("test", {})
        captured = {}

        def fake_fetch(query):
            captured["query"] = query
            dobj = DataObj()
            dobj.xdata = np.array([500.0])
            dobj.ydata = np.array([1.0])
            dobj.set_err(0, "OK")
            return dobj

        monkeypatch.setattr(access, "_UdaAccess__fetch_data_x", fake_fetch)
        query = "variable=FD,tsFormat=absolute,decSamples=-1,startTime=6000,endTime=7000,extSamples=True"
        held = access._UdaAccess__last_value_before(query, self._params(6000, 7000))

        assert held == 1.0
        # The look-back window is [archive start, startT] asking for a single closing sample.
        assert "startTime=0," in captured["query"]
        assert "endTime=6000" in captured["query"]
        assert "decSamples=1," in captured["query"]
        assert "decType=last" in captured["query"]
        assert "extSamples" not in captured["query"]

    def test_returns_none_when_no_earlier_sample(self, monkeypatch):
        access = UdaAccess("test", {})

        def fake_fetch(_query):
            dobj = DataObj()
            dobj.set_err(-3, "no data")
            return dobj

        monkeypatch.setattr(access, "_UdaAccess__fetch_data_x", fake_fetch)
        query = "variable=FD,tsFormat=absolute,decSamples=-1,startTime=100,endTime=200,extSamples=True"
        assert access._UdaAccess__last_value_before(query, self._params(100, 200)) is None


class TestParseVarsToDict:

    def test_without_limit_groups_on_first_dash_or_dot_only(self):
        lines = ['x:a-b', 'x:b-c', 'x:a-c', 'x:p.1', 'x:p.2', 'x:q_1', 'x:q_2']
        assert UdaAccess.parse_vars_to_dict(lines, 'x') == {
            'x:a': {'x:a-b': '', 'x:a-c': ''},
            'x:b-c': '',
            'x:p': {'x:p.1': '', 'x:p.2': ''},
            'x:q_1': '', 'x:q_2': '',
        }

    def test_without_limit_the_first_separator_wins(self):
        lines = ['x:a-b.1', 'x:a-b.2', 'x:p.1-a', 'x:p.2-a']
        assert UdaAccess.parse_vars_to_dict(lines, 'x') == {
            'x:a': {'x:a-b.1': '', 'x:a-b.2': ''},
            'x:p': {'x:p.1-a': '', 'x:p.2-a': ''},
        }

    def test_node_within_limit_keeps_the_dash_layout(self):
        lines = ['x:a-b', 'x:b-c', 'x:a-c', 'x:p.1', 'x:p.2']
        expected = UdaAccess.parse_vars_to_dict(lines, 'x')
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=5) == expected

    def test_large_node_splits_on_dash_dot_and_underscore(self):
        lines = ['x:a-1', 'x:a-2', 'x:b.1', 'x:b.2', 'x:c_1', 'x:c_2', 'x:d']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=2) == {
            'x:a': {'x:a-1': '', 'x:a-2': ''},
            'x:b': {'x:b.1': '', 'x:b.2': ''},
            'x:c': {'x:c_1': '', 'x:c_2': ''},
            'x:d': '',
        }

    def test_folder_above_limit_splits_again_on_its_next_segment(self):
        lines = ['x:a_b_1', 'x:a_b_2', 'x:a_c.1', 'x:a_c.2', 'x:a_d']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=2) == {
            'x:a': {
                'x:a_b': {'x:a_b_1': '', 'x:a_b_2': ''},
                'x:a_c': {'x:a_c.1': '', 'x:a_c.2': ''},
                'x:a_d': '',
            },
        }

    def test_splitting_stops_when_names_have_no_further_separator(self):
        lines = ['x:a_1', 'x:a_2', 'x:a_3']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=1) == {
            'x:a': {'x:a_1': '', 'x:a_2': '', 'x:a_3': ''},
        }

    def test_first_segment_is_never_empty(self):
        lines = ['x:-a-1', 'x:-a-2', 'x:-b']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=1) == {
            'x:-a': {'x:-a-1': '', 'x:-a-2': ''},
            'x:-b': '',
        }

    def test_variable_named_like_a_folder_sits_inside_it(self):
        lines = ['x:a', 'x:a_1', 'x:a_2']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=2) == {
            'x:a': {'x:a': '', 'x:a_1': '', 'x:a_2': ''},
        }

    def test_duplicated_names_are_listed_once(self):
        lines = ['x:a-1', 'x:a-1', 'x:a-2']
        assert UdaAccess.parse_vars_to_dict(lines, 'x', group_limit=1) == {
            'x:a': {'x:a-1': '', 'x:a-2': ''},
        }


class TestVariableGroupLimitConfig:

    def _var_dict(self, config, monkeypatch):
        # Underscore names: only the configured grouping splits on them.
        access = UdaAccess("test", config)
        monkeypatch.setattr(access, "get_var_list", lambda pattern, field=None: ['x:a_1', 'x:a_2', 'x:b'])
        return access.get_var_dict(pattern='x:.*', path='x')

    def test_grouping_is_off_when_the_key_is_absent(self):
        assert UdaAccess("test", {}).variable_group_limit is None

    def test_configured_limit_drives_the_split(self, monkeypatch):
        assert self._var_dict({"variable_group_limit": 2}, monkeypatch) == {
            'x:a': {'x:a_1': '', 'x:a_2': ''},
            'x:b': '',
        }

    def test_node_is_left_flat_when_the_key_is_absent(self, monkeypatch):
        assert self._var_dict({}, monkeypatch) == {'x:a_1': '', 'x:a_2': '', 'x:b': ''}

    def test_null_limit_keeps_every_node_flat(self, monkeypatch):
        assert self._var_dict({"variable_group_limit": None}, monkeypatch) == {'x:a_1': '', 'x:a_2': '', 'x:b': ''}


class TestParseSearchToDict:

    def test_plain_names_are_nested_by_node_segment(self):
        assert UdaAccess.parse_search_to_dict(['CTRL-CIS-MCTB:ALV_X']) == {
            'CTRL': {'CIS': {'MCTB': {'CTRL-CIS-MCTB:ALV_X': ''}}},
        }

    def test_consecutive_separators_do_not_break_the_search(self):
        """A node such as MAG-PFCS-SYSM-- used to raise IndexError, which the
        search swallows and leaves the user with an empty tree."""
        assert UdaAccess.parse_search_to_dict(['MAG-PFCS-SYSM--:CUCUB_Monitor-CUBHLTS']) == {
            'MAG': {'PFCS': {'SYSM': {
                'MAG-PFCS-SYSM--:CUCUB_Monitor': {'MAG-PFCS-SYSM--:CUCUB_Monitor-CUBHLTS': ''},
            }}},
        }

    def test_empty_segments_never_become_folders(self):
        out = UdaAccess.parse_search_to_dict(['MAG-PFCS-SYSM--:VAR'])
        assert '' not in out['MAG']['PFCS']['SYSM']

    def test_one_broken_name_does_not_hide_the_others(self):
        out = UdaAccess.parse_search_to_dict(['MAG-PFCS-SYSM--:VAR', 'MAG-PFCS-SYSM:OK'])
        assert set(out['MAG']['PFCS']['SYSM']) == {'MAG-PFCS-SYSM--:VAR', 'MAG-PFCS-SYSM:OK'}
