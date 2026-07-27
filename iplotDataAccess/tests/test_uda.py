import unittest
from unittest.mock import MagicMock
import numpy as np
import inspect
import os
import tempfile
import iplotDataAccess
from iplotDataAccess.dataAccess import DataAccess

dscfg = """{
    "codacuda": {
        "type": "CODAC_UDA",
        "host": "io-ls-udasrv1.iter.org",
        "port": 3090,
        "rturl": "https://controls.iter.org/dashboard/backend/sse",
        "rtheaders": "REMOTE_USER:$USERNAME,User-Agent:python_client",
        "rtauth": null,
        "default": true
    }
}
"""


class TestUDAAccess(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.da = DataAccess()
        self.ds = "codacuda"
        print(os.environ.get('PWD'))

        print(dir(iplotDataAccess))
        print(dir(__builtins__))
        with open('/tmp/mydataconf.cfg', mode='w') as fp:
            fp.write(dscfg)
            fp.seek(0)
            os.environ.update({'DATASOURCESCONF': os.path.abspath(fp.name)})

        ##print(os.environ.get('DATASOURCESCONF'))
        ##with open('/tmp/mydataconf.cfg') as f:
        ##    print( f.readlines())

        print(os.environ.get('PYTHONPATH'))
        try:
            load = self.da.load_config()
        except Exception as exc:
            self.skipTest(f"CODAC UDA data source not available: {exc}")

        if not load:
            self.skipTest("CODAC UDA data source not available")

    def test_UDAAccessISO(self) -> None:
        dobj = self.da.get_data(self.ds, varname="BUIL-SYSM-COM-4503-BU:SRV6101-NSBPS", tsS="2022-05-04T12:30:00",
                                tsE="2022-05-05T12:30:00", nbp=-1)
        self.assertEqual(len(dobj.xdata), 56507)
        self.assertAlmostEqual(np.amin(dobj.ydata), 6.27)
        self.assertAlmostEqual(np.amax(dobj.ydata), 833.252)

    def test_UDAAccessNano(self) -> None:
        dobj = self.da.get_data(self.ds, varname="BUIL-SYSM-COM-4503-BU:SRV6101-NSBPS", tsS="1651667400000000000",
                                tsE="1651753797000000000", nbp=-1)
        self.assertEqual(len(dobj.xdata), 56506)
        self.assertAlmostEqual(np.amin(dobj.ydata), 6.27)
        self.assertAlmostEqual(np.amax(dobj.ydata), 833.252)

    def test_UDAAccessInvVar(self) -> None:
        dobj = self.da.get_data(self.ds, varname="BUIL-SYSM-COM-XX03-BU:SRV6101-NSBPS", tsS="1651667400000000000",
                                tsE="1651753797000000000", nbp=-1)
        self.assertEqual(len(dobj.xdata), 0)

    def test_UDAAccessNoData(self) -> None:
        dobj = self.da.get_data(self.ds, varname="UTIL-HV-M1:TS2000-QT01", tsS="2022-06-14T02:26:02",
                                tsE="2022-06-14T12:26:06", nbp=-1)
        self.assertEqual(len(dobj.xdata), 0)

    def test_UDAAccessByPulse(self) -> None:
        dobj = self.da.get_data(self.ds, varname="UTIL-HV-M1:TS2000-QT01",
                                pulse="ITER:CWS-SCSU-BASIN-FILL-TESTS/130124",
                                tsS="0.0", tsE=None, nbp=-1, tsFormat="relative")
        self.assertEqual(len(dobj.xdata), 8)
        self.assertEqual(dobj.xunit, "s")

    def test_UDAAccessByPulseWithTime(self) -> None:
        dobj = self.da.get_data(self.ds, varname="UTIL-HV-M1:TS2000-QT01",
                                pulse="ITER:CWS-SCSU-BASIN-FILL-TESTS/130124",
                                tsS="172800", tsE="432000", nbp=-1, tsFormat="relative")
        self.assertEqual(len(dobj.xdata), 1)

        self.assertEqual(dobj.xunit, "s")


class TestUDAConfigParsing(unittest.TestCase):
    # Construction only reads the config, so these run without a live UDA server.
    def _make(self, config):
        try:
            from iplotDataAccess.udaAccess import UdaAccess
        except ImportError as exc:
            self.skipTest(f"uda_client_reader not available: {exc}")
        return UdaAccess("codacuda", config)

    def test_uda_for_export_present(self) -> None:
        ds = self._make({"host": "srv1", "port": 3090, "uda_for_export": "srv2"})
        self.assertEqual(ds.uda_for_export, "srv2")

    def test_uda_for_export_defaults_to_none(self) -> None:
        ds = self._make({"host": "srv1", "port": 3090})
        self.assertIsNone(ds.uda_for_export)


class TestArchiveWindowFallback(unittest.TestCase):
    """get_archive_window overflow fallback, mocked — no live server needed."""

    _TOO_MANY = ('Number of samples in reply exceeds available limit. '
                 'Reduce request interval, use decimation or read data by chunks.')

    def _make(self):
        try:
            from iplotDataAccess.udaAccess import UdaAccess
        except ImportError as exc:
            self.skipTest(f"uda_client_reader not available: {exc}")
        ds = UdaAccess("codacuda", {"host": "srv1", "port": 3090})
        ds.get_data = MagicMock()
        ds.get_envelope = MagicMock(return_value="envelope")
        return ds

    def test_overflow_keeps_the_callers_point_budget(self):
        ds = self._make()
        ds.get_data.return_value = MagicMock(errcode=-1, errdesc=self._TOO_MANY)
        out = ds.get_archive_window(varname='v', nbp=10_000, env_nbp=10_000)
        self.assertEqual(out, "envelope")
        self.assertEqual(ds.get_envelope.call_args.kwargs['nbp'], 10_000)

    def test_overflow_defaults_to_the_coarse_envelope(self):
        from iplotDataAccess.udaAccess import ENVELOPE_TARGET_POINTS
        ds = self._make()
        ds.get_data.return_value = MagicMock(errcode=-1, errdesc=self._TOO_MANY)
        ds.get_archive_window(varname='v', nbp=100_000)
        self.assertEqual(ds.get_envelope.call_args.kwargs['nbp'],
                         ENVELOPE_TARGET_POINTS)

    def test_env_nbp_is_not_forwarded_to_the_raw_read(self):
        ds = self._make()
        ds.get_data.return_value = MagicMock(errcode=0)
        ds.get_archive_window(varname='v', nbp=5, env_nbp=7)
        self.assertNotIn('env_nbp', ds.get_data.call_args.kwargs)
        ds.get_envelope.assert_not_called()


if __name__ == "__main__":
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
