import dataAccess.dataCommon as dc
#import uda_client_reader as uc
from uda_client_reader import uda_client_reader_python as uc
import logging2.setupLogger as ls
import dateutil.parser as dp
from datetime import timezone
logger = ls.get_logger(__name__)

###class to interface with data source - here UDA
class udaAccess:
    def __init__(self,parent=None):
        self.udahost="localhost"
        self.uport=3090
        self.errcode=0
        self.errdesc=""
        self.UCR=None
        self.connected=False
        self.__NODATAFOUND = ["Requested data cannot be located","data cannot be retrieved","could not retrieve data","Incorrect time"]


    def connectSource(self,connectionString):
        myconn=connectionString.split(",")
        logger.debug("connect source myconn=%s", myconn)
        self.connect(myconn)

    def connect(self,arglist=[]):
        for s in arglist:
            if s.startswith("host"):
                self.udahost=s.split("=")[1]
            if s.startswith("port"):
                self.uport=int(s.split("=")[1])

        logger.debug("Connecting to UDA host  %s", self.udahost)
        self.UCR=uc.UdaClientReaderPython(self.udahost,self.uport)
        if self.UCR.getErrorCode()!=0:
            self.errdesc="Cannot create UdaClientReader. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())
            self.errcode=-1
            self.connected=False
        else:
            self.connected=True
        #self.UCR.resetAll()

        return self.connected
        #self.dataR=DataObj()
        
    def isConnected(self):
        if self.connected:
            return True
        else:
            return False

    def convertudatypes(self,utype=None):
        
        if utype==uc.RAW_TYPE_FLOAT :
            return dc.DataType.DA_TYPE_FLOAT
        elif utype==uc.RAW_TYPE_DOUBLE:
            return dc.DataType.DA_TYPE_DOUBLE
        elif utype==uc.RAW_TYPE_STRING:
            return dc.DataType.DA_TYPE_STRING
        elif utype==uc.RAW_TYPE_LONG:
            return dc.DataType.DA_TYPE_LONG
        elif utype==uc.RAW_TYPE_UNSIGNED_LONG:
            return dc.DataType.DA_TYPE_ULONG
        elif utype==uc.RAW_TYPE_CHAR:
            return dc.DataType.DA_TYPE_CHAR
        elif utype==uc.RAW_TYPE_UNSIGNED_CHAR:
            return dc.DataType.DA_TYPE_UCHAR
        elif utype==uc.RAW_TYPE_SHORT:
            return dc.DataType.DA_TYPE_SHORT
        elif utype == uc.RAW_TYPE_UNSIGNED_SHORT:
            return dc.DataType.DA_TYPE_USHORT
        elif utype==uc.RAW_TYPE_INT:
            return dc.DataType.DA_TYPE_INT
        elif utype == uc.RAW_TYPE_UNSGINED_INT:
            return dc.DataType.DA_TYPE_UINT

    def convertToNanos(self,tsE):
        parsed_t=None
        if isinstance(tsE, float) or isinstance(tsE, int) :
            return tsE
        if "T" in tsE and "." in tsE:
            try:

                parsed_t = dp.parse(tsE)

                t_in_nsec = parsed_t.replace(tzinfo=timezone.utc).timestamp()*1000000000


                return format(t_in_nsec,'.0f')
            except OverflowError as ofe:
                logger.error("overflow error got invalid date %s ",tsE)
                return -1
            except ValueError as ofe:
                logger.error("value error got invalid date %s ",tsE)
                return -1
        else:
            return tsE


    def getData(self,**kwargs):
        varname=""
        pulsenb=None
        nbp=1000
        decType=None
        tsSN=0
        tsEN=0
        tsS = 0
        tsE = 0
        tsFormat="relative"
        varprefix=None
        pulse=None
        if kwargs.get("varname"):
            varname1=kwargs.get("varname")
            if varprefix is not None and len(varprefix)>0:
                varname=varname1.replace(varprefix,"",1)
            else:
                varname=varname1
        if kwargs.get("pulse"):
            pulsenb=kwargs.get("pulse")
            pulse=self.__parsePulse(pulsenb)
        if kwargs.get("nbp"):
            nbp=kwargs.get("nbp")
        if kwargs.get("decType"):
            decType = kwargs.get("decType")
        if kwargs.get("tsS"):
            tsS = kwargs.get("tsS")
            tsSN=self.convertToNanos(tsS)
        if kwargs.get("tsE"):
            tsE = kwargs.get("tsE")
            tsEN = self.convertToNanos(tsE)

        if kwargs.get("tsFormat"):
            tsFormat = kwargs.get("tsFormat")
        logger.debug("init timestamp tSS=%s and tsE=%s ",tsS,tsE)
        return self.getDataI(varname,pulse,nbp,tsSN,tsEN,tsFormat,decType)

    def __parsePulse(self,pulse):

        if pulse is None:
            return pulse
        p = str(pulse)
        res=p.split("/")
        reslen=len(res)
        if reslen>1:
            ## if last 2 are numeric means pulse nb/run nb
            if res[-1].lstrip("-").isnumeric() and res[-2].lstrip("-").isnumeric():
              p=pulse[:(len(res[-2]))]
        logger.debug("parse pulse %s", str(p))
        return p

    def getUnit(self,varname,tsmp='-1'):
        unitval=None
        if varname is None:
            return unitval
        if not self.connected:
            self.connect(self.udahost)
        MetaData = self.UCR.getMeta(varname, tsmp)
        for i in MetaData:
            if i.name.lower() == "units":
                unitval=i.value
                break
        return unitval

    def getDataI(self, varname="", pulsenb=None, nbp=100, tsS=0, tsE=0, tsFormat="relatve",decType=None, myprocList=None, myprocName=None):
        dobj = dc.DataObj()
        if not self.connected:
            self.connect(self.udahost)
            if self.errcode == -1:
                dobj.setErr(self.errcode, self.errdesc)
                return dobj



        if tsS == 0 and tsE == 0:
            if pulsenb == 0:
                pulsenb = self.UCR.getLastPulse()
                logger.debug("LAST PULSE: %s", pulsenb)


            if decType is None:
                query = "variable={},pulse={},tsFormat={},decSamples={}".format(varname, pulsenb, tsFormat,nbp)
            else:
                query = "variable={},pulse={},tsFormat={},decSamples={},decType={}".format(varname, pulsenb, tsFormat,nbp,decType)
        else:
            if pulsenb is None or pulsenb=="None":
                if decType is None:
                    query = "variable={},tsFormat={},decSamples={},startTime={},endTime={}".format(varname, tsFormat,nbp, tsS,
                                                                                                     tsE)
                else:
                    query = "variable={},tsFormat={},decSamples={},startTime={},endTime={},decType={}".format(varname,tsFormat,
                                                                                                                nbp,
                                                                                                                tsS,
                                                                                                               tsE,
                                                                                                                decType)
            else:
                query = "variable={},pulse={},tsFormat={},decSamples={},decType={},startTime={}S,endTime={}S".format(varname, pulsenb, tsFormat,
                                                                                            nbp, decType,tsS,tsE)

        logger.debug("Query ZZ: %s", query)
        handle = self.UCR.fetchData(query)
        self.errcode = 0
        self.errdesc = ""
        found=0
        if handle < 0:
            self.errcode = -1
            self.errdesc = self.UCR.getErrorMsg()
            logger.info("could not retrieve data and %s",self.errdesc)
            for s in self.__NODATAFOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    found=1
                    break
            if found==0 :
                self.UCR.resetAll()

            dobj.setErr(self.errcode, self.errdesc)
            return dobj

        # self.dataR.clearData()
        dobj.setA(self.convertudatypes(self.UCR.getFetchedTimeType(handle)),
                  self.convertudatypes(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                  self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                  self.UCR.getRank(handle))

        if dobj.ytype == dc.DataType.DA_TYPE_STRING:
            dobj.setData(self.UCR.getDataAsStrings(handle), 2, myprocList, myprocName)
        else:
            dobj.setData(self.UCR.getDataNativeRank(handle), 2, myprocList, myprocName)
        if (dobj.ydata is None):
            self.UCR.releaseData(handle)
            self.errdesc = "no data found {}for query ".format(query)
            self.errdesc = -1
            ##self.UCR.resetAll()
            dobj.setErr(self.errcode, self.errdesc)

            return dobj

        if dobj.xtype == dc.DataType.DA_TYPE_FLOAT or dobj.xtype == dc.DataType.DA_TYPE_DOUBLE:
            dobj.setData(self.UCR.getTimeStampsAsDouble(handle), 1)
        else:
            dobj.setData(self.UCR.getTimeStampsAsLong(handle), 1)

        self.UCR.releaseData(handle)
        dobj.setErr(0, "OK")
        return dobj

    def getEnvelope(self, varname="", pulse=0, nbp=100, tsS=0, tsE=0, tsFormat="relative",decType=None, myprocList=None,
                     myprocName=None):
        dmax = None
        dmin = None
        dmax = self.getData(varname=varname, pulse=pulse, nbp=nbp, tsS=tsS, tsE=tsE, tsFormat=tsFormat,decType="max")

        if dmax.getErr()[0] == 0:
            dmin = self.getData(varname=varname, pulse=pulse, nbp=nbp, tsS=tsS, tsE=tsE, tsFormat=tsFormat,decType="min")
        else:
            dmin = dc.DataObj()
            dmin.setEmpty("No data found ")
        return dmin, dmax
