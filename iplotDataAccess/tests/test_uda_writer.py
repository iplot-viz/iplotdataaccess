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
        ds.UCW.addPulse.return_value = ":/"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "t")
        self.assertFalse(result["ok"])
        self.assertIn("empty pulse", result["error"])
        ds.UCW.injectPulse.assert_not_called()

    def test_calls_addPulse_then_injectPulse_with_ns_timestamps(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulse.return_value = "ITER:test/7"
        ds.UCW.injectPulse.return_value = "ok"
        ds.add_pulse_info("ITER:test", 1_641_760_133_123_456_789,
                          1_641_760_833_123_456_789, "completed", "first")
        ds.UCW.addPulse.assert_called_once_with("ITER:test", "first")
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/7",
            "1641760133123456789",
            "1641760833123456789",
            "completed",
            "first",
        )

    def test_sub_second_pulse_keeps_ns_precision(self):
        # The ISO conversion used to truncate to whole seconds, collapsing
        # any pulse shorter than one second.
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulse.return_value = "ITER:test/7"
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1_641_760_133_100_000_000,
                                   1_641_760_133_600_000_000, "completed", "short")
        self.assertTrue(result["ok"])
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/7",
            "1641760133100000000",
            "1641760133600000000",
            "completed",
            "short",
        )

    def test_returns_ok_with_pulse_id_and_raw_on_success(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulse.return_value = "ITER:test/99"
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["pulse_id"], "ITER:test/99")
        self.assertEqual(result["raw"], "ok")

    def test_catches_writer_exception_and_reports_error(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.addPulse.side_effect = RuntimeError("server refused")
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x")
        self.assertFalse(result["ok"])
        self.assertIn("server refused", result["error"])


class AddPulseInfoExplicitNumberTests(unittest.TestCase):
    """User-chosen pulse number: written at scope/number via injectPulse,
    guarded by an existence check before and a creation check after."""

    @staticmethod
    def _wire_existence(ds, exists_sequence):
        # get_pulse_info returns None for a missing pulse; drive it directly
        # so the tests do not depend on the reader's error plumbing.
        ds.get_pulse_info = MagicMock(
            side_effect=[(object() if e else None) for e in exists_sequence])

    def test_rejects_duplicate_pulse_number(self):
        ds = _make_uda(write_capable=True)
        self._wire_existence(ds, [True])
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x",
                                   pulse_number=20260526)
        self.assertFalse(result["ok"])
        self.assertIn("already exists", result["error"])
        ds.UCW.injectPulse.assert_not_called()
        ds.UCW.addPulse.assert_not_called()

    def test_creates_at_requested_number_and_verifies(self):
        ds = _make_uda(write_capable=True)
        self._wire_existence(ds, [False, True])
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x",
                                   pulse_number=20260526)
        self.assertTrue(result["ok"])
        self.assertEqual(result["pulse_id"], "ITER:test/20260526")
        ds.UCW.addPulse.assert_not_called()
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/20260526", "1", "2", "completed", "x")

    def test_reports_error_when_server_did_not_create_the_pulse(self):
        ds = _make_uda(write_capable=True)
        self._wire_existence(ds, [False, False])
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x",
                                   pulse_number=20260526)
        self.assertFalse(result["ok"])
        self.assertIn("did not create", result["error"])

    def test_rejects_malformed_number(self):
        ds = _make_uda(write_capable=True)
        result = ds.add_pulse_info("ITERtest-no-colon", 1, 2, "completed", "x",
                                   pulse_number=1)
        self.assertFalse(result["ok"])
        self.assertIn("invalid pulse id", result["error"])
        ds.UCW.injectPulse.assert_not_called()

    def test_without_number_keeps_auto_path(self):
        ds = _make_uda(write_capable=True)
        ds.get_pulse_info = MagicMock()
        ds.UCW.addPulse.return_value = "ITER:test/7"
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.add_pulse_info("ITER:test", 1, 2, "completed", "x")
        self.assertTrue(result["ok"])
        ds.UCW.addPulse.assert_called_once()
        ds.get_pulse_info.assert_not_called()


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

    def test_calls_injectPulse_with_ns_timestamps(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.injectPulse.return_value = "ok"
        ds.update_pulse_info("ITER:test/1", 1_641_760_133_123_456_789,
                             1_641_760_833_123_456_789, "completed", "edit")
        ds.UCW.addPulse.assert_not_called()
        ds.UCW.injectPulse.assert_called_once_with(
            "ITER:test/1",
            "1641760133123456789",
            "1641760833123456789",
            "completed",
            "edit",
        )

    def test_returns_ok_with_raw_on_success(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.injectPulse.return_value = "ok"
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["raw"], "ok")

    def test_catches_writer_exception_and_reports_error(self):
        ds = _make_uda(write_capable=True)
        ds.UCW.injectPulse.side_effect = RuntimeError("server refused")
        result = ds.update_pulse_info("ITER:test/1", 1, 2, "completed", "x")
        self.assertFalse(result["ok"])
        self.assertIn("server refused", result["error"])


if __name__ == "__main__":
    unittest.main()
