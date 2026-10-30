# Description: Unit tests for the pyuda data source backend.

import os
import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from iplotDataAccess.pyudaAccess import PyudaAccess

LATEST_SHOT = 30500


class FakeClient:
    """Stand-in for pyuda.Client with a 1D signal ``ip``, a 2D signal ``ne_2d`` and a signal list."""
    server = None
    port = None

    def __init__(self):
        self.gets = []

    def latest_shot(self):
        return LATEST_SHOT

    def get(self, name, shot):
        self.gets.append((name, shot))
        time = SimpleNamespace(data=np.linspace(0.0, 0.9, 10), units="s")
        if name == "ip":
            return SimpleNamespace(data=np.arange(10, dtype=float), units="kA", label="Plasma Current",
                                   time=time)
        if name == "ne_2d":
            return SimpleNamespace(data=np.zeros((10, 3)), units="m^-3", label="", time=time)
        raise RuntimeError("No Record Found for this Generic Signal")

    def list_signals(self, shot):
        return [
            SimpleNamespace(signal_name="AMC_PLASMA CURRENT", generic_name="IP", source_alias="amc",
                            type="Analysed", description="Plasma current"),
            SimpleNamespace(signal_name="ANE_DENSITY", generic_name="", source_alias="ane",
                            type="A", description="Line integrated electron density"),
            SimpleNamespace(signal_name="ANE_DENSITY_ERR", generic_name="", source_alias="ane",
                            type="R", description="Density error"),
        ]

    def get_shot_date_time(self, shot):
        return "2013-07-04", "11:52:00"


@pytest.fixture
def fake_pyuda(monkeypatch):
    module = types.ModuleType("pyuda")
    module.Client = FakeClient
    monkeypatch.setitem(sys.modules, "pyuda", module)
    return module


@pytest.fixture
def pyuda_access(fake_pyuda):
    src = PyudaAccess("mast", {"pulse_list_size": 5})
    assert src.connect() is True
    return src


class TestConnect:

    def test_connect_sets_server_and_port(self, fake_pyuda):
        src = PyudaAccess("mast", {"host": "uda.example", "port": "1234"})
        assert src.connect() is True
        assert src.is_connected() is True
        assert fake_pyuda.Client.server == "uda.example"
        assert fake_pyuda.Client.port == 1234

    def test_connect_returns_false_when_server_fails(self, fake_pyuda, monkeypatch):
        def fail(self):
            raise RuntimeError("no server")
        monkeypatch.setattr(FakeClient, "latest_shot", fail)
        src = PyudaAccess("mast", {})
        assert src.connect() is False
        assert src.errdesc == "no server"


class TestParseShot:

    @pytest.mark.parametrize("pulse, shot", [("30420", 30420), (30420, 30420), ("MAST/30420", 30420),
                                             ("MAST:30420", 30420), ("-1", -1), (None, None), ("abc", None)])
    def test_parse_shot(self, pulse, shot):
        assert PyudaAccess.parse_shot(pulse) == shot


class TestGetData:

    def test_returns_full_signal_with_units(self, pyuda_access):
        d = pyuda_access.get_data(varname="ip", pulse="30420", tsS=None, tsE=None, nbp=-1)
        assert d.errcode == 0
        assert len(d.xdata) == 10
        assert list(d.ydata) == list(range(10))
        assert d.xunit == "s"
        assert d.yunit == "kA"
        assert d.ylabel == "Plasma Current"
        assert d.resolved_pulse is None

    def test_crops_to_time_window(self, pyuda_access):
        d = pyuda_access.get_data(varname="ip", pulse="30420", tsS=0.2, tsE=0.5)
        assert np.allclose(d.xdata, [0.2, 0.3, 0.4, 0.5])

    def test_decimates_to_nbp(self, pyuda_access):
        d = pyuda_access.get_data(varname="ip", pulse="30420", nbp=4)
        assert list(d.ydata) == [0, 3, 6, 9]

    def test_relative_pulse_resolves_to_latest_shot(self, pyuda_access):
        d = pyuda_access.get_data(varname="ip", pulse="0")
        assert d.errcode == 0
        assert d.resolved_pulse == str(LATEST_SHOT)
        d = pyuda_access.get_data(varname="ip", pulse="-2")
        assert d.resolved_pulse == str(LATEST_SHOT - 2)

    def test_caches_signals(self, pyuda_access):
        pyuda_access.get_data(varname="ip", pulse="30420")
        pyuda_access.get_data(varname="ip", pulse="30420", tsS=0.1)
        assert pyuda_access.client.gets == [("ip", 30420)]
        pyuda_access.clear_cache()
        pyuda_access.get_data(varname="ip", pulse="30420")
        assert len(pyuda_access.client.gets) == 2

    @pytest.mark.parametrize("kwargs, message", [
        ({"varname": "ip", "pulse": None}, "pulse"),
        ({"varname": "ne_2d", "pulse": "30420"}, "only 1D"),
        ({"varname": "missing", "pulse": "30420"}, "No Record Found"),
        ({"varname": "", "pulse": "30420"}, "No variable name"),
    ])
    def test_errors(self, pyuda_access, kwargs, message):
        d = pyuda_access.get_data(**kwargs)
        assert d.errcode == -1
        assert message in d.errdesc


