"""Unit tests for the optional pulse-creation API on UdaAccess.

The uda_client_writer module is not always installed (it ships as a
separate codac package). These tests use mocks so they pass regardless
of whether the writer is available locally — the feature itself is
gated by `_write_capable`, which we drive directly.
"""
import unittest
from unittest.mock import MagicMock

from iplotDataAccess.udaAccess import UdaAccess


def _make_uda(write_capable: bool = True) -> UdaAccess:
    ds = UdaAccess("codacuda", {"host": "localhost", "port": 3090})
    ds._write_capable = write_capable
    ds.UCW = MagicMock() if write_capable else None
    return ds


class IsWriteCapableTests(unittest.TestCase):
    def test_false_when_writer_module_missing(self):
        ds = _make_uda(write_capable=False)
        self.assertFalse(ds.is_write_capable())

    def test_false_when_flag_true_but_client_missing(self):
        ds = _make_uda(write_capable=True)
        ds.UCW = None
        self.assertFalse(ds.is_write_capable())

    def test_true_when_module_and_client_ready(self):
        ds = _make_uda(write_capable=True)
        self.assertTrue(ds.is_write_capable())


class GetPulseCategoriesTests(unittest.TestCase):
    def test_returns_categories_from_reader(self):
        ds = _make_uda(write_capable=True)
        ds.UCR = MagicMock()
        ds.UCR.getPulseCategories.return_value = ["ITER:local", "ITER:test"]
        ds.UCR.getErrorCode.return_value = 0
        self.assertEqual(ds.get_pulse_categories(), ["ITER:local", "ITER:test"])

    def test_returns_empty_when_reader_missing(self):
        ds = _make_uda(write_capable=True)
        ds.UCR = None
        self.assertEqual(ds.get_pulse_categories(), [])

    def test_returns_empty_when_reader_reports_error(self):
        ds = _make_uda(write_capable=True)
        ds.UCR = MagicMock()
        ds.UCR.getPulseCategories.return_value = None
        ds.UCR.getErrorCode.return_value = 5
        ds.UCR.getErrorMsg.return_value = "boom"
        self.assertEqual(ds.get_pulse_categories(), [])

    def test_returns_empty_when_reader_raises(self):
        ds = _make_uda(write_capable=True)
        ds.UCR = MagicMock()
        ds.UCR.getPulseCategories.side_effect = RuntimeError("boom")
        self.assertEqual(ds.get_pulse_categories(), [])

    def test_coerces_non_string_items(self):
        ds = _make_uda(write_capable=True)
        ds.UCR = MagicMock()
        ds.UCR.getPulseCategories.return_value = ["ITER:local", b"ITER:test"]
        ds.UCR.getErrorCode.return_value = 0
        self.assertEqual(ds.get_pulse_categories(),
                         ["ITER:local", "b'ITER:test'"])


class AddPulseInfoTests(unittest.TestCase):
    def test_disabled_when_not_write_capable(self):
        ds = _make_uda(write_capable=False)
        result = ds.add_pulse_info("ITER:local", 1, 2, "OK", "test")
        self.assertFalse(result["ok"])
        self.assertIn("not installed", result["error"])

    def test_rejects_description_over_200_chars(self):
        ds = _make_uda(write_capable=True)
        result = ds.add_pulse_info("ITER:local", 1, 2, "OK", "x" * 201)
        self.assertFalse(result["ok"])
        self.assertIn("200", result["error"])
        ds.UCW.addPulseInfo.assert_not_called()

    def test_passes_args_to_writer_with_ns_as_strings(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulseInfo.return_value = {"pulse_id": 42}
        ds.add_pulse_info("ITER:test", 1_641_760_133_123_456_789,
                          1_641_760_833_123_456_789, "completed", "first pulse")
        ds.UCW.addPulseInfo.assert_called_once_with(
            "ITER:test",
            "1641760133123456789",
            "1641760833123456789",
            "completed",
            "first pulse",
        )

    def test_returns_ok_with_raw_on_success(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulseInfo.return_value = {"pulse_id": 99}
        result = ds.add_pulse_info("ITER:test", 1, 2, "OK", "x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["raw"], {"pulse_id": 99})

    def test_catches_writer_exception_and_reports_error(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulseInfo.side_effect = RuntimeError("server refused")
        result = ds.add_pulse_info("ITER:test", 1, 2, "OK", "x")
        self.assertFalse(result["ok"])
        self.assertIn("server refused", result["error"])


if __name__ == "__main__":
    unittest.main()
