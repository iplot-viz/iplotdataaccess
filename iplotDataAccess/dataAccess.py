import copy
import os
import time


import iplotDataAccess.dataSourceConfig as dsc
import iplotLogging.setupLogger as ls
from iplotDataAccess.dataCommon import DataObj, DataEnvelope

logger = ls.get_logger(__name__)

##should import possible data sources like IMAS UDA and CODAC UDA
try:
    import imas
    import iplotDataAccess.imasAccess
except ModuleNotFoundError:
    logger.warning("import 'imas client' is not installed")

try:
    import uda_client_reader
    import iplotDataAccess.udaAccess
except ModuleNotFoundError:
    logger.warning("import'uda client' is not installed")

try:
    import iplotDataAccess.realTimeStreamer
except ModuleNotFoundError:
    logger.warning("import'uda RT streamer' is not installed")

import iplotDataAccess.dataCommon as dc


class RTHException(Exception):
    pass


class DataSource:

    def __init__(self, type=None, name=None):
        self.connected = False
        self.rtStatus = "UNEXISTING"
        self.errcode = 0
        self.rterrcode = 0
        self.errdesc = ""
        self.UCR = None
        self.varprefix = None
        self.dtype = ""
        self.isSupported = False
        self.connectionString = None
        self.daHandler = None
        self.RTHandler = None
        self.rth = None
        self.rta = None
        self.rtu = None
        self.MAX_ITER = 1000
        self.SLEEP_TO = 0.1
        if name is None:
            self.name = "DS _" + str(id(self))
        else:
            self.name = name
        if type == "CODAC_UDA":
            self.connectionString = "host=X,port=3090"
            self.dtype = "CODAC_UDA"
        elif type == "IMAS_UDA":
            self.connectionString = "database=ITER,path=public,backend=MDSPLUS"
            self.dtype = "IMAS_UDA"

    def setConnectionString(self, conninfo):
        self.connectionString = conninfo
        if "host" in conninfo:
            self.dtype = "CODAC_UDA"
        elif "database" in conninfo:
            self.dtype = "IMAS_UDA"

    def setVarPrefix(self, pref):
        self.varprefix = pref

    def setRTHeaders(self, headers):
        self.rth = headers

    def setRTAuth(self, auth):
        self.rta = auth

    def setRTUrl(self, url):
        self.rtu = url

    def setRTHandler(self):
        myhd = {}
        if self.dtype == "IMAS_UDA":
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"
            raise RTHException("Real Time Handler is not supported")

        if self.rth is not None:
            sd = self.rth.split(",")
            for i in range(len(sd)):
                entry = sd[i].split(":")
                if len(entry) != 2:
                    self.rterrcode = -1
                    self.rtStatus = "UNEXISTING"
                    raise RTHException("Invalid entry except 2 elements")
                myhd[entry[0]] = entry[1]
        try:
            self.RTHandler = iplotDataAccess.realTimeStreamer.RTStreamer(url=self.rtu, headers=myhd, auth=self.rta, udaA=self.daHandler)
            self.rterrcode = 0
            self.rtStatus = "INITIALISED"
            logger.debug("real time setRTHandler OK %s head=%s auth=%s ", self.rtu, myhd, self.rta)
        except ModuleNotFoundError:
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"
        except AttributeError:
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"

    def connect(self):
        if self.dtype == "IMAS_UDA":
            try:
                self.daHandler = iplotDataAccess.imasAccess.IMASDataAccess()
                self.connected = self.daHandler.connectSource(connectionString=self.connectionString)
            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        if self.dtype == "CODAC_UDA":
            try:
                self.daHandler = iplotDataAccess.udaAccess.udaAccess()
                logger.info("connect %s ", self.connectionString)
                self.connected = self.daHandler.connectSource(connectionString=self.connectionString)

            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        if self.rtu is not None:
            try:
                logger.debug("setRHandler")
                self.setRTHandler()
            except RTHException as rte:
                logger.error(" RTHException %s ", rte)

    def isConnected(self):
        if self.connected:
            return True
        else:
            return False

    def getRTStatus(self):
        return self.rtStatus

    def startSubscription(self, **kwargs):
        for _ in range(20):  # Time to update real status if it is STARTED
            if self.rtStatus != "STARTED":
                break
            time.sleep(0.1)
        if self.rtStatus in ["STARTED", "STOPPED"]:
            for _ in range(60):  # Wait for real status
                if self.rtStatus == self.RTHandler.getStatus():
                    break
                logger.debug('Waiting status sync for RTHandler')
                time.sleep(1)
        if self.rtStatus in ["INITIALISED", "STOPPED"]:
            try:
                self.rtStatus = "STARTED"
                logger.debug("startSubscription ")
                newparams = kwargs.get("params")

                kwargs["origparams"] = copy.deepcopy(kwargs.get("params"))
                kwargs["params"] = newparams
                logger.debug("start sub with params=%s and origparams=%s", kwargs["params"], kwargs["origparams"])
                self.RTHandler.startSubscription(**kwargs)
            except iplotDataAccess.realTimeStreamer.RTStreamerException as rtse:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def stopSubscription(self):
        logger.debug("stopSubscription Y %s ", self.rtStatus)
        if self.rtStatus == "STARTED":
            try:
                logger.debug("stopSubscription Z ")
                self.RTHandler.stopSubscription()
                self.rtStatus = "STOPPED"
            except iplotDataAccess.realTimeStreamer.RTStreamerException as rtse:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def getNextData(self, vname=None):
        counter = 0
        # Could happen that params is null if this call is done before startSubscription
        while (self.RTHandler is None or self.RTHandler.params is None) and counter < self.MAX_ITER:
            time.sleep(self.SLEEP_TO)
            counter = counter + 1
        if counter == self.MAX_ITER:
            dobj = dc.DataObj()
            dobj.setEmpty("Streamer not properly initialized: did the subscription start?")
            return dobj

        varnames = self.RTHandler.params[self.RTHandler.params.find("=") + 1:-1]
        varnames = varnames.split(',')
        if vname in varnames:
            dobj = self.RTHandler.getNextData(vname)
            logger.debug("type of data %s and len %d and unit %s ", type(dobj.ydata), len(dobj.ydata), dobj.yunit)
            return dobj
        else:
            return self.RTHandler.getNextData(vname)

    
    def __getDataI(self, **kwargs):
        return self.daHandler.getData(**kwargs)

    def getData(self, **kwargs):
        dobj = None
        logger.debug("getdata of data source and type %s", self.dtype)

        try:
            if self.daHandler is None:
                dobj = dc.DataObj()
                dobj.setEmpty(self.dtype + "_DataHandler is null")
            else:
                varname = kwargs.get("varname")
                logger.debug(f"varname: {varname}")
                dobj = self.__getDataI(**kwargs)

                if dobj.ydata is not None and len(dobj.ydata) > 0:
                    logger.debug(f"dtype: {dobj.ytype}")
                    logger.debug(f"actual dtype: {type(dobj.ydata)}")

        except ModuleNotFoundError:
            dobj = dc.DataObj()
            dobj.setEmpty("ModuleNotFound_" + self.dtype)
        logger.debug("exiting getdata")
        return dobj

    
    def __getEnvelopeI(self, **kwargs):
        return self.daHandler.getEnvelope(**kwargs)

    def getEnvelope(self, **kwargs):
        ret = (None, None)
        try: 
            if self.daHandler is None:
                dobj = dc.DataEnvelope()
                dobj.setEmpty(self.dtype + "_DataHandler is null")
            else:
                varname = kwargs.get("varname")
                logger.debug(f"varname: {varname}")
                ret = self.__getEnvelopeI(**kwargs)
                

                if ret.errcode==0 and ret.xdata is not None and len(ret.xdata) > 0:
                    logger.debug(f"dtype: {ret.ytype}")
                    logger.debug(f"actual dtype: {type(ret.ydata_min)}")

        except ModuleNotFoundError:
            logger.warning("ModuleNotFound_%s", self.dtype)
        return ret