class TestGetEnvelope:

    def test_bins_signal(self, pyuda_access):
        env = pyuda_access.get_envelope(varname="ip", pulse="30420", nbp=5)
        assert env.errcode == 0
        assert list(env.ydata_min) == [0, 2, 4, 6, 8]
        assert list(env.ydata_max) == [1, 3, 5, 7, 9]
        assert list(env.ydata_avg) == [0.5, 2.5, 4.5, 6.5, 8.5]
        assert len(env.xdata) == 5
        assert env.yunit == "kA"

    def test_error_gives_empty_envelope(self, pyuda_access):
        env = pyuda_access.get_envelope(varname="missing", pulse="30420")
        assert env.errcode == -1


class TestPulses:

    def test_existing_shot(self, pyuda_access):
        df = pyuda_access.get_pulses_df(pattern="30420")
        assert list(df["Pulse"]) == ["30420"]
        assert list(df.columns) == ["Pulse", "Run"]

    def test_shot_after_latest_is_not_found(self, pyuda_access):
        assert pyuda_access.get_pulses_df(pattern=str(LATEST_SHOT + 1)).empty

    def test_default_lists_recent_shots_oldest_first(self, pyuda_access):
        df = pyuda_access.get_pulses_df(pattern="*:*/*")
        assert list(df["Pulse"]) == [str(s) for s in range(LATEST_SHOT - 4, LATEST_SHOT + 1)]

    def test_search_matches_part_of_shot_number(self, pyuda_access):
        df = pyuda_access.search_pulses_df("3049")
        assert list(df["Pulse"]) == ["3049", "30490", "30491", "30492", "30493", "30494", "30495", "30496",
                                     "30497", "30498", "30499"]

    def test_search_skips_shots_after_latest(self, pyuda_access):
        df = pyuda_access.search_pulses_df("3050")
        assert list(df["Pulse"]) == ["3050", "30500"]

    def test_search_includes_exact_old_shot(self, pyuda_access):
        df = pyuda_access.search_pulses_df("30420")
        assert list(df["Pulse"]) == ["30420"]


class TestVariables:

    def test_groups_by_alias_with_generic_folder(self, pyuda_access):
        tree = pyuda_access.get_cbs_dict()
        assert tree == {
            "AMC": {"AMC_PLASMA CURRENT": ""},
            "ANE": {"ANE_DENSITY": "", "ANE_DENSITY_ERR": ""},
            "GENERIC": {"IP": ""},
        }

    def test_pattern_filters_case_insensitive(self, pyuda_access):
        assert pyuda_access.get_var_dict(pattern="density$") == {"ANE": {"ANE_DENSITY": ""}}

    def test_pattern_matches_description(self, pyuda_access):
        assert pyuda_access.get_var_dict(pattern="electron") == {"ANE": {"ANE_DENSITY": ""}}
        assert pyuda_access.get_var_dict(pattern="plasma current$") == {
            "AMC": {"AMC_PLASMA CURRENT": ""}, "GENERIC": {"IP": ""}}

    def test_var_fields_give_description_and_type(self, pyuda_access):
        assert pyuda_access.get_var_fields(variable="ANE_DENSITY") == {
            "value": {"type": "Analysed", "units": "", "description": "Line integrated electron density",
                      "dimensionality": []}}
        assert pyuda_access.get_var_fields(variable="ANE_DENSITY_ERR")["value"]["type"] == "Raw"

    def test_var_fields_of_generic_name(self, pyuda_access):
        fields = pyuda_access.get_var_fields(variable="IP")
        assert fields["value"]["description"] == "Plasma current"
        assert fields["value"]["type"] == "Analysed"

    def test_var_fields_of_unknown_variable_is_empty(self, pyuda_access):
        assert pyuda_access.get_var_fields(variable="missing") == {}


class TestPulseInfo:

    def test_contains_date_and_time(self, pyuda_access):
        info = pyuda_access.get_pulse_info(pulse=30420, run=0)
        assert info == {"shot": 30420, "run": 0, "latest_shot": LATEST_SHOT,
                        "date": "2013-07-04", "time": "11:52:00"}

    def test_works_without_date_and_time(self, pyuda_access, monkeypatch):
        def fail(self, shot):
            raise RuntimeError("no shot date")
        monkeypatch.setattr(FakeClient, "get_shot_date_time", fail)
        info = pyuda_access.get_pulse_info(pulse=30420, run=0)
        assert info == {"shot": 30420, "run": 0, "latest_shot": LATEST_SHOT}


@pytest.mark.skipif(not os.environ.get("PYUDA_LIVE_TESTS"), reason="set PYUDA_LIVE_TESTS=1 to use a live UDA server")
def test_live_mast_plasma_current():
    pytest.importorskip("pyuda")
    src = PyudaAccess("mast", {})
    assert src.connect() is True
    d = src.get_data(varname="ip", pulse="30420")
    assert d.errcode == 0
    assert len(d.xdata) == 30000
    assert d.yunit == "kA"


@pytest.mark.skipif(not os.environ.get("PYUDA_LIVE_TESTS"), reason="set PYUDA_LIVE_TESTS=1 to use a live UDA server")
def test_live_mast_signal_metadata():
    pytest.importorskip("pyuda")
    src = PyudaAccess("mast", {"list_shot": 30420})
    assert src.connect() is True
    assert src.get_var_fields(variable="ANE_DENSITY")["value"]["description"]
    assert "date" in src.get_pulse_info(pulse=30420, run=0)
