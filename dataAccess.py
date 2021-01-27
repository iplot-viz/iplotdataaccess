import sys

import os
import copy
from cachetools import cached, LRUCache, TTLCache
import access.dataSourceConfig as dsc
from access.dataCommon import DataObj
from proc.basicProcessing import exprProcessing, ProcParsingException
import log.setupLogger as ls

logger = ls.get_logger(__name__)

##should import possible data sources like IMAS UDA and CODAC UDA
try:
    import imas
    import access.imasAccess
except ModuleNotFoundError:
    logger.warning("import 'imas client' is not installed")

try:
    import uda_client_reader
    import access.udaAccess
except ModuleNotFoundError:
    logger.warning("import'uda client' is not installed")

try:
    import access.realTimeStreamer
except ModuleNotFoundError:
    logger.warning("import'uda RT streamer' is not installed")

import access.dataCommon as dc


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
        if name is None:
            self.name = "DS _" + str(id(self))
        else:
            self.name = name
        if type == "CODAC_UDA":
            self.connectionString = "host=X,port=3090"
            self.dtype = "CODAC_UDA"
        elif type == "IMAS_UDA":
            self.conectionString = "database=ITER,path=public,backend=MDSPLUS"
            self.dtype = "IMAS_UDA"

    def setConnectionString(self, conninfo):
        self.connectionString = conninfo
        if conninfo.find("host"):
            self.dtype = "IMAS_UDA"
        elif conninfo.find("database"):
            self.dtype = "CODAC_UDA"

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
            self.RTHandler = access.realTimeStreamer.RTStreamer(url=self.rtu, headers=myhd, auth=self.rta)
            self.rterrcode = 0
            self.rtStatus = "INITIALISED"
        except ModuleNotFoundError:
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"



    def connect(self):
        if self.dtype == "IMAS_UDA":
            try:
                self.daHandler=access.imasAccess.IMASDataAccess()
                self.connected=self.daHandler.connectSource(connectionString=self.connectionString)
            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        if self.dtype == "CODAC_UDA":
            try:
                self.daHandler = access.udaAccess.udaAccess()
                logger.info("connect %s ", self.connectionString)
                self.connected = self.daHandler.connectSource(connectionString=self.connectionString)

            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        if self.rtu is not None:
            try:
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

    def startSubscription (self,**kwargs):
        if self.rtStatus == "INITIALIZED" or self.rtStatus == "STOPPED":
            try:
                self.rtStatus == "STARTED"
                self.RTHandler.startSubscription(**kwargs)
            except access.realTimeStreamer.RTStreamerException as rtse:
                self.rtStatus = "ERROR"
                self.rterrcode = -2


    def stopSubscription (self):
        if self.rtStatus == "STARTED":
            try:

                self.RTHandler.stopSubscription(**kwargs)
                self.rtStatus == "STOPPED"
            except access.realTimeStreamer.RTStreamerException as rtse:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def getNextData (self, vname=None):
        return self.RTHandler.getNextData(vname)


    @cached(cache=LRUCache(maxsize=100))
    def getData(self, **kwargs):
        dobj=None
        logger.debug("getdata of data source and type %s",self.dtype)

        try:
            if self.daHandler is None:
                dobj = dc.DataObj()
                dobj.setEmpty( self.dtype+"_DataHandler is null")
            else:
                dobj=self.daHandler.getData(**kwargs)
        except ModuleNotFoundError:
                dobj=dc.DataObj()
                dobj.setEmpty("ModuleNotFound_"+self.dtype)
        logger.debug("exiting getdata")
        return dobj

    def getEnveloppe (self, **kwargs):
        ret = (None, None)
        try:
            ret= self.daHandler.getEnveloppe(self.UCR, **kwargs)
        except ModuleNotFoundError:
            logger.warning("ModuleNotFound_%s", self.dtype)
        return ret



