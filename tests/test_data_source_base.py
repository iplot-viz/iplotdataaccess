# Description: Unit tests for the DataSource abstract base class and its RT subscription state machine.

import pytest

from iplotDataAccess.dataSource import (
    DS_CODAC_TYPE,
    DataSource,
    RTHException,
)
from iplotDataAccess.realTimeStreamer import RTStreamerException


class _FakeRTHandler:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.start_called_with = None
        self.stop_called = False
        self._status = "INITIALISED"

    def start_subscription(self, **kwargs):
        self.start_called_with = kwargs

    def stop_subscription(self):
        self.stop_called = True

    def get_status(self):
        return self._status


@pytest.fixture
def fake_rt(monkeypatch):
    """Patch RTStreamer used inside dataSource so set_rt_handler builds the fake."""
    from iplotDataAccess import dataSource as ds_mod
    monkeypatch.setattr(ds_mod, "RTStreamer", _FakeRTHandler)
    return _FakeRTHandler


class TestSubclassValidation:

    def test_subclass_without_source_type_is_rejected(self):
        with pytest.raises(TypeError):
            class _Bad(DataSource):
                source_type = None

                def clear_cache(self): pass
                def is_connected(self): return True
                def get_data(self, **kwargs): pass
                def get_envelope(self, **kwargs): pass
                def search_pulses_df(self, text): pass
                def get_pulse_info(self, **kwargs): pass
                def get_pulses_df(self, **kwargs): pass
                def get_cbs_dict(self, **kwargs): pass
                def get_var_dict(self, **kwargs): pass
                def connect(self): return True


class TestRTHandlerSetters:

    def test_set_rt_headers_auth_url(self, concrete_data_source_class):
        ds = concrete_data_source_class()
        ds.set_rt_headers("k:v")
        ds.set_rt_auth("auth-token")
        ds.set_rt_url("http://example/sse")
        assert ds.rth == "k:v"
        assert ds.rta == "auth-token"
        assert ds.rtu == "http://example/sse"


class TestSetRTHandler:

    def test_raises_when_source_type_is_not_codac(self, concrete_data_source_class):
        ds = concrete_data_source_class()
        with pytest.raises(RTHException):
            ds.set_rt_handler()
        assert ds.rterrcode == -1
        assert ds.rtStatus == "UNEXISTING"

    def test_invalid_header_entry_raises(self, concrete_data_source_class):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_headers("malformed_entry_no_colon")
            with pytest.raises(RTHException):
                ds.set_rt_handler()
        finally:
            type(ds).source_type = "TEST"

    def test_well_formed_headers_initialise_handler(self, concrete_data_source_class, fake_rt):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u,User-Agent:py")
            ds.set_rt_handler()
            assert ds.rterrcode == 0
            assert ds.rtStatus == "INITIALISED"
            assert ds.RTHandler.kwargs["headers"] == {"REMOTE_USER": "u", "User-Agent": "py"}
        finally:
            type(ds).source_type = "TEST"

    def test_module_not_found_during_streamer_init_marks_unexisting(self, concrete_data_source_class, monkeypatch):
        from iplotDataAccess import dataSource as ds_mod

        def raise_mnf(**kwargs):
            raise ModuleNotFoundError("requests not installed")

        monkeypatch.setattr(ds_mod, "RTStreamer", raise_mnf)
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            assert ds.rterrcode == -1
            assert ds.rtStatus == "UNEXISTING"
        finally:
            type(ds).source_type = "TEST"


class TestStartSubscription:

    def test_starts_when_initialised_and_propagates_params(self, concrete_data_source_class, fake_rt):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            ds.start_subscription(params=["v1", "v2"])
            assert ds.rtStatus == "STARTED"
            assert ds.RTHandler.start_called_with["params"] == ["v1", "v2"]
            assert ds.RTHandler.start_called_with["origparams"] == ["v1", "v2"]
        finally:
            type(ds).source_type = "TEST"

    def test_streamer_exception_marks_error_state(self, concrete_data_source_class, fake_rt, monkeypatch):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            def boom(**kwargs):
                raise RTStreamerException("boom")
            monkeypatch.setattr(ds.RTHandler, "start_subscription", boom)
            ds.start_subscription(params=["v1"])
            assert ds.rtStatus == "ERROR"
            assert ds.rterrcode == -2
        finally:
            type(ds).source_type = "TEST"


class TestStopSubscription:

    def test_stop_after_start_transitions_to_stopped(self, concrete_data_source_class, fake_rt):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            ds.start_subscription(params=["v1"])
            ds.stop_subscription()
            assert ds.rtStatus == "STOPPED"
            assert ds.RTHandler.stop_called is True
        finally:
            type(ds).source_type = "TEST"

    def test_stop_when_not_started_is_noop(self, concrete_data_source_class):
        ds = concrete_data_source_class()
        ds.stop_subscription()
        assert ds.rtStatus == "UNEXISTING"

    def test_streamer_exception_on_stop_marks_error_state(self, concrete_data_source_class, fake_rt, monkeypatch):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            ds.start_subscription(params=["v1"])

            def boom():
                raise RTStreamerException("stop boom")

            monkeypatch.setattr(ds.RTHandler, "stop_subscription", boom)
            ds.stop_subscription()
            assert ds.rtStatus == "ERROR"
            assert ds.rterrcode == -2
        finally:
            type(ds).source_type = "TEST"


class TestGetNextData:

    def test_returns_empty_when_handler_not_initialised(self, concrete_data_source_class):
        ds = concrete_data_source_class()
        ds.RTHandler = None
        ds.MAX_ITER = 1
        ds.SLEEP_TO = 0
        d = ds.get_next_data("v1")
        assert d.errcode == -1
        assert "Streamer not properly initialized" in d.errdesc

    def test_delegates_to_handler_when_ready(self, concrete_data_source_class, fake_rt):
        ds = concrete_data_source_class()
        type(ds).source_type = DS_CODAC_TYPE
        try:
            ds.set_rt_url("http://x/sse")
            ds.set_rt_headers("REMOTE_USER:u")
            ds.set_rt_handler()
            ds.RTHandler.params = "variables=v1"
            ds.RTHandler.get_next_data = lambda vname: f"got:{vname}"
            assert ds.get_next_data("v1") == "got:v1"
        finally:
            type(ds).source_type = "TEST"