###class to interface with data source - here UDA
class DataAccess:

    def __init__(self, parent=None):
        d = dsc.dataSourceConfig()
        self.proto = d.getSupportedDataSource()
        self.dslist = {}
        self.defaultds = None

    def getDefaultDSName(self):
        if self.defaultds is None:
            return "N.P"
        else:
            return self.defaultds.name

    def loadConfig(self):

        dspath = os.environ.get('DATASOURCESCONF') or "mydatasources.cfg"
        dskeys = []
        dname = ""
        with open(dspath) as f:
            for line in f:

                if line.rstrip().startswith("["):
                    s = line.rstrip()
                    dname = s[s.find("[") + 1:s.find("]")]
                    ds = DataSource(name=dname)
                    self.dslist[dname] = ds
                    if self.defaultds is None:
                        self.defaultds = self.dslist[dname]

                if line.rstrip().startswith("conninfo"):
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].setConnectionString(s)
                if line.rstrip().startswith("rturl"):
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].setRTUrl(s)
                if line.rstrip().startswith("rtauth"):
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].setRTAuth(s)
                if line.rstrip().startswith("rtheaders"):
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].setRTHeaders(s)
                if line.rstrip().startswith("default"):
                    s = line.rstrip().split("=", 1)[1]
                    if s.lower() == 'true':
                        if self.defaultds is None:
                            self.defaultds = self.dslist[dname]
                            logger.debug("found a default data source")

                if line.rstrip().startswith("varprefix"):
                    s = line.rstrip().split("=", 1)[1]
                    logger.debug("found varprefix %s", s)
                    self.dslist[dname].setVarPrefix(s)

        # print("supported dslist ",self.dslist[0])
        for k, d in self.dslist.items():
            logger.info("data name=%s data type=%s connfino=%s", d.name, d.dtype, d.connectionString)

            if d.dtype in self.proto:
                d.connect()
                d.isSupported = True
                dskeys.append(d)
            else:
                logger.info("data source not supported %s", d.name)
        return dskeys

    def addDataSource(self, proto="", dataS=None):
        self.dslist[dataS.name] = dataS

    def connect(self, dataSName):
        for ds in self.dslist:
            if ds.name == dataSName:
                return ds.connect()
        return None

    def getData(self, dataSName, **kwargs):
        ##we can use the varprefix to get the data source while we introduce
        logger.debug("entering getdata  %s", dataSName)
        if dataSName is not None and dataSName in self.dslist.keys():
            if self.dslist[dataSName] is None:
                dobj = DataObj()

                dobj.setEmpty("Invalid data source pointer for ds name " + dataSName)
                logger.debug("Invalid data source pointer for ds name  %s", dataSName)
                return dobj
            else:

                dobj = self.dslist[dataSName].getData(**kwargs)
                return dobj
        else:
            if dataSName not in self.dslist.keys():
                logger.warning(" Invalid data source found %s ", dataSName)
                dobj = DataObj()
                dobj.setEmpty("Invalid data source name " + dataSName)

                return dobj
            if self.defaultds is not None:
                logger.info(" default source used ")
                return self.defaultds.getData(**kwargs)

        return None

    def startSubscription(self, dataSName, **kwargs):
        if dataSName is not None and dataSName in self.dslist.keys():
            self.dslist[dataSName].startSubscription(**kwargs)

    def stopSubscription(self, dataSName):
        if dataSName is not None and dataSName in self.dslist.keys():
            logger.debug("stopSubscription A ")
            self.dslist[dataSName].stopSubscription()

    def getNextData(self, dataSName, vname):
        if dataSName is not None and dataSName in self.dslist.keys():
            return self.dslist[dataSName].getNextData(vname)
        else:
            dobj = DataObj()
            dobj.setEmpty("Invalid data source name " + dataSName)
            return dobj

    def getEnvelope(self, dataSName, **kwargs):
        if dataSName is not None and dataSName in self.dslist.keys():
            if self.dslist[dataSName] is None:
                denv = DataEnvelope()
                denv.setEmpty("Invalid data source pointer for ds name " + dataSName)
                
                return denv
            else:
                return self.dslist[dataSName].getEnvelope(**kwargs)
        else:
            if dataSName not in self.dslist.keys():
                logger.warning("Invalid data source found %s ", dataSName)
                denv = DataEnvelope()
                denv.setEmpty("Invalid data source name " + dataSName)
               
                return denv
            if self.defaultds is not None:
                logger.info("default source used ")
                return self.defaultds.getEnvelope(**kwargs)

        return None
