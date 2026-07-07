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
