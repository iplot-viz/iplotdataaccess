import numpy as np
from enum import Enum
from collections import deque
from iplotDataAccess.dataCommon import DataObj, DataType
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)
try:
    import requests

except ModuleNotFoundError:
    logger.warning("import'requests' is not installed")

try:
    import sseclient

    print("sseclient is installed")
except ModuleNotFoundError:
    logger.warning("import'sseclient' is not installed")

try:
    import getpass
except ModuleNotFoundError:
    logger.warning("import getpass is not installed")


class RTStreamerException(Exception):
    pass


class ProtoHeader(Enum):
    VARNAME = 0
    TIME_DT = 1
    VAL_DT = 2
    NB_SMP = 3


class VarType(Enum):
    pon = "P"
    dan = "D"
    sdn = "S"


class RTStreamer:
    def __init__(self, url=None, headers=None, auth=None, uda_a=None):
        self.urlX = url or 'https://controls.iter.org/dashboard/backend/sse'
        self.params = None
        self.origparams = []
        self.origparams1 = []
        self.username = None
        self.password = None
        self.auth = auth
        self.response = None
        self.client = None
        self.__status = "INIT"
        self.__units = {}
        self.__enums = {}
        # self.headers = {'User-Agent': 'it_script_basic'}
        self.headers = headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
        # headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
        self.vardata = {}

        self.maxsizeP = 100
        self.maxsize = 1000
        self.udaAccess = uda_a
        self.__check_and_fill_headers()

    # logging.basicConfig(filename="/tmp/output_pro.log", format='%(asctime)s -%(levelname)s-%(funcName)s-%(message)s',
    # datefmt='%Y-%m-%dT%H:%M:%S', level=logging.DEBUG)
    # self.logger = logging.getLogger(__name__)

    def __check_and_fill_headers(self):
        logger.debug("headers is %s and type is %s ", self.headers, type(self.headers))
        for k, v in self.headers.items():
            if v == "$USERNAME":
                self.headers[k] = getpass.getuser()

    def __set_params(self, params=None):
        if params is None:
            params = []
        self.origparams1 = params
        if params is not None and len(params) > 0:
            p1 = set(params)
            self.params = "variables=" + ",".join(p1)
            if self.udaAccess is None:
                logger.warning(" no uda data access defined cannot get the units")
                return
            for s in p1:
                try:
                    self.__units[s] = self.udaAccess.get_unit(s)
                except Exception:
                    # Units are cosmetic; a metadata failure must not block the subscription.
                    logger.warning(f"Could not fetch unit for {s}")
                try:
                    labels = self.udaAccess.get_var_enum(s)
                    if labels:
                        self.__enums[s] = labels
                except Exception:
                    logger.warning(f"Could not fetch enum labels for {s}")

    @staticmethod
    def __convert_type(utype):

        if utype in ["D", "PD", "ED"]:
            return DataType.DA_TYPE_DOUBLE
        elif utype == "L":
            return DataType.DA_TYPE_LONG
        elif utype == "S" or utype == "PS":
            return DataType.DA_TYPE_STRING

    @staticmethod
    def __check_if_duplicate(varname, params=None):
        if params is None:
            params = []
        duplicated_index = []
        search_start_idx = 0

        while True:
            try:
                idx = params.index(varname, search_start_idx)
                duplicated_index.append(idx)
                search_start_idx = idx + 1
            except ValueError:
                break
        logger.debug("check duplicate %s %s %s", varname, params, duplicated_index)
        return duplicated_index

    def __create_queues(self, vkeys, vtype, data, params=None):
        if params is None:
            params = []
        logger.debug(f'create queues for vkeys={vkeys}')
        for vk in vkeys:
            sname = params[vk] + '@' + str(vk)
            if self.vardata.get(sname) is not None:
                logger.debug("adding data to queue for vname=%s", sname)
                self.vardata[sname].append(data)
            else:
                logger.debug(f'create queue for vname={sname}')
                if vtype.startswith(VarType.pon.value):
                    self.vardata[sname] = deque([data], self.maxsizeP)
                else:
                    self.vardata[sname] = deque([data], self.maxsize)

    def __parse_data(self, data, params=None):
        if params is None:
            params = []
        if data.startswith("heartbeat"):
            return
        line = data.split()
        if len(line) <= 1:  # If data is only one token, it is only time
            return

        num_samples = int(line[ProtoHeader.NB_SMP.value])
        xtype = DataType.DA_TYPE_ULONG
        xlabel = "Time"
        xunit = "ns"
        ylabel = ""
        drank = 1
        try:
            ytype = self.__convert_type(line[ProtoHeader.VAL_DT.value])
        except IndexError as _:
            logger.warning(f"index error for line {line}")
            return
        if ytype == DataType.DA_TYPE_STRING:
            enum_labels = self.__enums.get(line[ProtoHeader.VARNAME.value])
            if enum_labels is None:
                logger.debug("string not currently supported for streaming, skipping")
                return
            self.__queue_enum_samples(line, num_samples, enum_labels,
                                      xlabel, xunit, params=params)
            return

        if line[ProtoHeader.VAL_DT.value] == 'PD':
            values = [[line[4 + i], line[5 + num_samples + 4*i]] for i in range(num_samples)]
        elif line[ProtoHeader.VAL_DT.value] == "ED":
            values = [[line[4 + i]] + line[4 + num_samples + i: 7 + num_samples + i] for i in range(num_samples)]
        else:
            values = [[line[4 + i], line[4 + num_samples + i]] for i in range(num_samples)]
            # TODO
            # protect the code in case of event mixing up
            # ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513472231 ', '0.421761 NO_ALARM NO_ALARM']
            # ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513480496 ', '0.333320 NO_ALARM NO_ALARM']
            # ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513492192 ', '0.000000 NO_ALARM NO_ALARM']
            # ['UTIL-HV-S22:TOTAL_POWER_LC13 L PD 2 1629706018897 1629706018901  E[9] Connected ',
            # '0.000000 NO_ALARM NO_ALARM']
            # ['UTIL-HV-S22:TOTAL_POWER_LC13 L PD 2 1629706018897 1629706018901  E[9] Connected ',
            # '0.000000 NO_ALARM NO_ALARM']

            if len(values) < num_samples + 1:
                logger.warning(f"sline mixing event and data skipping {values}")
            return
        xdata = np.zeros(num_samples, dtype='uint64')
        ydata = np.zeros(num_samples)
        d = DataObj()
        yunit = self.__units.get(line[ProtoHeader.VARNAME.value])
        d.set_a(xtype, ytype, xlabel, ylabel, xunit, yunit, drank)

        for i, val in enumerate(values):
            xdata[i] = int(val[0]) * 1000000
            ydata[i] = float(val[1])

        d.set_data(xdata, 1)
        d.set_data(ydata, 2)
        # logger.debug("before calling check duplicate")
        vkeys = self.__check_if_duplicate(line[ProtoHeader.VARNAME.value], params=params)
        self.__create_queues(vkeys, line[ProtoHeader.VAL_DT.value], d, params=params)

    def __queue_enum_samples(self, line, num_samples, labels, xlabel, xunit, params=None):
        # Enumerated state PVs arrive as "V[<len>] <label>" per sample; the feed
        # carries only the label, so map it to its enum index (list position).
        if params is None:
            params = []
        varname = line[ProtoHeader.VARNAME.value]
        xdata = np.zeros(num_samples, dtype='uint64')
        ydata = np.zeros(num_samples)
        valid = 0
        for i in range(num_samples):
            try:
                ts = int(line[4 + i])
                label = line[4 + num_samples + 4 * i + 1]
            except (IndexError, ValueError):
                logger.debug(f"enum sample parse skipped for {line}")
                continue
            if label not in labels:
                logger.debug(f"unknown enum label {label} for {varname}")
                continue
            xdata[valid] = ts * 1000000
            ydata[valid] = labels.index(label)
            valid += 1
        if valid == 0:
            return
        d = DataObj()
        yunit = self.__units.get(varname)
        d.set_a(DataType.DA_TYPE_ULONG, DataType.DA_TYPE_LONG, xlabel, "", xunit, yunit, 1)
        d.set_data(xdata[:valid], 1)
        d.set_data(ydata[:valid], 2)
        vkeys = self.__check_if_duplicate(varname, params=params)
        self.__create_queues(vkeys, line[ProtoHeader.VAL_DT.value], d, params=params)

    def get_status(self):
        return self.__status

    def start_subscription(self, params=None, origparams=None):
        if origparams is None:
            origparams = []
        if params is None:
            params = []
        if self.__status == "STARTED":
            logger.error("Subscription is already started, needs to be stopped first or launch a new RTStreamer")
            raise RTStreamerException(" Streamer already started")
        self.__set_params(params)
        url1 = self.urlX + '?' + self.params
        logger.debug("starting sub header=%s and uri=%s", self.headers, url1)

        # response = requests.get(url=url1, stream=True, headers=self.headers, auth=self.auth, timeout=None)
        try:
            self.response = requests.get(url=url1, stream=True, headers=self.headers, timeout=None)
        except ConnectionError as ce:
            logger.error("got connection error %s with errcode = %d ", ce, self.response.status_code)
            self.__status = "ERROR"
            raise RTStreamerException(" could not connect - see log for more details")
        # print(response.headers)
        self.origparams = origparams
        paramsT = params
        logger.debug(" origparm %s  param=%s ", self.origparams, self.params)
        self.client = sseclient.SSEClient(self.response)
        self.__status = "STARTED"
        try:
            for event in self.client.events():
                logger.debug(f'found new data {event.data}')
                if self.__status == "STOPPING":
                    logger.info("receiving stop request")
                    break
                self.__parse_data(event.data, params=paramsT)
        except ConnectionError as _:
            self.__status = "ERROR"
            raise RTStreamerException(" connection lost - see log for more details")
        except Exception:
            # stop_subscription() closes the response to unblock this loop;
            # the resulting read error is a normal stop, not a failure.
            if self.__status != "STOPPING":
                self.__status = "ERROR"
                raise
        self.client.close()
        self.response.close()
        if self.vardata is not None:
            for k in self.vardata.keys():
                self.vardata[k].clear()
        self.__status = "STOPPED"

    def __get_next_data_i(self, vname):
        try:
            # logger.debug(" vname=%s origparm %s  self=%s ", vname,self.origparams,self.origparams1)

            idx = self.origparams.index(vname)
            sname = self.origparams1[idx] + "@" + str(idx)
            if sname in self.vardata.keys():
                dobj = self.vardata[sname].popleft()
            else:
                dobj = DataObj()
                dobj.set_empty("varname not in the keys")

        except ValueError:
            dobj = DataObj()
            dobj.set_empty("Value error : varname not in the keys")
        # logger.debug("invalid get next data call variable %s not in the list",vname)
        except IndexError:
            dobj = DataObj()
            dobj.set_empty("Index error : varname not in the keys")
        # logger.debug("invalid get next data call variable %s no data in the list",vname)

        return dobj

    # expect orig name with expression -> handle the case where we subscribe to the same variable but different
    # expressions are applied to them
    def get_next_data(self, vname=None):
        # logger.debug("got a call vanme=%s",vname)
        if vname is None:
            dobj = DataObj()
            dobj.set_empty("Varname is empty")
            return dobj

        dobj = self.__get_next_data_i(vname)
        if len(dobj.xdata) == 0:
            dobj = DataObj()
            dobj.set_empty("No data found")
        else:
            logger.debug(f'vname={vname} timestamp {dobj.xdata} and val={dobj.ydata}')
        return dobj

    def stop_subscription(self):
        logger.debug("receving stop subscription")
        if self.__status == "STARTED":
            self.__status = "STOPPING"
            logger.debug('stopping subscription')
            # Close the SSE response so the blocking events() loop unblocks
            # immediately instead of waiting for the next server event.
            try:
                if self.response is not None:
                    self.response.close()
            except Exception:
                logger.debug("closing SSE response raised; loop will exit on next event")
        elif self.__status != "STOPPING":
            logger.warning(f'ignored stopping subscription because of status of {self.__status}')
