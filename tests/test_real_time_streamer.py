# Description: Unit tests for the SSE-based RTStreamer.

import getpass
from collections import deque
from types import SimpleNamespace

import pytest

from iplotDataAccess.dataCommon import DataObj, DataType
from iplotDataAccess.realTimeStreamer import (
    ProtoHeader,
    RTStreamer,
    RTStreamerException,
    VarType,
)


class _UdaUnitStub:
    def __init__(self, units=None, enums=None):
        self._units = units or {}
        self._enums = enums or {}

    def get_unit(self, varname):
        return self._units.get(varname, "?")

    def get_var_enum(self, varname, tsmp='-1'):
        return self._enums.get(varname)


class TestEnums:

    def test_proto_header_member_values(self):
        assert ProtoHeader.VARNAME.value == 0
        assert ProtoHeader.TIME_DT.value == 1
        assert ProtoHeader.VAL_DT.value == 2
        assert ProtoHeader.NB_SMP.value == 3

    def test_var_type_members(self):
        assert VarType.pon.value == "P"
        assert VarType.dan.value == "D"
        assert VarType.sdn.value == "S"


class TestHeaderSubstitution:

    def test_username_placeholder_is_replaced(self):
        rt = RTStreamer(headers={"REMOTE_USER": "$USERNAME", "X": "static"})
        assert rt.headers["REMOTE_USER"] == getpass.getuser()
        assert rt.headers["X"] == "static"

    def test_default_headers_used_when_none_provided(self):
        rt = RTStreamer()
        assert "REMOTE_USER" in rt.headers
        assert rt.headers["User-Agent"] == "python_client"


class TestConvertType:

    @pytest.mark.parametrize("utype,expected", [
        ("D", DataType.DA_TYPE_DOUBLE),
        ("PD", DataType.DA_TYPE_DOUBLE),
        ("ED", DataType.DA_TYPE_DOUBLE),
        ("L", DataType.DA_TYPE_LONG),
        ("S", DataType.DA_TYPE_STRING),
        ("PS", DataType.DA_TYPE_STRING),
    ])
    def test_known_types_map_to_data_type_enum(self, utype, expected):
        assert RTStreamer._RTStreamer__convert_type(utype) is expected

    def test_unknown_type_returns_none(self):
        assert RTStreamer._RTStreamer__convert_type("ZZZ") is None


class TestCheckIfDuplicate:

    def test_returns_all_indices(self):
        out = RTStreamer._RTStreamer__check_if_duplicate("v", params=["v", "x", "v"])
        assert out == [0, 2]

    def test_returns_empty_when_absent(self):
        out = RTStreamer._RTStreamer__check_if_duplicate("v", params=["x", "y"])
        assert out == []


class TestSetParams:

    def test_set_params_builds_query_and_calls_uda_for_units(self):
        uda = _UdaUnitStub({"v1": "V", "v2": "A"})
        rt = RTStreamer(uda_a=uda)
        rt._RTStreamer__set_params(["v1", "v2"])
        assert "variables=" in rt.params
        assert "v1" in rt.params and "v2" in rt.params
        assert rt._RTStreamer__units == {"v1": "V", "v2": "A"}

    def test_set_params_warns_when_uda_is_none(self):
        rt = RTStreamer()
        rt._RTStreamer__set_params(["v1"])
        assert rt.params is not None

    def test_set_params_survives_a_unit_lookup_failure(self):
        class _FlakyUda(_UdaUnitStub):
            def get_unit(self, varname):
                if varname == "bad":
                    raise RuntimeError("no metadata")
                return super().get_unit(varname)

        rt = RTStreamer(uda_a=_FlakyUda({"good": "V"}))
        rt._RTStreamer__set_params(["good", "bad"])
        assert rt._RTStreamer__units.get("good") == "V"
        assert "bad" not in rt._RTStreamer__units


class TestParseDataAndQueues:

    def _build(self, params=("VAR_A",)):
        rt = RTStreamer(uda_a=_UdaUnitStub({"VAR_A": "V"}))
        rt._RTStreamer__set_params(list(params))
        return rt

    def test_heartbeat_message_is_ignored(self):
        rt = self._build()
        rt._RTStreamer__parse_data("heartbeat 12345", params=["VAR_A"])
        assert rt.vardata == {}

    def test_short_message_is_ignored(self):
        rt = self._build()
        rt._RTStreamer__parse_data("VAR_A", params=["VAR_A"])
        assert rt.vardata == {}

    def test_string_payload_is_skipped(self):
        rt = self._build()
        rt._RTStreamer__parse_data("VAR_A 0 S 1 1631513472231 hello", params=["VAR_A"])
        assert rt.vardata == {}

    def test_create_queues_pon_uses_smaller_max_size(self):
        rt = RTStreamer(uda_a=_UdaUnitStub())
        rt._RTStreamer__create_queues([0], "P", "stub", params=["VAR"])
        assert rt.vardata["VAR@0"].maxlen == rt.maxsizeP

    def test_create_queues_dan_uses_larger_max_size(self):
        rt = RTStreamer(uda_a=_UdaUnitStub())
        rt._RTStreamer__create_queues([0], "D", "stub", params=["VAR"])
        assert rt.vardata["VAR@0"].maxlen == rt.maxsize

    def test_create_queues_appends_to_existing_queue(self):
        rt = RTStreamer(uda_a=_UdaUnitStub())
        rt._RTStreamer__create_queues([0], "D", "first", params=["VAR"])
        rt._RTStreamer__create_queues([0], "D", "second", params=["VAR"])
        assert list(rt.vardata["VAR@0"]) == ["first", "second"]


