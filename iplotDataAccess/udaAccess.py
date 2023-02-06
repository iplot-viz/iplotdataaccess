
import iplotDataAccess.dataCommon as dc

#import uda_client_reader as uc
from uda_client_reader import uda_client_reader_python as uc
import iplotLogging.setupLogger as ls
import dateutil.parser as dp
from datetime import timezone

import numpy as np

import time
import os
import math

logger = ls.get_logger(__name__)

class udaParams:
    def __init__(self,parent=None):
        self.varname=None
        self.nbps=0
        self.decType=None
        self.startT=None
        self.endT =None
        self.pulse =None
        self.tsFormat=None
        self.pStart=None
        self.pEnd=None
        
       
        

    def setParams(self,varname,nbps,decType,startT,endT,pulse,tsFormat):
        
        self.varname=varname
        self.nbps=nbps
        self.decType=decType
        self.startT=startT
        self.endT =endT
        self.pulse =pulse
        self.tsFormat=tsFormat
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
        return self.connect(myconn)

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
        elif utype == uc.RAW_TYPE_UNSIGNED_INT:
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


    def getUdaParams(self,**kwargs):
        udaP= udaParams()
        varname=""
        pulsenb=None
        nbp=1000
        decType=None
        tsSN=0
        tsEN=0
        tsS = 0
        tsE = 0
        tsFormat="absolute"
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
        logger.debug("init timestamp tSS=%s and tsE=%s and tsformat=%s ",tsS,tsE,tsFormat)
        udaP.setParams(varname,nbp,decType,tsSN,tsEN,pulse,tsFormat)
        return udaP
        
    def getData(self,**kwargs):
        queryF1=None
        queryL1=None
        fneeded=True
        lneeded=True
        udaP=self.getUdaParams(**kwargs)
        query=self.getDataI(udaP)
        if query is None:
            dobj=dc.DataObj()
            dobj.setErr(-1, "Invalid Pulse ID")
            return dobj
        dobj=self.__fetchData(query)
        if dobj.errcode==-1 or os.getenv("MINT_GET_EXTRE") is None or udaP.tsFormat=="relative" or os.getenv("MINT_GET_EXTRE")=="False":
            return dobj
        
        ##we retrieve the extremities
        if "decType=" in query:
            
            queryL1=query.replace("decType"+udaP.decType,"decType=last")
        else:
            queryL1=query+",decType=last"
           
        
        if dobj.errcode==0:
            ##check if we need to retrieve the point before thet beginning decType=last
            if dobj.xdata[0]==udaP.startT:
                lneeded=False
            if dobj.xdata[-1]==udaP.endT:
                fneeded=False
        logger.debug("dobj first len=%d", len(dobj.xdata))
               
        if lneeded==True:        
            queryL2=queryL1.replace("startTime="+str(udaP.startT),"startTime=0")
            queryL=queryL2.replace("endTime="+str(udaP.endT),"endTime="+str(udaP.startT))
            dobjF=self.__fetchData(queryL)
            ##last query performed to retrieve the last point and to be put at the beginning
            
                
            if dobjF.errcode==0:
                if dobj.errcode==-3:
                    dobj=dc.DataObj()
                    dobj.xdata=numpy.empty(0)
                    dobj.ydata=numpy.empty(0)
                
                xdata=np.insert(dobj.xdata,0,udaP.startT)
                ydata=np.insert(dobj.ydata,0,dobjF.ydata[0])
                dobj.xdata=xdata
                dobj.ydata=ydata
                logger.debug("dobj F %d", dobjF.xdata[0])
                dobj.errcode=0
        ###if no data at the end make it constant to have a line especially when there is one point   if errcode==0 means no archive data   
        if fneeded==True and dobj.errcode==0:
            xdata1=np.append(dobj.xdata,udaP.endT)
            lastp=dobj.ydata[-1]
            ydata1=np.append(dobj.ydata,lastp)
            dobj.xdata=xdata1
            dobj.ydata=ydata1
            logger.debug("dobj final len=%d", len(dobj.xdata))
            
        
            
        return dobj    

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

    def getPulseInfo(self,pulseID="0"):
        PulseInfo=self.UCR.getPulseInfo2(pulseID)
        if self.UCR.getErrorCode() != 0:
            logger.error(("Request error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        if (self.UCR.isEmptyPulse2(PulseInfo.pulseID)):
            logger.error(("Request error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return PulseInfo
    
    def getPulses(self, pattern="ITER:PCS/*"):
        pulses_list = self.UCR.getPulses2(pattern)
        if self.UCR.getErrorCode() != 0:
            logger.error(("Response error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return pulses_list

    def get_cbs_list(self, sep=':', pattern='*', times='0'):
        cbs_list = self.UCR.get_cbs_list(sep, pattern, times)
        if self.UCR.getErrorCode() != 0:
            logger.error(("Response error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return cbs_list

    def get_var_list(self, pattern='.*'):
        var_list = self.UCR.getVariableList(pattern)
        if self.UCR.getErrorCode() != 0:
            print(("Response error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return var_list
    

            
    def getDataI(self, udaP):
        dobj = dc.DataObj()
        query= None
        query1=None
        if not self.connected:
            self.connect(self.udahost)
            if self.errcode == -1:
                dobj.setErr(self.errcode, self.errdesc)
                return dobj
        #we query always absolute to ease adding first and last data point and we transform the data aftewrads
        if udaP.pulse is None or udaP.pulse=="None":
            query1 = "variable={},tsFormat={},decSamples={},startTime={},endTime={}".format(udaP.varname,udaP.tsFormat,udaP.nbps, udaP.startT,udaP.endT)
        else:
            if udaP.pulse=="0":
                udaP.pulse = self.UCR.getLastPulse()
                logger.debug("LAST PULSE: %s", udaP.pulse)
             ##we need to check if it is an-going pulse to not use the cache...
            pulseI=self.getPulseInfo(udaP.pulse)
            if pulseI is None:
                return query
            ##on going pulse
            if pulseI.timeTo>=time.time_ns() and (pulseI.timeFrom+int(udaP.endT*1000000000)>=time.time_ns() or udaP.endT==0):
                
                
                udaP.endT=math.ceil((time.time_ns()-pulseI.timeFrom)/1000000000)
                
                
                ##get
                logger.debug("current pulse et=%d st=%d", udaP.endT,udaP.startT)
                
                ## to bypass the cache we explicitely move the end time...udaP.tsFormat,
                query1 = "variable={},tsFormat={},decSamples={},pulse={},startTime={}S,endTime={}S".format(udaP.varname,udaP.tsFormat, udaP.nbps,udaP.pulse, udaP.startT,udaP.endT)
            else:                                                      
                logger.debug("completed pulse tsE=%d,tsS=%d", udaP.endT, udaP.startT)
                if udaP.endT==0:
                    query1="variable={},tsFormat={},decSamples={},pulse={},startTime={}S".format(udaP.varname, udaP.tsFormat, udaP.nbps, udaP.pulse,udaP.startT,udaP.endT)
                else:
                    query1="variable={},tsFormat={},decSamples={},pulse={},startTime={}S,endTime={}S".format(udaP.varname, udaP.tsFormat, udaP.nbps, udaP.pulse,udaP.startT,udaP.endT)
                
        
        if udaP.decType is not None:
            query= query1+",decType={}".format(udaP.decType)
        else:
            query=query1
        return query
    
   
        
    
    ##@cached(cache=LRUCache(maxsize=100))
    def __fetchData(self,query):
        logger.debug("Query ZZ: %s", query)
        handle = self.UCR.fetchData(query)
        self.errcode = 0
        self.errdesc = ""
        found=0
        dobj= dc.DataObj()
        if handle < 0:
            self.errcode = -1
            self.errdesc = self.UCR.getErrorMsg()
            logger.info("could not retrieve data and %s",self.errdesc)
            for s in self.__NODATAFOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode=-3
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
            dobj.setData(self.UCR.getDataAsStrings(handle), 2)
        else:
            dobj.setData(self.UCR.getDataNativeRank(handle), 2)
        if (dobj.ydata is None):
            self.UCR.releaseData(handle)
            self.errdesc = "no data found {}for query ".format(query)
            self.errcode = -3
            ##self.UCR.resetAll()
            dobj.setErr(self.errcode, self.errdesc)

            return dobj

        if dobj.xtype == dc.DataType.DA_TYPE_FLOAT or dobj.xtype == dc.DataType.DA_TYPE_DOUBLE:
            dobj.setData(self.UCR.getTimeStampsAsDouble(handle), 1)
        else:
            dobj.setData(self.UCR.getTimeStampsAsLong(handle), 1)

        self.UCR.releaseData(handle)
        dobj.setErr(0, "OK")
        logger.debug("Query ZZ: %s and errcode=%d", query,self.errcode)
        return dobj
    
    ##@cached(cache=LRUCache(maxsize=100))
    def __fetchEnvelope(self,query):
        logger.debug("Query ZZ: %s", query)
        handle = self.UCR.fetchData(query)
        self.errcode = 0
        self.errdesc = ""
        found=0
        dEnv= dc.DataEnvelope()
        if handle < 0:
            self.errcode = -1
            self.errdesc = self.UCR.getErrorMsg()
            logger.info("could not retrieve data and %s",self.errdesc)
            for s in self.__NODATAFOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode=-3
                    found=1
                    break
            if found==0 :
                self.UCR.resetAll()
            
            dEnv.setErr(self.errcode, self.errdesc)
            return dEnv
        if dEnv.ytype == dc.DataType.DA_TYPE_STRING:
            ##we should not be there but...
            dEnv.setErr(-1,"Envelope has no meaning for string datatypes")
            return dEnv
        # self.dataR.clearData()
        dEnv.setA(self.convertudatypes(self.UCR.getFetchedTimeType(handle)),
                  self.convertudatypes(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                  self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                  self.UCR.getRank(handle))

        data=self.UCR.getDataNativeRank(handle)
        
        if (data is None):
            self.UCR.releaseData(handle)
            self.errdesc = "no data found {}for query ".format(query)
            self.errdesc = -3
            ##self.UCR.resetAll()
            dEnv.setErr(self.errcode, self.errdesc)

            return dEnv
        
        dEnv.setYData(data[:, 1], data[:, 2], data[:, 0])
        if dEnv.xtype == dc.DataType.DA_TYPE_FLOAT or dEnv.xtype == dc.DataType.DA_TYPE_DOUBLE:
            dEnv.setXData(self.UCR.getTimeStampsAsDouble(handle))
        else:
            dEnv.setXData(self.UCR.getTimeStampsAsLong(handle))

        self.UCR.releaseData(handle)
        dEnv.setErr(0, "OK")
        return dEnv

    def getEnvelope(self,**kwargs):
        kwargs['decType']="env"
            
        udaP=self.getUdaParams(**kwargs)
        query=self.getDataI(udaP)
        if query is None:
            dobj=dc.DataEnvelope()
            dobj.setErr(-1, "Invalid Pulse ID")
            logger.debug("getEnveloppe exiting pulse does not exist")
            return dobj
        dEnv=self.__fetchEnvelope(query)
        logger.debug("getEnveloppe exiting pulse does exist ")
        return dEnv
