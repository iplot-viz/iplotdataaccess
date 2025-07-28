import unittest
import numpy as np

import os
import tempfile

from iplotDataAccess.dataAccess import DataAccess

dscfg = """[imaspy]
type=IMASPY
database=iter
path=public
backend=MDSPLUS
"""

class TestUDAAccess(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.da = DataAccess()
        self.ds = "imaspy"
        with open('/tmp/mydataconf.cfg',mode='w') as fp:
            fp.write(dscfg)
            fp.seek(0)
            os.environ.update({'DATASOURCESCONF': os.path.abspath(fp.name)})
        if self.da.loadConfig()== False:
            print("Invalid data source")
            return None

    def test_IMASAccessInvVar(self)-> None:
        dobj=self.da.getData(self.ds,varname="BUIL-SYSM-COM-XX03-BU:SRV6101-NSBPS",pulse="130012/2",nbp=-1)
        self.assertEqual(len(dobj.xdata),0)

    def test_IMASAccessNoData(self)-> None:
        dobj=self.da.getData(self.ds,varname="UTIL-HV-M1:TS2000-QT01",pulse="12/4",nbp=-1)
        self.assertEqual(len(dobj.xdata),0)

    def test_IMASAccessByPulse(self)-> None:
        dobj=self.da.getData(self.ds,varname="summary/fusion/power/value",pulse="130012/2",nbp=-1)
        self.assertEqual(len(dobj.xdata),108)
        self.assertEqual(dobj.xunit, "s")

    def test_IMASAccessByPulseWithTime(self)-> None:
        dobj=self.da.getData(self.ds,varname="summary/fusion/power/value",pulse="130012/2",tsS="5",tsE="20",nbp=-1)
        self.assertEqual(len(dobj.xdata),4)
        self.assertEqual(len(dobj.ydata), 4)
        self.assertEqual(dobj.xunit, "s")
    def test_IMASHeterogenousTimestamp(self)->None:
        dobj = self.da.getData(self.ds, varname="pulse_schedule/ec/launcher(0)/power/reference/data", pulse="105023/1",nbp=-1)
        self.assertEqual(len(dobj.xdata), 6)
        self.assertEqual(dobj.xunit, "s")
    def test_IMASAccessByPulseContourData(self)-> None:
        dobj1=self.da.getData(self.ds,varname="equilibrium/time_slice/profiles_2d(0)/psi",pulse="135011/7",nbp=-1)
        self.assertEqual(dobj1.ydata.shape,(129, 65, 986))
        self.assertEqual(dobj1.yunit, "Wb")
        dobj2 = self.da.getData(self.ds, varname="core_profiles/profiles_1d/electrons/temperature", pulse="135011/7", nbp=-1)
        self.assertEqual(dobj2.ydata.shape, (50, 986))
        self.assertEqual(dobj2.yunit, "eV")
        dobj = self.da.getData(self.ds, varname="core_profiles/profiles_1d/electrons/temperature",tsS="5",tsE="20", pulse="135011/7",nbp=-1)
        self.assertEqual(dobj.ydata.shape, (15, 986))
        self.assertEqual(dobj.yunit, "eV")

if __name__ == "__main__":
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
