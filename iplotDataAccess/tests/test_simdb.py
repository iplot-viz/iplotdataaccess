"""Unit tests for SimDBClient"""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from iplotDataAccess.simdbAccess import (
    SIMDB_COLUMNS,
    SimDBClient,
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


CONFIG = {
    "simdb_url": "https://simdb.test/api/simulations",
    "simdb_metadata_url": "https://simdb.test/api/simulation/{uuid}",
    "simdb_user": "testuser",
    "simdb_password": "testpass",
}

METADATA_URL = "https://simdb.test/api/simulation/{uuid}"
AUTH = ("testuser", "testpass")


# ---------------------------------------------------------------------------
# fetch_simulation_metadata
# ---------------------------------------------------------------------------

class TestFetchSimulationMetadata(unittest.TestCase):
    """tests for fetch_simulation_metadata."""

    def _mock_session_get(self, resp):
        """Patch _get_session so session.get() returns resp."""
        mock_session = MagicMock()
        mock_session.get.return_value = resp
        return patch("iplotDataAccess.simdbAccess._get_session", return_value=mock_session)

    def test_returns_flat_dict_with_metadata_fields(self):
        """metadata elements and imas_uri are returned as a flat dict."""
        body = {
            "metadata": [
                {"element": "code.name", "value": "METIS"},
                {"element": "ids_properties.comment", "value": "baseline run"},
            ],
            "inputs": [{"uri": "imas://hdf5?uuid=abc"}],
            "outputs": [],
        }
        with self._mock_session_get(_make_response(json_body=body)):
            result = fetch_simulation_metadata(METADATA_URL, {"hex": "abc"}, AUTH)

        self.assertEqual(result["code.name"], "METIS")
        self.assertEqual(result["ids_properties.comment"], "baseline run")
        self.assertEqual(result["_imas_uri"], "imas://hdf5?uuid=abc")

    def test_non_ok_response_returns_empty_dict(self):
        """Any non-2xx HTTP status must return {} without raising."""
        with self._mock_session_get(_make_response(status=404)):
            result = fetch_simulation_metadata(METADATA_URL, {"hex": "abc"}, AUTH)
        self.assertEqual(result, {})

    def test_non_json_content_type_returns_empty_dict(self):
        """Non-JSON content-type must return {} without raising."""
        with self._mock_session_get(_make_response(content_type="text/html")):
            result = fetch_simulation_metadata(METADATA_URL, {"hex": "abc"}, AUTH)
        self.assertEqual(result, {})

    def test_network_exception_returns_empty_dict(self):
        """Network errors must be swallowed and return {}."""
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("timeout")
        with patch("iplotDataAccess.simdbAccess._get_session", return_value=mock_session):
            result = fetch_simulation_metadata(METADATA_URL, {"hex": "abc"}, AUTH)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# SimDBClient.fetch_pulses
# ---------------------------------------------------------------------------

class TestFetchPulses(unittest.TestCase):
    """Generic tests for SimDBClient.fetch_pulses."""

    # fetch_pulses builds records without "source" (added later by get_pulses_df)
    _FETCH_COLUMNS = [c for c in SIMDB_COLUMNS if c != "source"]

    @patch("iplotDataAccess.simdbAccess.fetch_simulation_metadata")
    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_returns_dataframe_with_expected_columns(self, mock_get, mock_meta):
        """Result contains all expected columns and exactly one row."""
        mock_get.return_value = _make_response(
            json_body={"count": 1, "results": [_sim_item("run1", "uid1")]}
        )
        mock_meta.return_value = {
            "code.name": "METIS", "ids_properties.comment": "ok",
            "ids_properties.creation_date": "2024-01-01", "_imas_uri": "imas://hdf5?uuid=uid1",
        }

        df = SimDBClient(CONFIG).fetch_pulses()

        self.assertIsInstance(df, pd.DataFrame)
        for col in self._FETCH_COLUMNS:
            self.assertIn(col, df.columns, msg=f"Missing column: {col}")
        self.assertEqual(len(df), 1)

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_auth_failure_returns_empty_df_with_correct_schema(self, mock_get):
        """401/403 must return an empty DataFrame that still has SIMDB_COLUMNS."""
        for status in (401, 403):
            with self.subTest(status=status):
                mock_get.return_value = _make_response(status=status)
                df = SimDBClient(CONFIG).fetch_pulses()
                self.assertTrue(df.empty)
                self.assertListEqual(list(df.columns), SIMDB_COLUMNS)

    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_non_json_response_returns_empty_df(self, mock_get):
        """Non-JSON content-type must return an empty DataFrame with SIMDB_COLUMNS."""
        mock_get.return_value = _make_response(status=200, content_type="text/html")
        df = SimDBClient(CONFIG).fetch_pulses()
        self.assertTrue(df.empty)
        self.assertListEqual(list(df.columns), SIMDB_COLUMNS)

    @patch("iplotDataAccess.simdbAccess.fetch_simulation_metadata")
    @patch("iplotDataAccess.simdbAccess.SimDBClient._do_get")
    def test_dashboard_link_built_from_uuid(self, mock_get, mock_meta):
        """dashboard_link must be constructed as the canonical SIMDB URL."""
        mock_get.return_value = _make_response(
            json_body={"count": 1, "results": [_sim_item("run", "JHSDF76GCBHXB")]}
        )
        mock_meta.return_value = {"_imas_uri": ""}

        df = SimDBClient(CONFIG).fetch_pulses()

        self.assertEqual(
            df.iloc[0]["dashboard_link"],
            "https://simdb.iter.org/dashboard/uuid/JHSDF76GCBHXB",
        )


if __name__ == "__main__":
    unittest.main()
