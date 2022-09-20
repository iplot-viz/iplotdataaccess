import unittest
import numpy as np

import os
import tempfile

from iplotDataAccess.dataAccess import DataAccess

dscfg = """[imasuda]
conninfo=database=iter,path=public,backend=MDSPLUS
varprefix=
"""

class TestUDAAccess(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.da = DataAccess()
        self.ds = "imasuda"
        with open('/tmp/mydataconf.cfg',mode='w') as fp:
            fp.write(dscfg)
            fp.seek(0)
            os.environ.update({'DATASOURCESCONF': os.path.abspath(fp.name)})
        if len(self.da.loadConfig()) < 1:
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
        self.assertEqual(dobj.xunit, "s")
    def test_IMASHeterogenousTimestamp(self)->None:
        dobj = self.da.getData(self.ds, varname="pulse_schedule/ec/launcher(0)/power/reference/data", pulse="105023/1",nbp=-1)
        self.assertEqual(len(dobj.xdata), 6)
        self.assertEqual(dobj.xunit, "s")

    def test_ProfileData1(self)->None:
        dobj = self.da.getData(self.ds, varname="core_profiles/profiles_1d[1]/electrons/temperature", pulse="134174/117",
                               nbp=-1)
        self.assertEqual(len(dobj.xdata), 299)
        self.assertEqual(len(dobj.ydata), 299)
    def test_ProfileData2(self)->None:
        dobj = self.da.getData(self.ds, varname="core_profiles/profiles_1d[1]/grid/rho_tor_norm",
                               pulse="134174/117",
                               nbp=-1)
        self.assertEqual(len(dobj.xdata), 299)
        self.assertEqual(len(dobj.ydata), 299)



if __name__ == "__main__":
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