###class to interface with data source - here UDA
class DataAccess:

    def __init__(self, parent=None):
        d= dsc.dataSourceConfig()
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
                    dname = s[s.find("[")+1:s.find("]")]
                    ds = DataSource(name=dname)
                    self.dslist[dname] = ds

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


                if line.rstrip().startswith("varprefix"):
                    s = line.rstrip().split("=", 1)[1]
                    logger.debug("found varprefix %s", s)
                    if len(s) == 0:
                        if self.defaultds is None:
                            self.defaultds = self.dslist[dname]
                            logger.debug("found a default data source")
                        else:
                            logger.debug("already find a default data source discarding %s ", self.defaultds.name)
                    self.dslist[dname].setVarPrefix(s)

        #print("supported dslist ",self.dslist[0])
        for k, d in self.dslist.items():
            logger.debug("data name=%s data type=%s connfino=%s", d.name, d.dtype, d.connectionString)

            if d.dtype in self.proto:
                d.connect()
                d.isSupported = True
                dskeys.append(d)
            else:
                logger.debug("data source not supported %s", d.name)
        return dskeys

    def addDataSource(self, proto="", dataS=None):
        self.dslist[dataS.name] = dataS

    def connect(self,dataSName):
        for ds in self.dslist:
            if ds.name == dataSName:
                return ds.connect()
        return None

    def getData(self,dataSName,**kwargs):
        ##we can use the varprefix to get the data source while we introduce
        if dataSName is not None and dataSName in self.dslist.keys():
            if self.dslist[dataSName] is None:
                dobj = DataObj()

                dobj.setEmpty("Invalid data source pointer for ds name " + dataSName)

                return dobj
            else:
                ep=exprProcessing()
                myexpr=kwargs.get("varname")
                logger.debug ("myexprZZ=%s", myexpr)
                ##we set expression and it is compiled
                try:
                    ep.setExpr(myexpr)
                    if ep.isExpr:
                        vm={}
                        for s in ep.vardict.keys():

                            kwargs["varname"] = s
                            if s is None:
                                dobj = DataObj()
                                dobj.setEmpty("issue when calling data access no varname provided")
                                return dobj
                            logger.debug("varname=%s", s)
                            dobj=self.dslist[dataSName].getData(**kwargs)
                            ##we need to make a copy of the object otherwise if it is in the cache, processing is applied n times..
                            dobjBis = copy.deepcopy(dobj)

                            vm[s]=dobjBis.ydata
                            if len(dobjBis.ydata) > 0:
                                logger.debug("type %s", dobjBis.ydata.dtype)
                                logger.debug("type %s", type(dobjBis.ydata))

                        ep.substituteExpr(vm)
                        ep.evalExpr()
                        dobjBis.ydata = ep.result

                        return dobjBis
                    else:
                        return self.dslist[dataSName].getData(**kwargs)

                except ProcParsingException:
                    logger.warning("parsing exception ")
                    dobj = DataObj()
                    dobj.setEmpty("Invalid expression " + myexpr)
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

    def stopSubscription(self):
        if dataSName is not None and dataSName in self.dslist.keys():
            self.dslist[dataSName].stopSubscription()

    def getNextData(self, dataSName, vname):
        if dataSName is not None and dataSName in self.dslist.keys():
            return self.dslist[dataSName].getNextData(vname)
        else:
            dobj = DataObj()
            dobj.setEmpty("Invalid data source name " + dataSName)
            return dobj


    def getEnveloppe(self,dataSName,**kwargs):
        if dataSName is not None and dataSName in self.dslist.keys():
            if self.dslist[dataSName] is None:
                dobj=DataObj()
                dobj.setEmpty("Invalid data source pointer for ds name "+dataSName)
                return dobj
            else:
                return self.dslist[dataSName].getEnveloppe(**kwargs)
        else:
            if dataSName not in self.dslist.keys():
                logger.warning("Invalid data source found %s ",dataSName)
                dobj = DataObj()
                dobj.setEmpty("Invalid data source name " + dataSName)
                return dobj
            if self.defaultds is not None:
                logger.info("default source used ")
                return self.defaultds.getEnveloppe(**kwargs)

        return None



