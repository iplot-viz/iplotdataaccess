import numpy as np
# from iplotDataAccess import realTimeStreamer as rtA
import time
import unittest
from iplotDataAccess import dataCommon as dc
import threading
from telnetlib import Telnet
import time
import os
# from iplotDataAccess import udaAccess as ua
import iplotLogging.setupLogger as ls

# from iplotDataAccess import realTimeStreamer as rtA
from iplotDataAccess.dataAccess import DataAccess

dscfg = """[codacuda]
conninfo=host=10.153.200.61,port=3090
varprefix=
rturl=http://io-ls-udaweb1.iter.org/dashboard/backend/sse
rtheaders=REMOTE_USER:$USERNAME,User-Agent:python_client
rtauth=None
"""

logger = ls.get_logger(__name__)
class TestUDAAccess(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.da = DataAccess()
        self.ds = "codacuda"
        print(os.environ.get('PWD'))

        #print(dir(iplotDataAccess))
        print(dir(__builtins__))
        with open('/tmp/mydataconf.cfg', mode='w') as fp:
            fp.write(dscfg)
            fp.seek(0)
            os.environ.update({'DATASOURCESCONF': os.path.abspath(fp.name)})

        ##print(os.environ.get('DATASOURCESCONF'))
        ##with open('/tmp/mydataconf.cfg') as f:
        ##    print( f.readlines())

        print(os.environ.get('PYTHONPATH'))
        if len(self.da.loadConfig()) < 1:
            print("Invalid data source")
            return None



    def test_Streamer(self) -> None:

        ds = "codacuda"
        varname = ["UTIL-HV-S22-BUS1:TOTAL_POWER"]
        x = threading.Thread(name="receiver", target=self.da.startSubscription, args=(ds,), kwargs={'params': varname})

        x.start()
        ts = time.time_ns()
        cnt = 0
        errcnt = 0
        firstT = 0
        time.sleep(5)
        while True:
            time.sleep(2)
            dobj = self.da.getNextData(ds, varname[0])
            if len(dobj.xdata) == 0:
                time.sleep(0.1)
                errcnt = errcnt + 1
                print("data is null")
                continue
            # we discard first point if too old
            if dobj.xdata[0] < ts:
                if len(dobj.xdata) == 1:
                    continue
                else:
                    if cnt == 0:
                        firstT = dobj.xdata[1]
                        print(" cnt=0 first timestamp %d", firstT)
            else:
                if cnt == 0:
                    firstT = dobj.xdata[0]
                    logger.info(" first timestamp %d", firstT)
            print("vname=%s timestamp %lu and val=%f", varname[0], dobj.xdata[0], dobj.ydata[0])

            cnt = cnt + 1
            if cnt > 10 or errcnt > 20:
                break
        print("end of loop")
        self.da.stopSubscription(ds)
        x.join()

        self.assertEqual(cnt, 11)


if __name__ == "__main__":
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")