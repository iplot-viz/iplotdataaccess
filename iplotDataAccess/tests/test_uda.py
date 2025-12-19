import unittest
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


if __name__ == "__main__":
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
