# Description: Unit tests for the static helpers exposed by UdaAccess.

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

uc = pytest.importorskip("uda_client_reader.uda_client_reader_python",
                         reason="uda_client_reader package required")

from iplotDataAccess import udaAccess
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
        assert p.fallbackNbps is None

    @pytest.mark.parametrize("nbps,fallback,expected", [
        (-1, 1920, "-1|1920"),
        (-1, None, "-1"),
        (-1, 0, "-1"),
        (1000, 1920, "1000"),
        (1, 1920, "1"),
    ])
    def test_dec_samples_falls_back_only_when_every_sample_is_asked_for(self, nbps, fallback, expected):
        p = UdaParams()
        p.set_params("var", nbps, None, "0", "1", None, "absolute", False, None, fallback)
        assert p.decSamples == expected


class TestDecSamplesFallback:
    """An interval with more samples than UDA sends in one reply comes back decimated, not as an error."""

    PULSE = "ITER:CAT/5"

    @staticmethod
    def _query(access, **request):
        access.connected = True
        return access.get_data_i(access.get_uda_params(varname="V", **request))

    def test_time_window(self):
        query = self._query(UdaAccess("test", {}), nbp=-1, fallback_nbp=1920, tsS="100", tsE="200")
        assert "decSamples=-1|1920,startTime=100,endTime=200" in query

    @pytest.mark.parametrize("ends_in,ts_e", [
        pytest.param(3600, None, id="ongoing"),
        pytest.param(-3600, None, id="completed"),
        pytest.param(-3600, "10", id="completed-up-to-a-time"),
    ])
    def test_pulse(self, ends_in, ts_e):
        access = UdaAccess("test", {})
        now = time.time_ns()
        access.pulses_cache[self.PULSE] = SimpleNamespace(timeFrom=now - 7200 * 10**9,
                                                          timeTo=now + ends_in * 10**9)
        query = self._query(access, nbp=-1, fallback_nbp=1920, pulse=self.PULSE, tsS="0", tsE=ts_e,
                            tsFormat="relative")
        assert f"decSamples=-1|1920,pulse={self.PULSE}," in query

    def test_without_fallback_every_sample_is_asked_for(self):
        query = self._query(UdaAccess("test", {}), nbp=-1, tsS="100", tsE="200")
        assert "decSamples=-1," in query

    def test_explicit_sample_count_is_kept(self):
        query = self._query(UdaAccess("test", {}), nbp=1000, fallback_nbp=1920, tsS="100", tsE="200")
        assert "decSamples=1000," in query

    def test_clients_that_cannot_report_decimation_get_no_fallback(self, monkeypatch):
        monkeypatch.setattr(udaAccess, "_UDA_REPORTS_DECIMATION", False)
        query = self._query(UdaAccess("test", {}), nbp=-1, fallback_nbp=1920, tsS="100", tsE="200")
        assert "decSamples=-1," in query


class TestDecimationFlag:
    """Replies say whether UDA decimated them."""

    @staticmethod
    def _access(data, decimated):
        access = UdaAccess("test", {})
        access.UCR = MagicMock()
        access.UCR.fetchData.return_value = 0
        access.UCR.getFetchedTimeType.return_value = uc.RAW_TYPE_LONG
        access.UCR.getFetchedType.return_value = uc.RAW_TYPE_DOUBLE
        access.UCR.getDataNativeRank.return_value = data
        access.UCR.getTimeStampsAsLong.return_value = np.arange(len(data))
        access.UCR.isDecimated.return_value = decimated
        return access

    @pytest.mark.parametrize("decimated", [True, False])
    def test_data_reply(self, decimated):
        dobj = self._access(np.ones(4), decimated)._UdaAccess__fetch_data_x("q")
        assert dobj.errcode == 0
        assert dobj.isdecimated is decimated

    @pytest.mark.parametrize("decimated", [True, False])
    def test_envelope_reply(self, decimated):
        d_env = self._access(np.ones((4, 3)), decimated)._UdaAccess__fetch_envelope("q")
        assert d_env.errcode == 0
        assert d_env.isdecimated is decimated

    def test_clients_without_the_flag_report_raw(self, monkeypatch):
        monkeypatch.setattr(udaAccess, "_UDA_REPORTS_DECIMATION", False)
        access = self._access(np.ones(4), True)
        assert access._UdaAccess__fetch_data_x("q").isdecimated is False
        access.UCR.isDecimated.assert_not_called()


class TestLastValueBefore:
    """Extremities must hold a flat line over intervals that contain no samples of their own."""

    @staticmethod
    def _params(start_t, end_t, dec_type=None, fallback=None):
        p = UdaParams()
        p.set_params("FD", -1, dec_type, start_t, end_t, None, "absolute", True, None, fallback)
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

    def test_fallback_query_still_asks_for_a_single_sample(self, monkeypatch):
        access = UdaAccess("test", {})
        captured = {}

        def fake_fetch(query):
            captured["query"] = query
            dobj = DataObj()
            dobj.set_err(-3, "no data")
            return dobj

        monkeypatch.setattr(access, "_UdaAccess__fetch_data_x", fake_fetch)
        query = "variable=FD,tsFormat=absolute,decSamples=-1|1920,startTime=6000,endTime=7000,extSamples=True"
        access._UdaAccess__last_value_before(query, self._params(6000, 7000, fallback=1920))
        assert "decSamples=1," in captured["query"]
        assert "1920" not in captured["query"]

    def test_returns_none_when_no_earlier_sample(self, monkeypatch):
        access = UdaAccess("test", {})

        def fake_fetch(_query):
            dobj = DataObj()
            dobj.set_err(-3, "no data")
            return dobj

        monkeypatch.setattr(access, "_UdaAccess__fetch_data_x", fake_fetch)
        query = "variable=FD,tsFormat=absolute,decSamples=-1,startTime=100,endTime=200,extSamples=True"
        assert access._UdaAccess__last_value_before(query, self._params(100, 200)) is None


class TestClientSideExtremities:
    """Extremities added by the client (MINT_GET_EXTRE=true)."""

    def test_look_back_keeps_the_plain_dec_samples(self, monkeypatch):
        monkeypatch.setenv("MINT_GET_EXTRE", "true")
        access = UdaAccess("test", {})
        access.connected = True
        queries = []

        def fake_fetch(query):
            queries.append(query)
            dobj = DataObj()
            dobj.xdata = np.array([150])
            dobj.ydata = np.array([1.0])
            dobj.set_err(0, "OK")
            return dobj

        monkeypatch.setattr(access, "_UdaAccess__fetch_data_x", fake_fetch)
        access.get_data(varname="V", nbp=-1, fallback_nbp=1920, tsS="100", tsE="200", extremities=True)
        assert "decSamples=-1|1920," in queries[0]
        assert "decSamples=-1,startTime=0,endTime=100" in queries[1]


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


class TestCacheSizeConfig:

    def test_defaults_to_three_hundred_queries(self):
        assert UdaAccess("test", {}).access_cache.maxsize == 300

    def test_configured_size_drives_the_cache(self):
        assert UdaAccess("test", {"cache_size": 500}).access_cache.maxsize == 500

    def test_unusable_values_fall_back(self):
        assert UdaAccess("test", {"cache_size": "many"}).access_cache.maxsize == 300
        assert UdaAccess("test", {"cache_size": 0}).access_cache.maxsize == 1


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
