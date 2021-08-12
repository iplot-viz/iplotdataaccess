
import re
import numpy as np
import imas
from iplotDataAccess.dataCommon import DataObj,DataType
import iplotLogging.setupLogger as ls

logger = ls.get_logger(__name__)


class IMASDataAccess:
    database='iter'
    user_or_path='public'
    imas_backend=imas.imasdef.MDSPLUS_BACKEND
    __input=None
    pulse         = None
    run          = None
    #user_or_path = 'public'
    #database     = 'iter'
    __isConnected=False
    def __init__(self):
        database = 'iter'
        user_or_path = 'public'
        imas_backend = imas.imasdef.MDSPLUS_BACKEND
        input = None
        pulse = 0
        run = 0
    def connectSource(self,connectionString=""):
        ###self.conectionString="database=ITER,user_or_path=public,backend=MDSPLUS"##
        myconn=connectionString.split(",")
        self.configure(listI=myconn)
        ##self.connect()
        return self.__input,self.__isConnected

    def configure(self,listI=[]):
        for s in listI:
            if s.startswith("database"):
                temp=s.split("=")
                self.database=temp[1]
            if s.startswith("path"):
                temp = s.split("=")
                self.user_or_path=temp[1]
            if s.startswith("backend"):
                temp = s.split("=")
                if temp[1]=="MDSPLUS":
                    self.imas_backend = imas.imasdef.MDSPLUS_BACKEND
            if s.startswith("pulseIdent"):
                temp = s.split("=")[1]
                ret = temp.split("/")
                try:
                    self.pulse = int(ret[0])
                    if len(ret) == 2:
                        self.run = int(ret[1])
                    else:
                        self.run=0
                except ValueError:
                    logger.error("got an invalid pulse identifier %s ", temp)
                    self.run = 0
                    self.pulse = 0


    def connect(self):
        try:
            if self.pulse is None or self.run is None:
                logger.warning("not connected to imas db,pulse or pulse is empty")
                self.__isConnected = False
                self.__input = None
                return
            self.__input = imas.DBEntry(self.imas_backend, self.database, self.pulse, self.run, self.user_or_path)
            [err, n] = self.__input.open()
            if err != 0:
                logger.warning("not connected to imas db")
                self.__isConnected=False
                self.__input=None

            else:
                logger.debug("connected to imas db")
            self.__isConnected=True
        except imas.UALBackendException as ual:
            logger.warning("issue with opening the file %s ", ual)
            self.__isConnected=False
            self.__input=None

    def isconnected(self):
        return self.__isConnected

    def getData(self,**kwargs):
        varprefix=None
        idspath=""
        mycfg=[]
        varname=""
        tsS=None
        tsE=None
        if kwargs.get("varname"):
            varname1=kwargs.get("varname")
            if varprefix is not None and len(varprefix) > 0:
                varname = varname1.replace(varprefix, "", 1)
            else:
                varname = varname1
        if kwargs.get("pulse"):
            mycfg.append("pulseIdent="+kwargs.get("pulse"))
            self.configure(mycfg)
        if kwargs.get("tsS"):
            tsS=kwargs.get("tsS")
        if kwargs.get("tsE"):
            tsE=kwargs.get("tsE")
        self.connect()
        return self.getDataI(varname,tsS,tsE)

    def __getUnits(self,idsn,idsp):
        ### this function does not work if we provide indexes on array so indices should be removed ...

        idsp1=re.sub("([\(\[]).*?([\)\]])", "", idsp)
        logger.debug("get unit for  %s", idsp1)
        return imas.dd_units.DataDictionaryUnits().get_units(idsn, idsp1)

    def __getTimeData(self,idsn,idsp):
        try:
            time_type = self.__input.partial_get(ids_name=idsn,data_path="ids_properties/homogeneous_time")
            timevec=[]
            dpath=None
            if time_type==1:
                dpath="time"
            else:
                idsp[0:idsp.rfind("/")] + "/time"
            timevec=self.__input.partial_get(ids_name=idsn, data_path=dpath)


        except AttributeError as err:
            logger.error("Invalid attribute: %s", err)
        except NameError as ne:
            logger.error("Invalid attribute: %s", ne)
        except imas.hli_exception.ALException as ale:
            logger.error("Invalid attribute: %s",ale)

        return timevec

    def getDataI(self,idspath_o=None,tsS=None,tsE=None):
        dobj = DataObj()
        if idspath_o is None:
            return dobj
        res=[]
        idspath_1=idspath_o.replace('[', '(')
        idspath=idspath_1.replace(']', ')')
        if idspath.startswith("/"):
            res=idspath.split("/", 2)

        else:
            res = idspath.split("/", 1)

        logger.debug("res=%s", res)

        if not self.isconnected():
            self.connect()
        if not self.isconnected():
            dobj.xdata = []
            dobj.ydata = []
            return dobj

        dobj.setA(DataType.DA_TYPE_FLOAT, DataType.DA_TYPE_FLOAT, 'Time', '', '', '', 1)
        try:
            time_type=-1
            idx=None
            dobj.setData(self.__input.partial_get(ids_name=res[-2],data_path=res[-1]), 2)
            if dobj.ydata is not None:
                dobj.setData(self.__getTimeData(idsn=res[-2],idsp=res[-1]), 1)
                dobj.yunit = self.__getUnits(res[-2], res[-1])
                dobj.xunit = self.__getUnits(res[-2], "time (s)")
                if dobj.yunit is not None:
                    logger.debug(" found unit %s", dobj.yunit)
                if dobj.xdata is None:
                    logger.debug(" xdata is NONE ")
                else:
                    logger.debug(" xdata is NOT NONE %d ", len(dobj.xdata))
                if tsS is not None and tsE is not None:
                    idx = np.where((dobj.xdata >= tsS) & (dobj.xdata <= tsE))
                    dobj.xdata=dobj.xdata.take(idx)
                    dobj.ydata = dobj.ydata.take(idx)
                    #logger.debug(" idx  %s and ydata=%s ", idx,dobj.ydata)

                else:
                    if tsE is not None:
                        idx = np.where( dobj.xdata <= tsE)
                        dobj.xdata = dobj.xdata.take(idx)
                        dobj.ydata = dobj.ydata.take(idx)
                    elif tsS is not None:
                        idx = np.where(dobj.xdata >= tsS)
                        dobj.xdata = dobj.xdata.take(idx)
                        dobj.ydata = dobj.ydata.take(idx)

            else:
                dobj.xdata=[]
                dobj.ydata=[]


            dobj.errcode=0
            self.close()
        except AttributeError as err:
            logger.debug("Invalid attribute: %s", err)
            dobj.errcode=-1
            dobj.errdescr="Invalid IDS path"
            dobj.ydata=[]
            dobj.xdata=[]
        except NameError as ne:
            logger.debug("Invalid name: %s", ne)
            dobj.errcode = -1
            dobj.errdescr = "Invalid IDS path"
            dobj.ydata = []
            dobj.xdata = []
        except imas.hli_exception.ALException as ale:
            logger.debug("Invalid hli exc: %s",ale)
        return dobj

    def close(self):
        if self.isconnected():
            self.__input.close()
            self.__isConnected=False

    def getEnvelope(self, **kwargs):
       dmin = self.getData( **kwargs)
       dmax=dmin
       logger.debug("envelope function returning %d", len(dmin))
       return dmin,dmax


