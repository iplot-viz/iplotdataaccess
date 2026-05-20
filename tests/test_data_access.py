# Description: Unit tests for the DataAccess orchestrator.

import json

import pytest

from iplotDataAccess.dataAccess import DataAccess
from iplotDataAccess.dataCommon import DataEnvelope, DataObj


@pytest.fixture
def patched_data_access(monkeypatch, concrete_data_source_class):
    """Build a DataAccess instance whose backend registry only contains the test source."""
    monkeypatch.setattr(
        DataAccess,
        "get_supported_data_source",
        staticmethod(lambda: {"TEST": concrete_data_source_class}),
    )
    return DataAccess()


def _write_cfg(path, mapping):
    path.write_text(json.dumps(mapping))
    return path


class TestGetSupportedDataSource:

    def test_real_registry_contains_csv_backend(self):
        registry = DataAccess.get_supported_data_source()
        assert "CSV" in registry


class TestLoadConfigFallbackChain:

    def test_load_config_uses_explicit_file_first(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "good.cfg", {"a": {"type": "TEST"}})
        assert patched_data_access.load_config(str(cfg)) is True
        assert "a" in patched_data_access.ds_list

    def test_load_config_falls_back_to_env_var(self, tmp_path, patched_data_access, monkeypatch):
        cfg = _write_cfg(tmp_path / "envcfg.cfg", {"b": {"type": "TEST"}})
        monkeypatch.setenv("IPLOT_SOURCES_CONFIG", str(cfg))
        assert patched_data_access.load_config() is True
        assert "b" in patched_data_access.ds_list

    def test_load_config_returns_false_when_all_paths_missing(self, patched_data_access, monkeypatch, tmp_path):
        monkeypatch.delenv("IPLOT_SOURCES_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        assert patched_data_access.load_config() is False


class TestLoadConfigFile:

    def test_invalid_json_returns_false(self, tmp_path, patched_data_access):
        bad = tmp_path / "bad.cfg"
        bad.write_text("{ not json }")
        assert patched_data_access.load_config_file(str(bad)) is False

    def test_unsupported_data_source_type_is_skipped(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "mixed.cfg",
                         {"good": {"type": "TEST"}, "bad": {"type": "UNKNOWN"}})
        assert patched_data_access.load_config_file(str(cfg)) is True
        assert list(patched_data_access.ds_list.keys()) == ["good"]

    def test_default_data_source_is_picked_when_flagged(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "default.cfg", {
            "first": {"type": "TEST"},
            "primary": {"type": "TEST", "default": True},
        })
        assert patched_data_access.load_config_file(str(cfg)) is True
        assert patched_data_access.default_ds.name == "primary"

    def test_default_falls_back_to_first_when_none_flagged(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "no_default.cfg", {
            "alpha": {"type": "TEST"},
            "beta": {"type": "TEST"},
        })
        assert patched_data_access.load_config_file(str(cfg)) is True
        assert patched_data_access.default_ds.name == "alpha"

    def test_returns_false_when_no_data_source_connects(self, tmp_path, patched_data_access, concrete_data_source_class):
        original_init = concrete_data_source_class.__init__

        def init(self, name, config=None):
            original_init(self, name, config)
            self.connected = False

        concrete_data_source_class.__init__ = init
        try:
            cfg = _write_cfg(tmp_path / "dead.cfg", {"x": {"type": "TEST"}})
            assert patched_data_access.load_config_file(str(cfg)) is False
        finally:
            concrete_data_source_class.__init__ = original_init

    def test_backend_raising_in_connect_is_logged_and_skipped(self, tmp_path, patched_data_access, concrete_data_source_class):
        original_connect = concrete_data_source_class.connect

        def boom(self):
            raise RuntimeError("connect failed")

        concrete_data_source_class.connect = boom
        try:
            cfg = _write_cfg(tmp_path / "raise.cfg", {"bad": {"type": "TEST"}})
            assert patched_data_access.load_config_file(str(cfg)) is False
            assert "bad" not in patched_data_access.ds_list
        finally:
            concrete_data_source_class.connect = original_connect


class TestGetDataSource:

    def test_returns_named_data_source(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        assert patched_data_access.get_data_source("a").name == "a"

    def test_returns_default_when_name_is_none(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        assert patched_data_access.get_data_source(None).name == "a"

    def test_returns_none_when_no_default_and_name_none(self, patched_data_access):
        assert patched_data_access.get_data_source(None) is None

    def test_returns_none_when_name_unknown(self, patched_data_access):
        assert patched_data_access.get_data_source("missing") is None

    def test_default_ds_name_helper(self, tmp_path, patched_data_access):
        assert patched_data_access.get_default_ds_name() is None
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        assert patched_data_access.get_default_ds_name() == "a"


class TestGetDataDispatch:

    def test_get_data_for_known_source_returns_backend_payload(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        d = patched_data_access.get_data("a")
        assert isinstance(d, DataObj)
        assert list(d.xdata) == [0, 1, 2]

    def test_get_data_for_unknown_source_returns_empty_dataobj(self, patched_data_access):
        d = patched_data_access.get_data("does_not_exist")
        assert isinstance(d, DataObj)
        assert d.errcode == -1
        assert "Invalid data source name" in d.errdesc

    def test_get_data_with_none_returns_empty(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        d = patched_data_access.get_data(None)
        assert isinstance(d, DataObj)
        assert d.errcode == -1
        assert "Invalid data source name None" in d.errdesc

    def test_get_data_with_invalid_pointer_returns_empty(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        patched_data_access.ds_list["a"] = None
        d = patched_data_access.get_data("a")
        assert d.errcode == -1
        assert "Invalid data source pointer" in d.errdesc


class TestGetEnvelopeDispatch:

    def test_get_envelope_for_known_source(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        env = patched_data_access.get_envelope("a")
        assert isinstance(env, DataEnvelope)
        assert env.ydata_max == [1, 2, 3]

    def test_get_envelope_for_unknown_source_returns_empty(self, patched_data_access):
        env = patched_data_access.get_envelope("missing")
        assert isinstance(env, DataEnvelope)
        assert env.errcode == -1

    def test_get_envelope_with_none_returns_empty(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        env = patched_data_access.get_envelope(None)
        assert isinstance(env, DataEnvelope)
        assert env.errcode == -1

    def test_get_envelope_with_invalid_pointer_returns_empty(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        patched_data_access.ds_list["a"] = None
        env = patched_data_access.get_envelope("a")
        assert env.errcode == -1
        assert "Invalid data source pointer" in env.errdesc


class TestSubscriptionDispatch:

    def test_start_stop_subscription_call_through_to_backend(self, tmp_path, patched_data_access, monkeypatch):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        ds = patched_data_access.ds_list["a"]
        called = []
        monkeypatch.setattr(ds, "start_subscription", lambda **kw: called.append(("start", kw)))
        monkeypatch.setattr(ds, "stop_subscription", lambda: called.append(("stop",)))
        patched_data_access.start_subscription("a", params=["v1"])
        patched_data_access.stop_subscription("a")
        assert ("start", {"params": ["v1"]}) in called
        assert ("stop",) in called

    def test_subscription_for_unknown_source_does_nothing(self, patched_data_access):
        patched_data_access.start_subscription("ghost", params=[])
        patched_data_access.stop_subscription("ghost")

    def test_get_next_data_unknown_source_returns_empty(self, patched_data_access):
        d = patched_data_access.get_next_data("ghost", "v")
        assert isinstance(d, DataObj)
        assert d.errcode == -1


class TestConnectedDataSources:

    def test_connected_data_source_names(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {
            "a": {"type": "TEST", "default": True},
            "b": {"type": "TEST"},
        })
        patched_data_access.load_config_file(str(cfg))
        names = patched_data_access.get_connected_data_source_names()
        assert names[0] == "a"
        assert "b" in names

    def test_get_connected_data_sources_filters_disconnected(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}, "b": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        patched_data_access.ds_list["b"].connected = False
        connected = patched_data_access.get_connected_data_sources()
        assert [ds.name for ds in connected] == ["a"]

    def test_clear_cache_propagates_to_connected_sources(self, tmp_path, patched_data_access):
        cfg = _write_cfg(tmp_path / "ds.cfg", {"a": {"type": "TEST"}, "b": {"type": "TEST"}})
        patched_data_access.load_config_file(str(cfg))
        patched_data_access.ds_list["b"].connected = False
        patched_data_access.clear_cache()
        assert patched_data_access.ds_list["a"].cleared == 1
        assert patched_data_access.ds_list["b"].cleared == 0
