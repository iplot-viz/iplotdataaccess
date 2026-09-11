import json
import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def reset_app_data_access():
    """Reset the AppDataAccess singleton between tests."""
    from iplotDataAccess.appDataAccess import AppDataAccess
    AppDataAccess.da = None
    AppDataAccess.configured = False
    yield
    AppDataAccess.da = None
    AppDataAccess.configured = False


@pytest.fixture
def temp_csv_root(tmp_path):
    """Build a CSV folder tree compatible with CsvAccess.transform_pulse_to_file_path.

    Layout (single-level, matches what CsvAccess expects):
        <root>/COMM/data_111.csv
        <root>/COMM/data_112.csv
        <root>/EXP/data_200.csv
    """
    root = tmp_path / "ITER"
    comm = root / "COMM"
    exp = root / "EXP"
    comm.mkdir(parents=True)
    exp.mkdir(parents=True)

    (comm / "data_111.csv").write_text(
        "Time,VAR_A (V),VAR_B (A)\n"
        "0.0,1.0,10.0\n"
        "1.0,2.0,20.0\n"
        "2.0,3.0,30.0\n"
        "3.0,4.0,40.0\n"
    )
    (comm / "data_112.csv").write_text(
        "Time,VAR_A (V)\n"
        "0.0,5.0\n"
        "1.0,6.0\n"
    )
    (exp / "data_200.csv").write_text(
        "Time,TEMP (C)\n"
        "0.0,21.0\n"
        "1.0,22.0\n"
    )
    # Non-CSV files must be ignored by walks.
    (comm / "README.txt").write_text("not a csv file")
    (exp / ".DS_Store").write_text("metadata")
    return root


@pytest.fixture
def csv_config_file(tmp_path, temp_csv_root):
    """Create a JSON configuration file describing the CSV data source."""
    cfg_path = tmp_path / "datasources.cfg"
    cfg = {
        "csv_test": {
            "type": "CSV",
            "path": str(temp_csv_root).replace(os.sep, "/"),
            "default": True,
        }
    }
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


@pytest.fixture
def concrete_data_source_class():
    """Build a minimal concrete DataSource subclass usable in tests."""
    from iplotDataAccess.dataSource import DataSource

    class _TestDS(DataSource):
        source_type = "TEST"

        def __init__(self, name="test_ds", config=None):
            super().__init__(name, config or {})
            self.connected = True
            self.cleared = 0

        def clear_cache(self):
            self.cleared += 1

        def is_connected(self):
            return self.connected

        def get_data(self, **kwargs):
            from iplotDataAccess.dataCommon import DataObj
            d = DataObj()
            d.set_data([0, 1, 2], 1)
            d.set_data([10, 20, 30], 2)
            return d

        def get_envelope(self, **kwargs):
            from iplotDataAccess.dataCommon import DataEnvelope
            env = DataEnvelope()
            env.set_x_data([0, 1, 2])
            env.set_y_data([0, 1, 2], [1, 2, 3], [0.5, 1.5, 2.5])
            return env

        def search_pulses_df(self, text):
            import pandas as pd
            return pd.DataFrame([{"pulseId": "p1", "Status": "completed"}])

        def get_pulse_info(self, **kwargs):
            return {"info": "ok"}

        def get_pulses_df(self, **kwargs):
            import pandas as pd
            return pd.DataFrame([{"pulseId": "p1"}])

        def get_cbs_dict(self, **kwargs):
            return {"cbs": {}}

        def get_var_dict(self, **kwargs):
            return {"var": {}}

        def connect(self):
            return self.connected

    return _TestDS


@pytest.fixture
def fake_sse_event():
    """Return a factory that builds objects with the same shape as sseclient events."""
    def _make(data: str):
        return SimpleNamespace(data=data)
    return _make
