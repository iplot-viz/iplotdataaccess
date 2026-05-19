"""unit tests for SIMDB-backed pulse population.

Covers:
  1. Pagination + metadata merge
  2. Auth failure handling (401/403)
  3. Local folder merge / local-source filtering from cache
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from iplotDataAccess.simdbAccess import (
    EMPTY_DF,
    SIMDB_COLUMNS,
    SimDBClient,
    _decode_array,
    fetch_simulation_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status=200, json_body=None, content_type="application/json"):
    resp = MagicMock()
    resp.ok = (200 <= status < 300)
    resp.status_code = status
    resp.reason = "OK" if resp.ok else "Error"
    resp.headers = {"Content-Type": content_type}
    resp.json.return_value = json_body or {}
    return resp


def _sim_item(alias="run1", uuid_hex="abc123"):
    return {"alias": alias, "uuid": {"hex": uuid_hex}, "datetime": "2024-01-01T00:00:00"}


def _meta_response(uuid_hex):
    return {
        "metadata": [
            {"element": "code.name", "value": "METIS"},
            {"element": "ids_properties.comment", "value": "test run"},
            {"element": "ids_properties.creation_date", "value": "2024-01-01"},
        ],
        "inputs": [{"uri": f"imas://hdf5?uuid={uuid_hex}"}],
        "outputs": [],
    }


CONFIG = {
    "simdb_url": "https://simdb.test/api/simulations",
    "simdb_metadata_url": "https://simdb.test/api/simulation/{uuid}",
    "simdb_user": "testuser",
    "simdb_password": "testpass",
}


# ---------------------------------------------------------------------------
# 1. Metadata merge
# ---------------------------------------------------------------------------

class TestPagination(unittest.TestCase):
    """fetch_pulses attaches metadata to the correct rows."""

    def _build_page(self, items, total):
        return {"count": total, "results": items}

    @patch("iplotDataAccess.simdbAccess.fetch_simulation_metadata")
    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_metadata_merged_into_row(self, mock_get, mock_meta):
        items = [_sim_item("myrun", "uuid1"), _sim_item("otherrun", "uuid2")]
        mock_get.return_value = _make_response(json_body=self._build_page(items, 2))
        meta_by_uuid = {
            "uuid1": {
                "code.name": "workflow-1",
                "ids_properties.comment": "hello-1",
                "_imas_uri": "imas://hdf5?uuid=uuid1",
            },
            "uuid2": {
                "code.name": "workflow-2",
                "ids_properties.comment": "hello-2",
                "_imas_uri": "imas://hdf5?uuid=uuid2",
            },
        }
        mock_meta.side_effect = lambda _template, uuid, _auth: meta_by_uuid[uuid["hex"]]

        df = SimDBClient(CONFIG).fetch_pulses()
        rows = df.set_index("uuid")

        self.assertEqual(rows.loc["uuid1"]["workflow"], "workflow-1")
        self.assertEqual(rows.loc["uuid1"]["description"], "hello-1")
        self.assertEqual(rows.loc["uuid1"]["imas_uri"], "imas://hdf5?uuid=uuid1")
        self.assertEqual(rows.loc["uuid2"]["workflow"], "workflow-2")
        self.assertEqual(rows.loc["uuid2"]["description"], "hello-2")
        self.assertEqual(rows.loc["uuid2"]["imas_uri"], "imas://hdf5?uuid=uuid2")

    @patch("iplotDataAccess.simdbAccess.fetch_simulation_metadata")
    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_dashboard_link_constructed(self, mock_get, mock_meta):
        items = [_sim_item("run", "deadbeef")]
        mock_get.return_value = _make_response(json_body=self._build_page(items, 1))
        mock_meta.return_value = {"_imas_uri": ""}

        df = SimDBClient(CONFIG).fetch_pulses()

        self.assertEqual(df.iloc[0]["dashboard_link"],
                         "https://simdb.iter.org/dashboard/uuid/deadbeef")


# ---------------------------------------------------------------------------
# 2. Auth failure handling
# ---------------------------------------------------------------------------

class TestAuthFailure(unittest.TestCase):
    def _assert_empty_df(self, df):
        self.assertTrue(df.empty)
        self.assertListEqual(list(df.columns), SIMDB_COLUMNS)

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_401_returns_empty(self, mock_get):
        mock_get.return_value = _make_response(status=401)
        df = SimDBClient(CONFIG).fetch_pulses()
        self._assert_empty_df(df)

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_403_returns_empty(self, mock_get):
        mock_get.return_value = _make_response(status=403)
        df = SimDBClient(CONFIG).fetch_pulses()
        self._assert_empty_df(df)

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_401_clears_credentials(self, mock_get):
        mock_get.return_value = _make_response(status=401)
        client = SimDBClient(CONFIG)
        with patch.object(client, "_clear_credentials") as mock_clear:
            client.fetch_pulses()
            mock_clear.assert_called_once_with("testuser")

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_non_json_response_returns_empty(self, mock_get):
        mock_get.return_value = _make_response(
            status=200, content_type="text/html", json_body={}
        )
        df = SimDBClient(CONFIG).fetch_pulses()
        self._assert_empty_df(df)


# ---------------------------------------------------------------------------
# 3. Local folder merge and cache filtering
# ---------------------------------------------------------------------------

class TestLocalMerge(unittest.TestCase):

    def setUp(self):
        # Reset class-level pulse_list between tests
        from iplotDataAccess.imaspyAccess import IMASPYDataAccess
        IMASPYDataAccess.pulse_list = None

    def _make_local_df(self):
        return pd.DataFrame([{
            "alias": "local_run", "ip": "", "b0": "", "workflow": "",
            "date": "", "description": "local", "uuid": "loc1",
            "dashboard_link": "", "imas_uri": "imas://local", "source": "local",
        }])

    def _make_simdb_df(self):
        return pd.DataFrame([{
            "alias": "simdb_run", "ip": "", "b0": "", "workflow": "",
            "date": "", "description": "simdb", "uuid": "sim1",
            "dashboard_link": "https://simdb.iter.org/dashboard/uuid/sim1",
            "imas_uri": "imas://simdb", "source": "simdb",
        }])

    @patch("iplotDataAccess.localPulseAccess.LocalPulseScanner")
    @patch("iplotDataAccess.imaspyAccess.SimDBClient")
    def test_local_and_simdb_rows_both_present(self, mock_simdb_cls, mock_scanner_cls):
        mock_simdb_cls.return_value.fetch_pulses.return_value = self._make_simdb_df()
        mock_scanner_cls.return_value.fetch_pulses.return_value = self._make_local_df()

        from iplotDataAccess.imaspyAccess import IMASPYDataAccess
        config = {
            "populate_pulse_table": True,
            "pulse_list_folder": "/fake/folder",
            "simdb_url": "https://simdb.test/api/simulations",
            "simdb_metadata_url": "https://simdb.test/api/simulation/{uuid}",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"IPLOT_DUMP_PATH": tmpdir}):
                da = IMASPYDataAccess.__new__(IMASPYDataAccess)
                da.config = config
                df = da.get_pulses_df()

        aliases = list(df["alias"])
        self.assertIn("local_run", aliases)
        self.assertIn("simdb_run", aliases)

    @patch("iplotDataAccess.localPulseAccess.LocalPulseScanner")
    @patch("iplotDataAccess.imaspyAccess.SimDBClient")
    def test_local_entries_not_written_to_cache(self, mock_simdb_cls, mock_scanner_cls):
        """Local-source rows must be stripped before writing the parquet cache."""
        simdb_df = self._make_simdb_df()
        local_df = self._make_local_df()
        mock_simdb_cls.return_value.fetch_pulses.return_value = simdb_df
        mock_scanner_cls.return_value.fetch_pulses.return_value = local_df

        from iplotDataAccess.imaspyAccess import IMASPYDataAccess
        config = {
            "populate_pulse_table": True,
            "pulse_list_folder": "/fake/folder",
            "simdb_url": "https://simdb.test/api/simulations",
            "simdb_metadata_url": "https://simdb.test/api/simulation/{uuid}",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"IPLOT_DUMP_PATH": tmpdir}):
                da = IMASPYDataAccess.__new__(IMASPYDataAccess)
                da.config = config
                da.get_pulses_df()

                cached = pd.read_parquet(os.path.join(tmpdir, "pulses_df.parquet"))

        # local_run must NOT be in the cache
        self.assertNotIn("local_run", list(cached["alias"]))
        self.assertIn("simdb_run", list(cached["alias"]))


# ---------------------------------------------------------------------------
# 4. _decode_array helper
# ---------------------------------------------------------------------------

class TestDecodeArray(unittest.TestCase):

    def test_list_decoded(self):
        arr = _decode_array([1.0, 2.0, 3.0])
        self.assertEqual(list(arr), [1.0, 2.0, 3.0])

    def test_none_returned_for_unknown(self):
        self.assertIsNone(_decode_array("not_an_array"))
        self.assertIsNone(_decode_array(None))


if __name__ == "__main__":
    unittest.main()
