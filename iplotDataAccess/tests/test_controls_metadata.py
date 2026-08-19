"""Unit tests for the controls metadata (HMI variables) support in DataSource."""

import unittest
from unittest.mock import MagicMock, patch

from iplotDataAccess.dataSource import DataSource


class _StubSource(DataSource):
    """Minimal concrete DataSource: the HMI support lives in the base class."""
    source_type = "STUB"

    def clear_cache(self):
        pass

    def is_connected(self):
        return True

    def get_data(self, **kwargs):
        pass

    def get_envelope(self, **kwargs):
        pass

    def search_pulses_df(self, text):
        pass

    def get_pulse_info(self, **kwargs):
        pass

    def get_pulses_df(self, **kwargs):
        pass

    def get_cbs_dict(self, **kwargs):
        return {}

    def get_var_dict(self, **kwargs):
        return {}

    def connect(self):
        return True


HMI_BODY = [
    {"variable": "UTIL-S15-VA:RB01-FT01", "description": "Flow rate", "unit": "m3/s", "data_type": "float"},
    {"variable": "UTIL-S15-VA:RB01-TT01", "description": "Water temperature", "unit": "K", "data_type": "float"},
]


def _make_response(json_body):
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


class TestParseHmiBody(unittest.TestCase):

    def test_bare_list_is_normalized(self):
        result = DataSource._parse_hmi_body(HMI_BODY)
        self.assertEqual(set(result), {"UTIL-S15-VA:RB01-FT01", "UTIL-S15-VA:RB01-TT01"})
        self.assertEqual(result["UTIL-S15-VA:RB01-FT01"],
                         {"description": "Flow rate", "units": "m3/s", "type": "float"})

    def test_wrapped_list_is_accepted(self):
        result = DataSource._parse_hmi_body({"variables": HMI_BODY})
        self.assertEqual(len(result), 2)

    def test_key_variants_are_tolerated(self):
        body = [{"name": "VAR-A", "description": "d", "units": "V", "data type": "int"}]
        result = DataSource._parse_hmi_body(body)
        self.assertEqual(result["VAR-A"], {"description": "d", "units": "V", "type": "int"})

    def test_entries_without_name_are_skipped(self):
        body = [{"description": "orphan"}, "not-a-dict", {"variable": "VAR-B"}]
        result = DataSource._parse_hmi_body(body)
        self.assertEqual(set(result), {"VAR-B"})
        self.assertEqual(result["VAR-B"], {"description": "", "units": "", "type": ""})

    def test_non_list_body_returns_empty(self):
        self.assertEqual(DataSource._parse_hmi_body("garbage"), {})
        self.assertEqual(DataSource._parse_hmi_body({"count": 3}), {})


class TestGetHmiVarDict(unittest.TestCase):

    def test_without_server_configured_returns_empty(self):
        source = _StubSource("s", {})
        with patch("requests.get") as mock_get:
            self.assertEqual(source.get_hmi_var_dict(), {})
            mock_get.assert_not_called()

    def test_fetches_and_caches(self):
        source = _StubSource("s", {"controlsmetadata": "meta-host.iter.org:3000"})
        with patch("requests.get", return_value=_make_response(HMI_BODY)) as mock_get:
            first = source.get_hmi_var_dict()
            second = source.get_hmi_var_dict()
            self.assertEqual(len(first), 2)
            self.assertIs(first, second)
            mock_get.assert_called_once_with("http://meta-host.iter.org:3000/variable_hmi", timeout=30,
                                             proxies={"http": None, "https": None})

    def test_refresh_requests_again(self):
        source = _StubSource("s", {"controlsmetadata": "http://meta-host.iter.org:3000"})
        with patch("requests.get", return_value=_make_response(HMI_BODY)) as mock_get:
            source.get_hmi_var_dict()
            source.get_hmi_var_dict(refresh=True)
            self.assertEqual(mock_get.call_count, 2)

    def test_request_failure_returns_empty_and_keeps_cache_clear(self):
        source = _StubSource("s", {"controlsmetadata": "http://meta-host.iter.org:3000"})
        with patch("requests.get", side_effect=OSError("unreachable")):
            self.assertEqual(source.get_hmi_var_dict(), {})
        with patch("requests.get", return_value=_make_response(HMI_BODY)):
            self.assertEqual(len(source.get_hmi_var_dict()), 2)


if __name__ == "__main__":
    unittest.main()
