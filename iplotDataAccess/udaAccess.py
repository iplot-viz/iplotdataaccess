import operator

import iplotDataAccess.dataCommon as dc
import iplotDataAccess.dataCommon as dataCommon
import iplotDataAccess.nestedDatatype as nDT
from cachetools import cachedmethod

# import uda_client_reader as uc
from uda_client_reader import uda_client_reader_python as uc
import iplotLogging.setupLogger as setupLog
import dateutil.parser as dp
from datetime import timezone

import numpy as np

import time
import os
import math
import json
import collections
import cachetools as ct

logger = setupLog.get_logger(__name__)



class udaParams:
    def __init__(self):
        self.varname = None
        self.nbps = 0
        self.decType = None
        self.startT = None
        self.endT = None
        self.pulse = None
        self.tsFormat = None
        self.pStart = None
        self.pEnd = None

    def setParams(self, varname, nbps, dec_type, start_t, end_t, pulse, ts_format):
        self.varname = varname
        self.nbps = nbps
        self.decType = dec_type
        self.startT = start_t
        self.endT = end_t
        self.pulse = pulse
        self.tsFormat = ts_format


# class to interface with data source - here UDA
class udaAccess:
    def __init__(self):
        self.udahost = "localhost"
        self.uport = 3090
        self.errcode = 0
        self.errdesc = ""
        self.UCR = None
        self.connected = False
        self.__NODATAFOUND = ["Requested data cannot be located", "data cannot be retrieved", "could not retrieve data",
                              "Incorrect time"]
        self.access_cache = ct.LRUCache(maxsize=100)

    def connectSource(self, connectionString):
        myconn = connectionString.split(",")
        logger.debug("connect source myconn=%s", myconn)
        return self.connect(myconn)

    def connect(self, arglist=None):
        if arglist is None:
            arglist = []
        for s in arglist:
            if s.startswith("host"):
                self.udahost = s.split("=")[1]
            if s.startswith("port"):
                self.uport = int(s.split("=")[1])

        logger.debug("Connecting to UDA host  %s", self.udahost)
        self.UCR = uc.UdaClientReaderPython(self.udahost, self.uport)
        self.connected = self.UCR.isConnected()
        self.errdesc = self.UCR.getErrorMsg()
        self.errcode = self.UCR.getErrorCode()
        # self.UCR.resetAll()

        return self.connected
        # self.dataR=DataObj()

    def isConnected(self):
        return self.connected

    @staticmethod
    def convertudatypes(utype=None):

        if utype == uc.RAW_TYPE_FLOAT:
            return dataCommon.DataType.DA_TYPE_FLOAT
        elif utype == uc.RAW_TYPE_DOUBLE:
            return dataCommon.DataType.DA_TYPE_DOUBLE
        elif utype == uc.RAW_TYPE_STRING:
            return dataCommon.DataType.DA_TYPE_STRING
        elif utype == uc.RAW_TYPE_LONG:
            return dataCommon.DataType.DA_TYPE_LONG
        elif utype == uc.RAW_TYPE_UNSIGNED_LONG:
            return dataCommon.DataType.DA_TYPE_ULONG
        elif utype == uc.RAW_TYPE_CHAR:
            return dataCommon.DataType.DA_TYPE_CHAR
        elif utype == uc.RAW_TYPE_UNSIGNED_CHAR:
            return dataCommon.DataType.DA_TYPE_UCHAR
        elif utype == uc.RAW_TYPE_SHORT:
            return dataCommon.DataType.DA_TYPE_SHORT
        elif utype == uc.RAW_TYPE_UNSIGNED_SHORT:
            return dataCommon.DataType.DA_TYPE_USHORT
        elif utype == uc.RAW_TYPE_INT:
            return dataCommon.DataType.DA_TYPE_INT
        elif utype == uc.RAW_TYPE_UNSIGNED_INT:
            return dataCommon.DataType.DA_TYPE_UINT

    @staticmethod
    def convertToNanos(ts_e):
        if isinstance(ts_e, float) or isinstance(ts_e, int):
            return ts_e
        if "T" in ts_e and "." in ts_e:
            try:

                parsed_t = dp.parse(ts_e)

                t_in_nsec = parsed_t.replace(tzinfo=timezone.utc).timestamp() * 1000000000

                return format(t_in_nsec, '.0f')
            except OverflowError as _:
                logger.error("overflow error got invalid date %s ", ts_e)
                return -1
            except ValueError as _:
                logger.error("value error got invalid date %s ", ts_e)
                return -1
        else:
            return ts_e

    def getUdaParams(self, **kwargs):
        uda_p = udaParams()
        varname = ""
        nbp = 1000
        dec_type = None
        ts_sn = 0
        ts_en = 0
        ts_s = 0
        ts_e = 0
        ts_format = "absolute"
        varprefix = None
        pulse = None
        if kwargs.get("varname"):
            varname1 = kwargs.get("varname")
            if varprefix is not None and len(varprefix) > 0:
                varname = varname1.replace(varprefix, "", 1)
            else:
                varname = varname1
        if kwargs.get("pulse"):
            pulsenb = kwargs.get("pulse")
            pulse = self.__parsePulse(pulsenb)
        if kwargs.get("nbp"):
            nbp = kwargs.get("nbp")
        if kwargs.get("decType"):
            dec_type = kwargs.get("decType")
        if kwargs.get("tsS"):
            ts_s = kwargs.get("tsS")
            ts_sn = self.convertToNanos(ts_s)
        if kwargs.get("tsE"):
            ts_e = kwargs.get("tsE")
            ts_en = self.convertToNanos(ts_e)

        if kwargs.get("tsFormat"):
            ts_format = kwargs.get("tsFormat")
        logger.debug("init timestamp tSS=%s and tsE=%s and tsformat=%s ", ts_s, ts_e, ts_format)
        uda_p.setParams(varname, nbp, dec_type, ts_sn, ts_en, pulse, ts_format)
        return uda_p

    def checkToAddInCache(self, query, udaP):
        if udaP.tsFormat == "relative" and udaP.pulse is not None:
            pnb = udaP.pulse.split("/")[-1]
            ##case we access using a relative pulse number cannot be cached as it moves ...
            if int(pnb) < 1:
                return False
            pinfo = self.getPulseInfo(udaP.pulse)
            ##case where a pulse is on going ....
            if self.UCR.isEmptyTimeStamp(pinfo.timeTo):
                return False
        else:
            ###we allow alatency of 20
            if udaP.pEnd is not None and (time.time_ns - udaP.pEnd < 20 * 1000000000):
                return False
        return True

    def getData(self, **kwargs):
        queryF1 = None
        queryL1 = None
        fneeded = True
        lneeded = True
        toBeCached = True
        uda_p = self.getUdaParams(**kwargs)
        query = self.getDataI(uda_p)
        if query is None:
            dobj = dataCommon.DataObj()
            dobj.setErr(-1, "Invalid Pulse ID")
            return dobj

        print("value of query =%s", query)
        tobeCached = self.checkToAddInCache(query, uda_p)

        if tobeCached:
            dobj = self.__fetchDataWithCache(query)
        else:
            dobj = self.__fetchDataX(query)

        if dobj.errcode == -1 or os.getenv("MINT_GET_EXTRE") is None or uda_p.tsFormat == "relative" or os.getenv(
                "MINT_GET_EXTRE") == "False":
            return dobj

        # we retrieve the extremities
        if "decType=" in query:
            query_l1 = query.replace("decType" + uda_p.decType, "decType=last")
        else:
            query_l1 = query + ",decType=last"

        if dobj.errcode == 0:
            # check if we need to retrieve the point before thet beginning decType=last
            if dobj.xdata[0] == uda_p.startT:
                lneeded = False
            if dobj.xdata[-1] == uda_p.endT:
                fneeded = False
        logger.debug("dobj first len=%d", len(dobj.xdata))

        if lneeded:
            query_l2 = query_l1.replace("startTime=" + str(uda_p.startT), "startTime=0")
            query_l = query_l2.replace("endTime=" + str(uda_p.endT), "endTime=" + str(uda_p.startT))
            dobj_f = self.__fetchDataX(query_l)
            # last query performed to retrieve the last point and to be put at the beginning

            if dobj_f.errcode == 0:
                if dobj.errcode == -3:
                    dobj = dataCommon.DataObj()
                    dobj.xdata = np.empty(0)
                    dobj.ydata = np.empty(0)

                xdata = np.insert(dobj.xdata, 0, uda_p.startT)
                ydata = np.insert(dobj.ydata, 0, dobj_f.ydata[0])
                dobj.xdata = xdata
                dobj.ydata = ydata
                logger.debug("dobj F %d", dobj_f.xdata[0])
                dobj.errcode = 0
        # if no data at the end make it constant to have a line especially when there is one point
        # if errcode==0 means no archive data
        if fneeded and dobj.errcode == 0:
            xdata1 = np.append(dobj.xdata, uda_p.endT)
            lastp = dobj.ydata[-1]
            ydata1 = np.append(dobj.ydata, lastp)
            dobj.xdata = xdata1
            dobj.ydata = ydata1
            logger.debug("dobj final len=%d", len(dobj.xdata))

        return dobj

    @staticmethod
    def __parsePulse(pulse):

        if pulse is None:
            return pulse
        p = str(pulse)
        res = p.split("/")
        reslen = len(res)
        if reslen > 1:
            # if last 2 are numeric means pulse nb/run nb
            if res[-1].lstrip("-").isnumeric() and res[-2].lstrip("-").isnumeric():
                p = pulse[:(len(res[-2]))]
        logger.debug("parse pulse %s", str(p))
        return p

    def getUnit(self, varname, tsmp='-1'):
        unitval = None
        if varname is None:
            return unitval
        if not self.connected:
            self.connect(self.udahost)
        meta_data = self.UCR.getMeta(varname, tsmp)
        for i in meta_data:
            if i.name.lower() == "units":
                unitval = i.value
                break
        return unitval

    def getPulseInfo(self, pulse_id="0"):
        pulse_info = self.UCR.getPulseInfo2(pulse_id)
        if self.UCR.getErrorCode() != 0:
            logger.error(("Request error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        if self.UCR.isEmptyPulse2(pulse_info.pulseID):
            logger.error(("Request error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return pulse_info

    def getPulses(self, pattern="ITER:PCS/*"):
        pulses_list = self.UCR.getPulses2(pattern)
        if self.UCR.getErrorCode() != 0:
            logger.error(("Response error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None
        return pulses_list

    def get_cbs_list(self, sep=':', pattern='*', times='0'):
        cbs_list = self.UCR.getCbsList(sep, pattern, times)
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return None
        return cbs_list

    def get_var_list(self, pattern='.*'):
        var_list = self.UCR.getVariableList(pattern)
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return None
        return var_list

    def get_var_fields(self, variable, timestamp='-1'):
        uda_type = self.UCR.getMetaTypeJSONCollapsed(variable, str(timestamp))
        if self.UCR.getErrorCode() != 0:
            print(("Response error. Error: {} {}".format(self.UCR.getErrorCode(), self.UCR.getErrorMsg())))
            return None

        if uda_type:
            js_nested = json.loads(uda_type, object_pairs_hook=collections.OrderedDict)
            dt = nDT.NestedDatatype("")
            dt.loadUDAJson(js_nested)
            fdt = dt.flatDatatype("")
            return fdt.fields_to_json()

        return None

    def getDataI(self, uda_p):
        dobj = dataCommon.DataObj()
        query = None
        if not self.connected:
            self.connect(self.udahost)
            if self.errcode == -1:
                dobj.setErr(self.errcode, self.errdesc)
                return dobj
        # we query always absolute to ease adding first and last data point, and we transform the data aftewrads
        if uda_p.pulse is None or uda_p.pulse == "None":
            query1 = "variable={},tsFormat={},decSamples={},startTime={},endTime={}".format(uda_p.varname,
                                                                                            uda_p.tsFormat,
                                                                                            uda_p.nbps, uda_p.startT,
                                                                                            uda_p.endT)
        else:
            if uda_p.pulse == "0":
                uda_p.pulse = self.UCR.getLastPulse()
                logger.debug("LAST PULSE: %s", uda_p.pulse)
            # we need to check if it is an-going pulse to not use the cache...
            pulse_i = self.getPulseInfo(uda_p.pulse)
            if pulse_i is None:
                return query
            # ongoing pulse
            if pulse_i.timeTo >= time.time_ns() and (
                    pulse_i.timeFrom + int(uda_p.endT * 1000000000) >= time.time_ns() or uda_p.endT == 0):

                uda_p.endT = math.ceil((time.time_ns() - pulse_i.timeFrom) / 1000000000)

                # get
                logger.debug("current pulse et=%d st=%d", uda_p.endT, uda_p.startT)

                # to bypass the cache we explicitely move the end time...udaP.tsFormat,
                query1 = "variable={},tsFormat={},decSamples={},pulse={},startTime={}S,endTime={}S".format(
                    uda_p.varname,
                    uda_p.tsFormat,
                    uda_p.nbps,
                    uda_p.pulse,
                    uda_p.startT,
                    uda_p.endT)
            else:
                logger.debug("completed pulse tsE=%d,tsS=%d", uda_p.endT, uda_p.startT)
                if uda_p.endT == 0:
                    query1 = "variable={},tsFormat={},decSamples={},pulse={},startTime={}S".format(uda_p.varname,
                                                                                                   uda_p.tsFormat,
                                                                                                   uda_p.nbps,
                                                                                                   uda_p.pulse,
                                                                                                   uda_p.startT,
                                                                                                   uda_p.endT)
                else:
                    query1 = "variable={},tsFormat={},decSamples={},pulse={},startTime={}S,endTime={}S".format(
                        uda_p.varname, uda_p.tsFormat, uda_p.nbps, uda_p.pulse, uda_p.startT, uda_p.endT)

        if uda_p.decType is not None:
            query = query1 + ",decType={}".format(uda_p.decType)
        else:
            query = query1
        return query

    def clearCache(self):
        self.access_cache.clear()

    @cachedmethod(operator.attrgetter('access_cache'))
    def __fetchDataWithCache(self, query):
        return self.__fetchDataX(query)

    @cachedmethod(operator.attrgetter('access_cache'))
    def __fetchEnvelopeWithCache(self, query):
        return self.__fetchEnvelope(query)

    def __fetchDataX(self, query):
        logger.debug("Query ZZ: %s", query)
        handle = self.UCR.fetchData(query)
        self.errcode = 0
        self.errdesc = ""
        found = 0
        dobj = dataCommon.DataObj()
        if handle < 0:
            self.errcode = -1
            self.errdesc = self.UCR.getErrorMsg()
            logger.info("could not retrieve data and %s", self.errdesc)
            for s in self.__NODATAFOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode = -3
                    found = 1
                    break
            if found == 0:
                self.UCR.resetAll()

            dobj.setErr(self.errcode, self.errdesc)
            return dobj

        # self.dataR.clearData()
        dobj.setA(self.convertudatypes(self.UCR.getFetchedTimeType(handle)),
                  self.convertudatypes(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                  self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                  self.UCR.getRank(handle))

        if dobj.ytype == dataCommon.DataType.DA_TYPE_STRING:
            dobj.setData(self.UCR.getDataAsStrings(handle), 2)
        else:
            dobj.setData(self.UCR.getDataNativeRank(handle), 2)
        if dobj.ydata is None:
            self.UCR.releaseData(handle)
            self.errdesc = "no data found {}for query ".format(query)
            self.errcode = -3
            # self.UCR.resetAll()
            dobj.setErr(self.errcode, self.errdesc)

            return dobj

        if dobj.xtype == dataCommon.DataType.DA_TYPE_FLOAT or dobj.xtype == dataCommon.DataType.DA_TYPE_DOUBLE:
            dobj.setData(self.UCR.getTimeStampsAsDouble(handle), 1)
        else:
            dobj.setData(self.UCR.getTimeStampsAsLong(handle), 1)

        self.UCR.releaseData(handle)
        dobj.setErr(0, "OK")
        logger.debug("Query ZZ: %s and errcode=%d", query, self.errcode)
        return dobj

    # @cached(cache=LRUCache(maxsize=100))
    def __fetchEnvelope(self, query):
        logger.debug("Query ZZ: %s", query)
        handle = self.UCR.fetchData(query)
        self.errcode = 0
        self.errdesc = ""
        found = 0
        d_env = dataCommon.DataEnvelope()
        if handle < 0:
            self.errcode = -1
            self.errdesc = self.UCR.getErrorMsg()
            logger.info("could not retrieve data and %s", self.errdesc)
            for s in self.__NODATAFOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode = -3
                    found = 1
                    break
            if found == 0:
                self.UCR.resetAll()

            d_env.setErr(self.errcode, self.errdesc)
            return d_env
        if d_env.ytype == dataCommon.DataType.DA_TYPE_STRING:
            # we should not be there but...
            d_env.setErr(-1, "Envelope has no meaning for string datatypes")
            return d_env
        # self.dataR.clearData()
        d_env.setA(self.convertudatypes(self.UCR.getFetchedTimeType(handle)),
                   self.convertudatypes(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                   self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                   self.UCR.getRank(handle))

        data = self.UCR.getDataNativeRank(handle)

        if data is None:
            self.UCR.releaseData(handle)
            self.errdesc = "no data found {}for query ".format(query)
            self.errdesc = -3
            # self.UCR.resetAll()
            d_env.setErr(self.errcode, self.errdesc)

            return d_env

        d_env.setYData(data[:, 1], data[:, 2], data[:, 0])
        if d_env.xtype == dataCommon.DataType.DA_TYPE_FLOAT or d_env.xtype == dataCommon.DataType.DA_TYPE_DOUBLE:
            d_env.setXData(self.UCR.getTimeStampsAsDouble(handle))
        else:
            d_env.setXData(self.UCR.getTimeStampsAsLong(handle))

        self.UCR.releaseData(handle)
        d_env.setErr(0, "OK")
        return d_env

    def getEnvelope(self, **kwargs):
        kwargs['decType'] = "env"

        uda_p = self.getUdaParams(**kwargs)
        query = self.getDataI(uda_p)
        if query is None:
            dobj = dataCommon.DataEnvelope()
            dobj.setErr(-1, "Invalid Pulse ID")
            logger.debug("getEnveloppe exiting pulse does not exist")
            return dobj

        tobeCached = self.checkToAddInCache(query, uda_p)

        if tobeCached:
            d_env = self.__fetchEnvelopeWithCache(query)
        else:
            d_env = self.__fetchEnvelope(query)
        logger.debug("getEnveloppe exiting pulse does exist ")
        return d_env
