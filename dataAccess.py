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

import access.dataCommon as dc

class DataSource:

    def __init__(self,type=None,name=None):
        self.connected=False
        self.errcode = 0
        self.errdesc = ""
        self.UCR = None
        self.varprefix=None
        self.dtype=""
        self.isSupported=False
        self.connectionString=None
        self.daHandler=None
        if name is None:
           self.name="DS _"+str(id(self))
        else:
            self.name=name
        if type == "CODAC_UDA":
            self.connectionString="host=X,port=3090"
            self.dtype="CODAC_UDA"
        elif type=="IMAS_UDA":
            self.conectionString="database=ITER,path=public,backend=MDSPLUS"
            self.dtype="IMAS_UDA"

    def setConnectionString(self,conninfo):
        self.connectionString=conninfo

        if conninfo.find("host"):
            self.dtype="IMAS_UDA"
        elif conninfo.find("database"):
            self.dtype="CODAC_UDA"

    def setVarPrefix(self,pref):
        self.varprefix=pref

    def connect(self):
        if self.dtype=="IMAS_UDA":
            try:
                self.daHandler=access.imasAccess.IMASDataAccess()
                self.connected=self.daHandler.connectSource(connectionString=self.connectionString)

            except ModuleNotFoundError:
                self.errcode=-1
                self.connected=False

        if self.dtype=="CODAC_UDA":
            try:
                self.daHandler = access.udaAccess.udaAccess()
                print("connect ",self.connectionString)
                self.connected=self.daHandler.connectSource(connectionString=self.connectionString)

            except ModuleNotFoundError:
                self.errcode=-1
                self.connected=False

    def isConnected(self):
        if self.connected:
            return True
        else:
            return False

    @cached(cache=LRUCache(maxsize=100))
    def getData(self,**kwargs):
        dobj=None
        logger.debug("getdata of data source and type %s",self.dtype)
        if self.dtype == "CODAC_UDA":
            try:
                if self.daHandler is None:
                    dobj = dc.DataObj()
                    dobj.setEmpty( "CODAC_UDA_DataHandler is null")
                else:
                    dobj=self.daHandler.getData(**kwargs)
            except ModuleNotFoundError:
                dobj=dc.DataObj()
                dobj.setEmpty("ModuleNotFound_CODAC_UDA")
        if self.dtype== "IMAS_UDA":
            try:
                if self.daHandler is None:
                    dobj = dc.DataObj()
                    dobj.setEmpty( "IMAS_UDA_DataHndler is null")
                else:
                    dobj=self.daHandler.getData(**kwargs)
            except ModuleNotFoundError:
                dobj = dc.DataObj()
                dobj.setEmpty("ModuleNotFound_IMAS_UDA")
        logger.debug("exiting getdata")
        return dobj


    def getEnveloppe(self, **kwargs):
        ret=(None,None)
        if type == "CODAC_UDA":
            try:
                ret= self.daHandler.getEnveloppe(self.UCR, **kwargs)
            except ModuleNotFoundError:
                logger.warning( "ModuleNotFound_CODAC_UDA")

        if type == "IMAS_UDA":
            try:
                ret= self.daHandler.getEnveloppe(self.UCR, **kwargs)
            except ModuleNotFoundError:
                logger.warning("ModuleNotFound_IMAS_UDA")

        return ret



###class to interface with data source - here UDA
class DataAccess:

    def __init__(self,parent=None):
        d= dsc.dataSourceConfig()
        self.proto=d.getSupportedDataSource()
        self.dslist={}
        self.defaultds=None

    def getDefaultDSName(self):
        if self.defaultds is None:
            return "N.P"
        else:
            return self.defaultds.name

    def loadConfig(self):

        dspath=os.environ.get('DATASOURCESCONF') or "mydatasources.cfg"
        dskeys=[]
        dname = ""
        with open(dspath) as f:
            for line in f:

                if line.rstrip().startswith("["):
                    s=line.rstrip()
                    dname=s[s.find("[")+1:s.find("]")]
                    ds= DataSource(name=dname)
                    self.dslist[dname]=ds

                if line.rstrip().startswith("conninfo"):
                    s=line.rstrip().split("=",1)[1]
                    self.dslist[dname].setConnectionString(s)
                if line.rstrip().startswith("varprefix"):
                    s = line.rstrip().split("=",1)[1]
                    logger.debug("found varprefix %s", s)
                    if len(s)==0:
                        if self.defaultds is None:
                            self.defaultds=self.dslist[dname]
                            logger.debug("found a default data source")
                        else:
                            logger.debug("already find a default data source discarding %s ", self.defaultds.name)
                    self.dslist[dname].setVarPrefix(s)
        #print("supported dslist ",self.dslist[0])
        for k, d in self.dslist.items():
            logger.debug("data name=%s data type=%s connfino=%s", d.name, d.dtype, d.connectionString)

            if d.dtype in self.proto:
                d.connect()
                d.isSupported=True
                dskeys.append(d)
            else:
                logger.debug("data source not supported %s", d.name)

        return dskeys






    def addDataSource(self,proto="",dataS=None):
        self.dslist[dataS.name]=dataS

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

                            kwargs["varname"]=s
                            if s is None:
                                dobj = DataObj()
                                dobj.setEmpty("issue when calling data access no varname provided")
                                return dobj
                            logger.debug("varname=%s", s)
                            dobj=self.dslist[dataSName].getData(**kwargs)
                            ##we need to make a copy of the object otherwise if it is in the cache, processing is applied n times..
                            dobjBis = copy.deepcopy(dobj)

                            vm[s]=dobjBis.ydata
                            logger.debug("type %s", dobjBis.ydata.dtype)
                            logger.debug("type %s", type(dobjBis.ydata))

                        ep.substituteExpr(vm)
                        ep.evalExpr()
                        dobjBis.ydata=ep.result

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



