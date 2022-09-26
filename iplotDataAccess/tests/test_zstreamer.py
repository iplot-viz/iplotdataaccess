import numpy as np
# from iplotDataAccess import realTimeStreamer as rtA
import time
import unittest
from iplotDataAccess import dataCommon as dc
import threading
from telnetlib import Telnet
import time
import os, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib
# from iplotDataAccess import udaAccess as ua
import iplotLogging.setupLogger as ls

try:
	import sseclient
except ModuleNotFoundError:
	print("import'sseclient' is not installed")

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
        f = open("/tmp/mylog", 'w')
        loopCnt=0
        ds = "codacuda"
        varname = ["UTIL-HV-S22-BUS1:TOTAL_POWER"]
        x = threading.Thread(name="receiver", target=self.da.startSubscription, args=(ds,), kwargs={'params': varname})
        x.start()
        ts = time.time_ns()
        cnt = 0
        errcnt = 0
        firstT = 0
        time.sleep(5)
        while loopCnt < 50:
            loopCnt = loopCnt+1
            time.sleep(2)
            if cnt > 5 or errcnt > 10:
                break
            dobj = self.da.getNextData(ds, varname[0])
            if len(dobj.xdata) == 0:
                time.sleep(0.1)
                errcnt = errcnt + 1
                print("data is null")
                f.write("data is null ")
                f.write("\n")
                continue
            # we discard first point if too old
            if dobj.xdata[0] < ts:
                f.write("found timestamp less current timestamp ")
                f.write("\n")
                print("found timestamp less than current timestamp %lu", dobj.xdata[0])
                if len(dobj.xdata) == 1:
                    errcnt = errcnt + 1
                    print("dobj has one element")
                    f.write("dobj has one element")
                    f.write("\n")
                else:
                    if cnt == 0:
                        firstT = dobj.xdata[1]
                        print(" cnt=0 first timestamp %d", firstT)
                        f.write("cnt=0 first timestamp")
                        f.write("\n")
            else:
                if cnt == 0:
                    firstT = dobj.xdata[0]
                    logger.info(" first timestamp %d", firstT)
                    f.write("cnt=0 first timestamp, but timestamp is ok")
                    f.write("\n")
            print("vname=%s timestamp %lu and val=%f", varname[0], dobj.xdata[0], dobj.ydata[0])
            f.write("end of block")
            f.write("\n")
            cnt = cnt + 1

        print("end of loop")
        f.write("end of loop")
        f.write("\n")
        self.da.stopSubscription(ds)
        f.write("call to stop subscription")
        f.write("\n")
        x.join(5)

        self.assertEqual(cnt, 6)


if __name__ == "__main__":
    mailServer = "SMTPX.iter.org"
    fromaddr = "bamboo <no-reply@iter.org>"
    toaddr="['lana.abadie@iter.org']"
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = ", ".join(toaddr)
    msg['Subject'] = "bamboo report"
    body="log in case it hangs"
    msg.attach(MIMEText(body, 'plain'))
    unittest.main()
    os.remove("/tmp/mydataconf.cfg")
    with open("/tmp/mylog", "rb") as fil:
        part = MIMEApplication(fil.read(), Name=os.path.basename(resultFile))

    part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(resultFile)
    msg.attach(part)
    server = smtplib.SMTP(mailServer, 25)
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()