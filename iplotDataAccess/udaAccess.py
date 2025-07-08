import operator
from typing import List

from pandas import DataFrame

import iplotDataAccess.dataCommon as dataCommon
import iplotDataAccess.nestedDatatype as nDT
from cachetools import cachedmethod

# import uda_client_reader as uc
from uda_client_reader import uda_client_reader_python as uc
import iplotLogging.setupLogger as setupLog
import dateutil.parser as dp
from datetime import timezone

import numpy as np
import pandas as pd

import time
import os
import math
import json
import collections
import cachetools as ct

from iplotDataAccess.dataSource import DataSource
from iplotDataAccess.realTimeStreamer import RTStreamer

logger = setupLog.get_logger(__name__)


class RTHException(Exception):
    pass


class UdaParams:
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
        self.extSamples = None

    def set_params(self, varname, nbps, dec_type, start_t, end_t, pulse, ts_format, ext_samples):
        self.varname = varname
        self.nbps = nbps
        self.decType = dec_type
        self.startT = start_t
        self.endT = end_t
        self.pulse = pulse
        self.tsFormat = ts_format
        self.extSamples = ext_samples


# class to interface with data source - here UDA
class UdaAccess(DataSource):
    source_type = "CODAC_UDA"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.host = config.get("host")
        self.port = config.get("port")

        self.rtu = config.get("rturl")
        self.rtheaders = config.get("rtheaders")
        self.rtauth = config.get("rtauth")
        self.errcode = 0
        self.errdesc = ""
        self.UCR = None
        self.connected = False
        self.__NO_DATA_FOUND = ["Requested data cannot be located", "data cannot be retrieved",
                                "could not retrieve data", "Incorrect time"]
        self.access_cache = ct.LRUCache(maxsize=100)
        self.pulses_cache = {}

    def connect(self) -> bool:

        logger.debug("Connecting to UDA host  %s and url=%s ", self.host,self.rtu)
        self.UCR = uc.UdaClientReaderPython(self.host, self.port)
        self.connected = self.UCR.isConnected()
        self.errdesc = self.UCR.getErrorMsg()
        self.errcode = self.UCR.getErrorCode()

        self.set_rt_handler()

        return self.connected

    def is_connected(self):
        return self.connected

    @staticmethod
    def convert_uda_types(utype=None):

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

    def set_rt_handler(self):
        myhd = {}
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
            self.RTHandler = RTStreamer(url=self.rtu, headers=myhd, auth=self.rta,
                                        uda_a=self.daHandler)
            self.rterrcode = 0
            self.rtStatus = "INITIALISED"
            logger.debug("real time setRTHandler OK %s head=%s auth=%s ", self.rtu, myhd, self.rta)
        except ModuleNotFoundError:
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"
        except AttributeError:
            self.rterrcode = -1
            self.rtStatus = "UNEXISTING"

    @staticmethod
    def convert_to_nanos(ts_e: str):
        if not isinstance(ts_e, str):
            return ts_e
        if "T" in ts_e and "." in ts_e:
            try:
                parsed_t = dp.parse(ts_e)
                t_in_nsec = parsed_t.replace(tzinfo=timezone.utc).timestamp() * 1000000000
                return f"{t_in_nsec:.0f}"
            except OverflowError as _:
                logger.error("overflow error got invalid date %s ", ts_e)
                return -1
            except ValueError as _:
                logger.error("value error got invalid date %s ", ts_e)
                return -1
        else:
            return ts_e

    def get_uda_params(self, **kwargs):
        uda_p = UdaParams()

        varname = kwargs.get("varname", "")
        pulse_nb = kwargs.get("pulse", None)
        pulse = self.__parse_pulse(pulse_nb)
        nbp = kwargs.get("nbp", 1000)
        dec_type = kwargs.get("decType", None)

        ts_s = kwargs.get("tsS", "0")
        ts_sn = self.convert_to_nanos(ts_s)
        ts_e = kwargs.get("tsE", "0")
        ts_en = self.convert_to_nanos(ts_e)
        ext_samples = kwargs.get("extremities", False)
        ts_format = kwargs.get("tsFormat", "absolute")
        logger.debug(f"init timestamp tSS={ts_s} and tsE={ts_e} and ts_format={ts_format}")
        uda_p.set_params(varname, nbp, dec_type, ts_sn, ts_en, pulse, ts_format, ext_samples)
        return uda_p

    def check_to_add_in_cache(self, uda_p):
        if uda_p.tsFormat == "relative" and uda_p.pulse is not None:
            pnb = uda_p.pulse.split("/")[-1]
            # case we access using a relative pulse number cannot be cached as it moves ...
            if int(pnb) < 1:
                return False
            if uda_p.pulse in self.pulses_cache:
                pinfo = self.pulses_cache.get(uda_p.pulse)
            else:
                pinfo = self.get_pulse_info(uda_p.pulse)
            # case where a pulse is on going ....
            if self.UCR.isEmptyTimeStamp(pinfo.timeTo):
                return False
        else:
            # we allow alatency of 20
            if uda_p.pEnd is not None and (time.time_ns() - uda_p.pEnd < 20 * 1000000000):
                return False
        return True

    def get_data(self, **kwargs):
        first_needed = True
        last_needed = True
        uda_p = self.get_uda_params(**kwargs)
        query = self.get_data_i(uda_p)
        if query is None:
            data_obj = dataCommon.DataObj()
            data_obj.set_err(-1, "Invalid Pulse ID")
            return data_obj

        # print("value of query =%s", query)
        tobe_cached = self.check_to_add_in_cache(uda_p)

        if tobe_cached:
            data_obj = self.__fetch_data_with_cache(query)
        else:
            data_obj = self.__fetch_data_x(query)

        if data_obj.errcode == -1 or uda_p.tsFormat == "relative" or not uda_p.extSamples:
            return data_obj

        if os.getenv("MINT_GET_EXTRE", "").lower() == "true":
            # we retrieve the extremities
            if "decType=" in query:
                query_l1 = query.replace("decType" + uda_p.decType, "decType=last")
            else:
                query_l1 = query + ",decType=last"

            if data_obj.errcode == 0:
                # check if we need to retrieve the point before thet beginning decType=last
                if data_obj.xdata[0] == uda_p.startT:
                    last_needed = False
                if data_obj.xdata[-1] == uda_p.endT:
                    first_needed = False
            logger.debug("dobj first len=%d", len(data_obj.xdata))

            if last_needed:
                query_l2 = query_l1.replace("startTime=" + str(uda_p.startT), "startTime=0")
                query_l = query_l2.replace("endTime=" + str(uda_p.endT), "endTime=" + str(uda_p.startT))
                dobj_f = self.__fetch_data_x(query_l)
                # last query performed to retrieve the last point and to be put at the beginning

                if dobj_f.errcode == 0:
                    if data_obj.errcode == -3:
                        data_obj = dataCommon.DataObj()
                        data_obj.xdata = np.empty(0)
                        data_obj.ydata = np.empty(0)

                    xdata = np.insert(data_obj.xdata, 0, uda_p.startT)
                    ydata = np.insert(data_obj.ydata, 0, dobj_f.ydata[0])
                    data_obj.xdata = xdata
                    data_obj.ydata = ydata
                    logger.debug("dobj F %d", dobj_f.xdata[0])
                    data_obj.errcode = 0
            # if no data at the end make it constant to have a line especially when there is one point
            # if errcode==0 means no archive data
            if first_needed and data_obj.errcode == 0:
                xdata1 = np.append(data_obj.xdata, uda_p.endT)
                lastp = data_obj.ydata[-1]
                ydata1 = np.append(data_obj.ydata, lastp)
                data_obj.xdata = xdata1
                data_obj.ydata = ydata1
                logger.debug("dobj final len=%d", len(data_obj.xdata))

        else:
            x_data = data_obj.xdata
            y_data = data_obj.ydata

            if uda_p.startT not in x_data:
                x_idx_start = sum(x_data < uda_p.startT) - 1
                if x_idx_start != -1:
                    y_value = y_data[x_idx_start]
                    x_data = x_data[x_idx_start + 1:]
                    y_data = y_data[x_idx_start + 1:]
                    x_data = np.insert(x_data, 0, uda_p.startT)
                    y_data = np.insert(y_data, 0, y_value)

            if uda_p.endT not in data_obj.xdata:
                x_idx_end = sum(x_data < uda_p.endT) - 1
                if x_idx_end != -1:
                    y_value = y_data[x_idx_end]
                    x_data = x_data[:x_idx_end + 1]
                    y_data = y_data[:x_idx_end + 1]
                    x_data = np.append(x_data, uda_p.endT)
                    y_data = np.append(y_data, y_value)

            data_obj.xdata = x_data
            data_obj.ydata = y_data
        return data_obj

    @staticmethod
    def max_value_index_less_than(arr, num):
        filtered_index = np.where(arr < num)[0]
        if filtered_index.size == 0:
            return None

        max_index = filtered_index[np.argmax(arr[filtered_index])]

        return max_index

    @staticmethod
    def __parse_pulse(pulse):
        if not pulse:
            return None
        p = str(pulse)
        res = p.split("/")
        reslen = len(res)
        if reslen > 1:
            # if last 2 are numeric means pulse nb/run nb
            if res[-1].lstrip("-").isnumeric() and res[-2].lstrip("-").isnumeric():
                p = pulse[:(len(res[-2]))]
        logger.debug("parse pulse %s", str(p))
        return p

    def get_unit(self, varname, tsmp='-1'):
        unitval = None
        if varname is None:
            return unitval
        if not self.connected:
            self.connect()
        meta_data = self.UCR.getMeta(varname, tsmp)
        for i in meta_data:
            if i.name.lower() == "units":
                unitval = i.value
                break
        return unitval

    def get_pulse_info(self, pulse_id="0"):
        logger.debug(f"requires a pulse {pulse_id} and the cache {self.pulses_cache}")
        if pulse_id in self.pulses_cache.keys():
            pulse_info = self.pulses_cache.get(pulse_id)
            logger.debug("found pulse in the cache", pulse_id)
        else:
            pulse_info = self.UCR.getPulseInfo2(pulse_id)
            if self.UCR.getErrorCode() != 0:
                logger.error(f"Request error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
                return None
            if self.UCR.isEmptyPulse2(pulse_info.pulseID):
                logger.error(f"Request error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
                return None
            if pulse_info.timeTo < time.time_ns():
                self.pulses_cache.update({pulse_id: pulse_info})

        return pulse_info

    def search_pulses_df(self, text: str) -> DataFrame:
        location = ''
        folder = ''
        pulse = ''
        if text.isdigit():
            pattern = f'*:*/{text}'
        else:
            parts = text.split(':')
            if len(parts) > 1:
                # At least, location and folder
                location = parts[0]
                rest = parts[1].split('/')
                if len(rest) > 1 and (rest[1].isdigit() or rest[1] == '*'):
                    # Location, folder and pulse number specified
                    folder = rest[0]
                    pulse = rest[1]
                else:
                    # Just location and folder
                    folder = parts[1]
                    pulse = ''
            else:
                # Multiple cases: just location , just folder or folder with pulse
                ofd = parts[0].split('/')
                if len(ofd) > 1 and (ofd[1].isdigit() or ofd[1] == '*'):
                    # Folder and pulse number specified
                    location = ''
                    folder = ofd[0] if not ofd[0].startswith('*') else ofd[0][1:]
                    pulse = ofd[1]
                else:
                    # Just location or folder
                    if ofd[0].startswith('*') and ofd[0].endswith('*'):
                        # Valid just for folder
                        location = ''
                        folder = ofd[0][1:]  # Remove the first '*'
                        pulse = ''
                    elif ofd[0].endswith('*'):
                        # Valid just for location
                        location = ofd[0]
                        folder = ''
                        pulse = ''

            # Set pattern for search
            if location and folder and pulse:
                pattern = f'{location}:{folder}/{pulse}'
            elif location and not folder and not pulse:
                pattern = f'{location}:*/*'
            elif location and folder and not pulse:
                pattern = f'{location}:{folder}/*'
            elif not location and folder and pulse:
                pattern = f'*:{folder}/{pulse}'
            elif not location and folder and not pulse:
                pattern = f'*:{folder}/*'
            else:
                pattern = ' '

        found = self.get_pulses_df(pattern=pattern)
        return found

    def get_pulses_df(self, pattern='*:*/*') -> DataFrame:
        pulses_list = self.UCR.getPulses2(pattern)
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return DataFrame(columns=['Pulse', 'Time From', 'Time To', 'Duration', 'Status', 'Description'])
        pulse_df = DataFrame([[
            line.pulseID,
            pd.to_datetime(line.timeFrom),
            pd.to_datetime(line.timeTo),
            pd.to_datetime(line.timeTo) - pd.to_datetime(line.timeFrom),
            line.status.strip(),
            line.description]
            for line in pulses_list],
            columns=['Pulse', 'Time From', 'Time To', 'Duration', 'Status', 'Description'])
        return pulse_df

    def get_cbs_list(self, sep=':', pattern='*', times='0') -> List[str]:
        cbs_list = self.UCR.getCbsList(sep, pattern, times)
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return []
        return cbs_list

    def get_cbs_dict(self, sep=':', pattern='*', times='0') -> dict:
        cbs_list = self.get_cbs_list(sep, pattern, times)
        cbs_dict = dict()
        for line in cbs_list:
            cur_dict = cbs_dict
            list_line = line.split('-')
            for var in list_line:
                if var.endswith('?V'):
                    cur_dict = cur_dict.setdefault('-'.join(list_line).replace('?V', ''), '')
                else:
                    cur_dict = cur_dict.setdefault(var, {})

        return cbs_dict

    def get_var_list(self, pattern='.*') -> List[str]:
        var_list = self.UCR.getVariableList(pattern)
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return []

        return var_list

    def get_var_dict(self, pattern='.*', path=None) -> dict:
        var_list = self.get_var_list(pattern)
        if path:
            var_dict = self.parse_vars_to_dict(var_list, path)
        else:
            var_dict = self.parse_search_to_dict(var_list)

        return var_dict

    def get_var_fields(self, variable, timestamp='-1'):
        uda_type = self.UCR.getMetaTypeJSONCollapsed(variable, str(timestamp))
        if self.UCR.getErrorCode() != 0:
            logger.error(f"Response error. Error: {self.UCR.getErrorCode()} {self.UCR.getErrorMsg()}")
            return None

        if uda_type:
            js_nested = json.loads(uda_type, object_pairs_hook=collections.OrderedDict)
            dt = nDT.NestedDatatype("")
            dt.load_uda_json(js_nested)
            fdt = dt.flat_datatype("")
            return fdt.fields_to_json()

        return None

    def get_data_i(self, uda_p):
        dobj = dataCommon.DataObj()
        query = None
        isnew = 0
        logger.debug(" entering getDataI for pulse=%s", uda_p.pulse)
        if not self.connected:
            self.connect()
            if self.errcode == -1:
                dobj.set_err(self.errcode, self.errdesc)
                return dobj
        # If venv extremities is activated disable extSamples option in query
        if os.getenv("MINT_GET_EXTRE") is None or os.getenv("MINT_GET_EXTRE").lower() == "false":
            ext_query = f",extSamples={uda_p.extSamples}"
        else:
            ext_query = ""

        # we query always absolute to ease adding first and last data point, and we transform the data afterward
        if uda_p.pulse is None or uda_p.pulse == "None":
            query1 = (f"variable={uda_p.varname},tsFormat={uda_p.tsFormat},decSamples={uda_p.nbps},"
                      f"startTime={uda_p.startT},endTime={uda_p.endT}{ext_query}")
        else:
            if uda_p.pulse == "0":
                uda_p.pulse = self.UCR.getLastPulse()
                logger.debug("LAST PULSE: %s", uda_p.pulse)
            # we need to check if it is an-going pulse to not use the cache...
            if uda_p.pulse not in self.pulses_cache.keys():
                pulse_i = self.get_pulse_info(uda_p.pulse)
                isnew = 1
                logger.debug(" do not use cache for pulse=%s", uda_p.pulse)
            else:
                pulse_i = self.pulses_cache.get(uda_p.pulse)
                logger.debug(" use cache for pulse=%s", uda_p.pulse)
            if pulse_i is None:
                return query
            # ongoing pulse
            if pulse_i.timeTo >= time.time_ns() and (
                    uda_p.endT is None or pulse_i.timeFrom + int(uda_p.endT * 1000000000) >= time.time_ns()):

                uda_p.endT = math.ceil((time.time_ns() - pulse_i.timeFrom) / 1000000000)

                # get
                logger.debug("current pulse et=%d st=%d", uda_p.endT, uda_p.startT)

                # to bypass the cache we explicitly move the end time...udaP.tsFormat,
                query1 = (f"variable={uda_p.varname},tsFormat={uda_p.tsFormat},decSamples={uda_p.nbps},"
                          f"pulse={uda_p.pulse},startTime={uda_p.startT}S,endTime={uda_p.endT}S{ext_query}")

            else:
                if isnew == 1:
                    self.pulses_cache.update({uda_p.pulse: pulse_i})
                    logger.debug(f"completed pulse tsE={uda_p.endT},tsS={uda_p.startT} and added to the cache")
                if uda_p.endT is None:
                    query1 = (f"variable={uda_p.varname},tsFormat={uda_p.tsFormat},decSamples={uda_p.nbps},"
                              f"pulse={uda_p.pulse},startTime={uda_p.startT}S{ext_query}")
                else:
                    query1 = (f"variable={uda_p.varname},tsFormat={uda_p.tsFormat},decSamples={uda_p.nbps},"
                              f"pulse={uda_p.pulse},startTime={uda_p.startT}S,endTime={uda_p.endT}S{ext_query}")

        if uda_p.decType is not None:
            query = query1 + f",decType={uda_p.decType}"
        else:
            query = query1
        return query

    def clear_cache(self):
        self.access_cache.clear()
        self.pulses_cache.clear()

    @cachedmethod(operator.attrgetter('access_cache'))
    def __fetch_data_with_cache(self, query):
        return self.__fetch_data_x(query)

    @cachedmethod(operator.attrgetter('access_cache'))
    def __fetch_envelope_with_cache(self, query):
        return self.__fetch_envelope(query)

    def __fetch_data_x(self, query):
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
            for s in self.__NO_DATA_FOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode = -3
                    found = 1
                    break
            if found == 0:
                self.UCR.resetAll()

            dobj.set_err(self.errcode, self.errdesc)
            return dobj

        # self.dataR.clearData()
        dobj.set_a(self.convert_uda_types(self.UCR.getFetchedTimeType(handle)),
                   self.convert_uda_types(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                   self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                   self.UCR.getRank(handle))

        if dobj.ytype == dataCommon.DataType.DA_TYPE_STRING:
            dobj.set_data(self.UCR.getDataAsStrings(handle), 2)
        else:
            dobj.set_data(self.UCR.getDataNativeRank(handle), 2)
        if dobj.ydata is None:
            self.UCR.releaseData(handle)
            self.errdesc = f"No data found for query '{query}'"
            self.errcode = -3
            # self.UCR.resetAll()
            dobj.set_err(self.errcode, self.errdesc)

            return dobj

        if dobj.xtype == dataCommon.DataType.DA_TYPE_FLOAT or dobj.xtype == dataCommon.DataType.DA_TYPE_DOUBLE:
            dobj.set_data(self.UCR.getTimeStampsAsDouble(handle), 1)
        else:
            dobj.set_data(self.UCR.getTimeStampsAsLong(handle), 1)

        self.UCR.releaseData(handle)
        dobj.set_err(0, "OK")
        logger.debug("Query ZZ: %s and errcode=%d", query, self.errcode)
        return dobj

    # @cached(cache=LRUCache(maxsize=100))
    def __fetch_envelope(self, query):
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
            for s in self.__NO_DATA_FOUND:
                if s in self.errdesc:
                    self.UCR.releaseData(handle)
                    self.errcode = -3
                    found = 1
                    break
            if found == 0:
                self.UCR.resetAll()

            d_env.set_err(self.errcode, self.errdesc)
            return d_env
        if d_env.ytype == dataCommon.DataType.DA_TYPE_STRING:
            # we should not be there but...
            d_env.set_err(-1, "Envelope has no meaning for string datatypes")
            return d_env
        # self.dataR.clearData()
        d_env.set_a(self.convert_uda_types(self.UCR.getFetchedTimeType(handle)),
                    self.convert_uda_types(self.UCR.getFetchedType(handle)), self.UCR.getLabelX(handle),
                    self.UCR.getLabelY(handle), self.UCR.getUnitsX(handle), self.UCR.getUnitsY(handle),
                    self.UCR.getRank(handle))

        data = self.UCR.getDataNativeRank(handle)

        if data is None:
            self.UCR.releaseData(handle)
            self.errdesc = f"No data found for query '{query}'"
            self.errdesc = -3
            # self.UCR.resetAll()
            d_env.set_err(self.errcode, self.errdesc)

            return d_env

        d_env.set_y_data(data[:, 1], data[:, 2], data[:, 0])
        if d_env.xtype == dataCommon.DataType.DA_TYPE_FLOAT or d_env.xtype == dataCommon.DataType.DA_TYPE_DOUBLE:
            d_env.set_x_data(self.UCR.getTimeStampsAsDouble(handle))
        else:
            d_env.set_x_data(self.UCR.getTimeStampsAsLong(handle))

        self.UCR.releaseData(handle)
        d_env.set_err(0, "OK")
        return d_env

    def get_envelope(self, **kwargs):
        kwargs['decType'] = "env"

        uda_p = self.get_uda_params(**kwargs)
        query = self.get_data_i(uda_p)
        if query is None:
            dobj = dataCommon.DataEnvelope()
            dobj.set_err(-1, "Invalid Pulse ID")
            logger.debug("getEnveloppe exiting pulse does not exist")
            return dobj

        tobe_cached = self.check_to_add_in_cache(uda_p)

        if tobe_cached:
            d_env = self.__fetch_envelope_with_cache(query)
        else:
            d_env = self.__fetch_envelope(query)
        logger.debug("getEnveloppe exiting pulse does exist ")
        return d_env

    @staticmethod
    def parse_search_to_dict(lines: List[str]) -> dict:
        """
        Parses a list of lines representing search strings and organizes them into a dictionary.
        :param lines: A list of strings representing search strings to be parsed.
        :return: A dictionary containing the parsed search strings organized hierarchically.
        """
        result = dict()
        for line in lines:
            list_line = line.replace(':', '-:', 1).split('-')
            cur_dict = result
            for ix in range(len(list_line)):
                if ix == len(list_line) - 1:
                    cur_dict = cur_dict.setdefault('-'.join(list_line).replace('-:', ':', 1), '')
                elif list_line[ix][0] == ':':
                    temp = '-'.join(list_line[:ix + 1]).replace('-:', ':')
                    if cur_dict.get(temp, None) != "":
                        cur_dict = cur_dict.setdefault(temp, {})
                    cur_dict = cur_dict.setdefault('-'.join(list_line).replace('-:', ':', 1), '')
                    break
                else:
                    cur_dict = cur_dict.setdefault(list_line[ix], {})

        return result

    @staticmethod
    def parse_vars_to_dict(lines: List[str], path: str) -> dict:
        """
        Parses a list of lines and organizes them into a dictionary based on a specified pattern.
        :param lines: A list of strings representing lines to be parsed.
        :param path : A string representing the pattern to be used for organizing the lines.
        :return dict: A dictionary containing the parsed lines organized according to the specified pattern.

        Example:
            lines = ['x:a-b','x:b-c','x:a-c']
            pattern = 'x'
            result = parse_vars_to_dict(lines, pattern)
            # Output:
            # {
            #   'x:a': {'x:a-b': '', 'x:a-c': ''},
            #   'x:b-c': ''
            # }
        """
        result = {}
        folder_names = [line.split(':')[1].split('-')[0] for line in lines]
        folder_counts = collections.Counter(folder_names)
        for ix, line in enumerate(lines):
            folder = folder_names[ix]
            if folder_counts[folder] > 1:
                key = f'{path}:{folder}'
                if key not in result:
                    result[key] = {}
                result[key][line] = ''
            else:
                result[line] = ''

        return result