class TestEnumStreaming:

    def _build(self, enums):
        rt = RTStreamer(uda_a=_UdaUnitStub(units={"FAN": "?"}, enums=enums))
        rt._RTStreamer__set_params(["FAN"])
        return rt

    def test_set_params_caches_enum_labels(self):
        rt = self._build({"FAN": ("OFF", "ON")})
        assert rt._RTStreamer__enums == {"FAN": ("OFF", "ON")}

    def test_non_enum_string_leaves_cache_empty(self):
        rt = self._build({})
        assert rt._RTStreamer__enums == {}

    def test_enum_label_is_mapped_to_index(self):
        rt = self._build({"FAN": ("OFF", "ON")})
        rt._RTStreamer__parse_data(
            "FAN L PS 1 1784903188614 V[2] ON NO_ALARM NO_ALARM", params=["FAN"])
        d = rt.vardata["FAN@0"][0]
        assert list(d.ydata) == [1]
        assert list(d.xdata) == [1784903188614 * 1000000]

    def test_off_label_maps_to_zero(self):
        rt = self._build({"FAN": ("OFF", "ON")})
        rt._RTStreamer__parse_data(
            "FAN L PS 1 1784903188614 V[3] OFF COMM INVALID", params=["FAN"])
        assert list(rt.vardata["FAN@0"][0].ydata) == [0]

    def test_unknown_enum_label_is_dropped(self):
        rt = self._build({"FAN": ("OFF", "ON")})
        rt._RTStreamer__parse_data(
            "FAN L PS 1 1784903188614 V[7] UNKNOWN NO_ALARM NO_ALARM", params=["FAN"])
        assert rt.vardata == {}

    def test_string_without_enum_mapping_is_skipped(self):
        rt = self._build({})
        rt._RTStreamer__parse_data(
            "FAN L PS 1 1784903188614 V[5] hello NO_ALARM NO_ALARM", params=["FAN"])
        assert rt.vardata == {}


class TestGetNextData:

    def test_returns_empty_when_vname_is_none(self):
        rt = RTStreamer()
        d = rt.get_next_data(None)
        assert d.errcode == -1
        assert d.errdesc == "Varname is empty"

    def test_returns_empty_when_no_data(self):
        rt = RTStreamer()
        rt.origparams = ["v1"]
        rt.origparams1 = ["v1"]
        rt.vardata["v1@0"] = deque(maxlen=10)
        d = rt.get_next_data("v1")
        assert d.errcode == -1

    def test_returns_data_when_available(self):
        rt = RTStreamer()
        rt.origparams = ["v1"]
        rt.origparams1 = ["v1"]
        sample = DataObj()
        sample.set_data([1, 2], 1)
        sample.set_data([10, 20], 2)
        rt.vardata["v1@0"] = deque([sample], maxlen=10)
        d = rt.get_next_data("v1")
        assert list(d.xdata) == [1, 2]

    def test_unknown_varname_returns_no_data_found(self):
        rt = RTStreamer()
        rt.origparams = ["v1"]
        rt.origparams1 = ["v1"]
        d = rt.get_next_data("missing")
        assert d.errcode == -1
        assert d.errdesc == "No data found"


class TestSubscriptionStateMachine:

    def test_double_start_raises(self, monkeypatch):
        rt = RTStreamer()
        rt._RTStreamer__status = "STARTED"
        with pytest.raises(RTStreamerException):
            rt.start_subscription(params=["v1"])

    def test_stop_when_started_marks_stopping(self):
        rt = RTStreamer()
        rt._RTStreamer__status = "STARTED"
        rt.stop_subscription()
        assert rt.get_status() == "STOPPING"

    def test_stop_when_idle_is_noop(self):
        rt = RTStreamer()
        rt.stop_subscription()
        assert rt.get_status() == "INIT"


class TestStartSubscriptionMocked:

    def test_full_flow_with_mocked_sse(self, monkeypatch):
        from iplotDataAccess import realTimeStreamer as rts_mod

        captured = {}

        def fake_get(url, stream=None, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return SimpleNamespace(close=lambda: None, status_code=200)

        class FakeClient:
            def __init__(self, response):
                self.response = response

            def events(self):
                yield SimpleNamespace(data="VAR_A 0 D 1 1631513472231 0.5")

            def close(self):
                pass

        monkeypatch.setattr(rts_mod.requests, "get", fake_get)
        monkeypatch.setattr(rts_mod.sseclient, "SSEClient", FakeClient)

        rt = RTStreamer(url="http://x/sse", uda_a=_UdaUnitStub({"VAR_A": "V"}))
        rt.start_subscription(params=["VAR_A"], origparams=["VAR_A"])

        assert "variables=VAR_A" in captured["url"]
        assert rt.get_status() == "STOPPED"
