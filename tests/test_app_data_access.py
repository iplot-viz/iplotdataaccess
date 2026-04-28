# Description: Unit tests for the AppDataAccess singleton facade.

from iplotDataAccess.appDataAccess import AppDataAccess
from iplotDataAccess.dataAccess import DataAccess


class TestAppDataAccess:

    def test_initial_state_is_unconfigured(self, reset_app_data_access):
        assert AppDataAccess.is_configured() is False
        assert AppDataAccess.get_data_access() is None

    def test_initialize_creates_data_access_instance(self, reset_app_data_access, monkeypatch):
        monkeypatch.setattr(DataAccess, "load_config", lambda self, conf=None: True)
        result = AppDataAccess.initialize()
        assert result is True
        assert AppDataAccess.is_configured() is True
        assert isinstance(AppDataAccess.get_data_access(), DataAccess)

    def test_initialize_propagates_load_config_failure(self, reset_app_data_access, monkeypatch):
        monkeypatch.setattr(DataAccess, "load_config", lambda self, conf=None: False)
        result = AppDataAccess.initialize()
        assert result is False
        assert AppDataAccess.is_configured() is False
        assert isinstance(AppDataAccess.get_data_access(), DataAccess)

    def test_initialize_reuses_existing_data_access_instance(self, reset_app_data_access, monkeypatch):
        monkeypatch.setattr(DataAccess, "load_config", lambda self, conf=None: True)
        AppDataAccess.initialize()
        first = AppDataAccess.get_data_access()
        AppDataAccess.initialize()
        second = AppDataAccess.get_data_access()
        assert first is second

    def test_initialize_passes_config_file_through(self, reset_app_data_access, monkeypatch):
        captured = {}

        def fake_load(self, conf_file=None):
            captured["arg"] = conf_file
            return True

        monkeypatch.setattr(DataAccess, "load_config", fake_load)
        AppDataAccess.initialize(config_file="/tmp/myconf.cfg")
        assert captured["arg"] == "/tmp/myconf.cfg"
