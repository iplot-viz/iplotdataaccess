import numpy as np
# from iplotDataAccess import realTimeStreamer as rtA
import time
import unittest
from iplotDataAccess import dataCommon as dc
import threading
import time
import os, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib
# from iplotDataAccess import udaAccess as ua
import iplotLogging.setupLogger as ls

# from iplotDataAccess import realTimeStreamer as rtA
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

logger = ls.get_logger(__name__)


class TestRTAccess(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        # print(os.environ.get('PYTHONPATH'))
        # pintel = os.environ.get('PWD') + "/iplotDataAccess_intel/lib/python3.8/site-packages"
        # pfoss = os.environ.get('PWD') + "/iplotDataAccess_foss/lib/python3.8/site-packages"
        # if os.path.exists(pintel):
        #   path1 = os.environ.get('PYTHONPATH') + ":" + pintel
        # else:
        #   path1 = os.environ.get('PYTHONPATH') + ":" + pfoss
        # os.environ.update({'PYTHONPATH': path1})
        # print(os.environ.get('PYTHONPATH'))
        self.da = DataAccess()
        self.ds = "codacuda"
        print(os.environ.get('PWD'))

        # print(dir(iplotDataAccess))
        print(dir(__builtins__))
        with open('/tmp/mydataconf.cfg', mode='w') as fp:
            fp.write(dscfg)
            fp.seek(0)
            os.environ.update({'IPLOT_SOURCES_CONFIG': os.path.abspath(fp.name)})

        ##print(os.environ.get('DATASOURCESCONF'))
        ##with open('/tmp/mydataconf.cfg') as f:
        ##    print( f.readlines())

        try:
            load = self.da.load_config()
        except Exception as exc:
            self.skipTest(f"CODAC UDA data source not available: {exc}")

        if not load:
            self.skipTest("CODAC UDA data source not available")

    def test_Streamer(self) -> None:
        f = open("/tmp/mylog", 'w')
        loopCnt = 0
        ds = "codacuda"
        varname = ["UTIL-HV-S22-BUS1:TOTAL_POWER"]
        f.write("before thread dcreation")

        x = threading.Thread(name="receiver", target=self.da.start_subscription, args=(ds,), kwargs={'params': varname})
        f.write("before starting the thread")
        x.start()
        ts = time.time_ns()
        cnt = 0
        errcnt = 0
        firstT = 0
        f.write("before sleep")

        time.sleep(5)
        while loopCnt < 25:
            loopCnt = loopCnt + 1
            dobj = self.da.get_next_data(ds, varname[0])
            if len(dobj.xdata) == 0:
                # time.sleep(0.1)
                errcnt = errcnt + 1
                # print("data is null")
                f.write("data is null ")
                f.write("\n")

                # we discard first point if too old
            else:
                logger.info("vname=%s timestamp %lu and val=%f", varname[0], dobj.xdata[0], dobj.ydata[0])
                f.write("end of block")
                f.write("\n")
                cnt = cnt + 1
        #   time.sleep(2)
        logger.info("end of loop")
        f.write("end of loop")
        f.write("\n")

        self.da.stop_subscription(ds)
        f.write("call to stop subscription")
        f.write("\n")
        f.close()
        x.join(5)

        self.assertGreater(cnt, 2)


if __name__ == "__main__":
    mailServer = "SMTPX.iter.org"
    fromaddr = "bamboo <no-reply@iter.org>"
    toaddr = "['lana.abadie@iter.org']"
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = ", ".join(toaddr)
    msg['Subject'] = "bamboo report"
    body = "log in case it hangs"
    msg.attach(MIMEText(body, 'plain'))
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
    # with open("/tmp/mylog", "rb") as fil:
    #    part = MIMEApplication(fil.read(), Name=os.path.basename(resultFile))

    # part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(resultFile)
    # msg.attach(part)
    # server = smtplib.SMTP(mailServer, 25)
    # text = msg.as_string()
    # server.sendmail(fromaddr, toaddr, text)
    # server.quit()
