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


def _wire_reader_iso_converter(ds: UdaAccess) -> None:
    # add_pulse_info / update_pulse_info call UCR.convertTimeNsToISO. In
    # tests we stub it deterministically so assertions can match exactly.
    if ds.UCR is None:
        ds.UCR = MagicMock()
    ds.UCR.convertTimeNsToISO.side_effect = lambda ns: f"ISO({ns})"


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


class IsValidPulseIdTests(unittest.TestCase):
    def test_rejects_none(self):
        self.assertFalse(UdaAccess._is_valid_pulse_id(None))

    def test_rejects_empty_marker(self):
        self.assertFalse(UdaAccess._is_valid_pulse_id(":/"))

    def test_rejects_empty_string(self):
        self.assertFalse(UdaAccess._is_valid_pulse_id(""))

    def test_rejects_missing_separators(self):
        self.assertFalse(UdaAccess._is_valid_pulse_id("ITERlocal1"))

    def test_accepts_well_formed(self):
        self.assertTrue(UdaAccess._is_valid_pulse_id("ITER:MCTB-SIMU/1"))

    def test_accepts_well_formed_with_whitespace(self):
        self.assertTrue(UdaAccess._is_valid_pulse_id("  ITER:test/42  "))


class AddPulseInfoTests(unittest.TestCase):
    def test_disabled_when_not_write_capable(self):
        ds = _make_uda(write_capable=False)
        result = ds.add_pulse_info("ITER:local", 1, 2, "completed", "t")
        self.assertFalse(result["ok"])
        self.assertIn("not installed", result["error"])

    def test_rejects_description_over_200_chars(self):
        ds = _make_uda(write_capable=True)
        result = ds.add_pulse_info("ITER:local", 1, 2, "completed", "x" * 201)
        self.assertFalse(result["ok"])
        self.assertIn("200", result["error"])
        ds.UCW.addPulse.assert_not_called()
        ds.UCW.injectPulse.assert_not_called()

    def test_rejects_when_addPulse_returns_empty_marker(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.addPulse.return_value = ":/"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "t")
        self.assertFalse(result["ok"])
        self.assertIn("empty pulse", result["error"])
        ds.UCW.injectPulse.assert_not_called()

    def test_calls_addPulse_then_injectPulse_with_iso_timestamps(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.addPulse.return_value = "ITER:test/7"
        ds.UCW.injectPulse.return_value = "ok"
        ds.add_pulse_info("ITER:test", 1_641_760_133_123_456_789,
                          1_641_760_833_123_456_789, "completed", "first")
        ds.UCW.addPulse.assert_called_once_with("ITER:test", "first")
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/7",
            "ISO(1641760133123456789)",
            "ISO(1641760833123456789)",
            "completed",
            "first",
        )

    def test_returns_ok_with_pulse_id_and_raw_on_success(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.addPulse.return_value = "ITER:test/99"
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["pulse_id"], "ITER:test/99")
        self.assertEqual(result["raw"], "ok")

    def test_catches_writer_exception_and_reports_error(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.addPulse.side_effect = RuntimeError("server refused")
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x")
        self.assertFalse(result["ok"])
        self.assertIn("server refused", result["error"])


class UpdatePulseInfoTests(unittest.TestCase):
    def test_disabled_when_not_write_capable(self):
        ds = _make_uda(write_capable=False)
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "t")
        self.assertFalse(result["ok"])
        self.assertIn("not installed", result["error"])

    def test_rejects_description_over_200_chars(self):
        ds = _make_uda(write_capable=True)
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "x" * 201)
        self.assertFalse(result["ok"])
        self.assertIn("200", result["error"])
        ds.UCW.injectPulse.assert_not_called()

    def test_rejects_invalid_pulse_id(self):
        ds = _make_uda(write_capable=True)
        result = ds.update_pulse_info(":/", 1, 2, "completed", "t")
        self.assertFalse(result["ok"])
        self.assertIn("invalid pulse id", result["error"])
        ds.UCW.injectPulse.assert_not_called()

    def test_calls_injectPulse_with_iso_timestamps(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.injectPulse.return_value = "ok"
        ds.update_pulse_info("ITER:test/1", 1_641_760_133_123_456_789,
                             1_641_760_833_123_456_789, "completed", "edit")
        ds.UCW.addPulse.assert_not_called()
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/1",
            "ISO(1641760133123456789)",
            "ISO(1641760833123456789)",
            "completed",
            "edit",
        )

    def test_returns_ok_with_raw_on_success(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["raw"], "ok")

    def test_catches_writer_exception_and_reports_error(self):
        ds = _make_uda(write_capable=True)
        _wire_reader_iso_converter(ds)
        ds.UCW.injectPulse.side_effect = RuntimeError("server refused")
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "x")
        self.assertFalse(result["ok"])
        self.assertIn("server refused", result["error"])


if __name__ == "__main__":
    unittest.main()
