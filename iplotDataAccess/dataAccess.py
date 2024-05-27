import copy
import os
import time
from typing import Dict, List, Union

import iplotDataAccess.dataSourceConfig as dSC
from iplotLogging import setupLogger

from iplotDataAccess.dataCommon import DataObj, DataEnvelope

logger = setupLogger.get_logger(__name__)

# Should import possible data sources like IMAS UDA and CODAC UDA
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


class RTHException(Exception):
    pass


class DataSource:

    def __init__(self, dtype=None, name=None):
        self.connected = False
        self.rtStatus = "UNEXISTING"
        self.errcode = 0
        self.rterrcode = 0
        self.errdesc = ""
        self.UCR = None
        self.varprefix = None
        self.dtype = ""
        self.connectionString = None
        self.daHandler = None
        self.RTHandler = None
        self.rth = None
        self.rta = None
        self.rtu = None
        self.MAX_ITER = 1000
        self.SLEEP_TO = 0.1
        self.default = False
        if name is None:
            self.name = "DS _" + str(id(self))
        else:
            self.name = name
        if dtype == dSC.DS_CODAC_TYPE:
            self.connectionString = "host=X,port=3090"
        elif dtype == dSC.DS_IMAS_TYPE:
            self.connectionString = "database=ITER,path=public,backend=MDSPLUS"
        self.dtype = dtype

    def set_connection_string(self, conninfo):
        self.connectionString = conninfo
        if "host" in conninfo:
            self.dtype = dSC.DS_CODAC_TYPE
        elif "database" in conninfo:
            self.dtype = dSC.DS_IMAS_TYPE

    def set_default_ds(self, default):
        self.default = default

    def set_var_prefix(self, pref):
        self.varprefix = pref

    def set_rt_headers(self, headers):
        self.rth = headers

    def set_rt_auth(self, auth):
        self.rta = auth

    def set_rt_url(self, url):
        self.rtu = url

    def set_rt_handler(self):
        myhd = {}
        if self.dtype == dSC.DS_IMAS_TYPE:
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
            self.RTHandler = iplotDataAccess.realTimeStreamer.RTStreamer(url=self.rtu, headers=myhd, auth=self.rta,
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

    def connect(self):
        if self.dtype == dSC.DS_IMAS_TYPE:
            try:
                self.daHandler = iplotDataAccess.imasAccess.IMASDataAccess()
                self.connected = self.daHandler.connect_source(connection_string=self.connectionString)
            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        elif self.dtype == dSC.DS_CODAC_TYPE:
            try:
                self.daHandler = iplotDataAccess.udaAccess.UdaAccess()
                logger.debug("connect %s ", self.connectionString)
                self.connected = self.daHandler.connect_source(connection_string=self.connectionString)

            except ModuleNotFoundError:
                self.errcode = -1
                self.connected = False

        if self.rtu is not None:
            try:
                logger.debug("setRHandler")
                self.set_rt_handler()
            except RTHException as rte:
                logger.error(" RTHException %s ", rte)

    def start_subscription(self, **kwargs):
        for _ in range(20):  # Time to update real status if it is STARTED (2 s)
            if self.rtStatus != "STARTED":
                break
            time.sleep(0.1)
        else:
            logger.warning('Started subscription with status STARTED')

        if self.rtStatus in ["STARTED", "STOPPED"]:
            for _ in range(60):  # Wait for real status (60 s)
                if self.rtStatus == self.RTHandler.get_status():
                    break
                logger.debug('Waiting status sync for RTHandler')
                time.sleep(1)
            else:
                logger.warning('Subscription and RT handler have different status')

        if self.rtStatus in ["INITIALISED", "STOPPED"]:
            try:
                self.rtStatus = "STARTED"
                logger.debug("startSubscription ")
                newparams = kwargs.get("params")

                kwargs["origparams"] = copy.deepcopy(kwargs.get("params"))
                kwargs["params"] = newparams
                logger.debug("start sub with params=%s and origparams=%s", kwargs["params"], kwargs["origparams"])
                self.RTHandler.start_subscription(**kwargs)
            except iplotDataAccess.realTimeStreamer.RTStreamerException:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def stop_subscription(self):
        logger.debug("stopSubscription Y %s ", self.rtStatus)
        if self.rtStatus == "STARTED":
            try:
                logger.debug("stopSubscription Z ")
                self.RTHandler.stop_subscription()
                self.rtStatus = "STOPPED"
            except iplotDataAccess.realTimeStreamer.RTStreamerException as _:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def get_next_data(self, vname=None):
        counter = 0
        # Could happen that params is null if this call is done before startSubscription
        while (self.RTHandler is None or self.RTHandler.params is None) and counter < self.MAX_ITER:
            time.sleep(self.SLEEP_TO)
            counter = counter + 1
        if counter == self.MAX_ITER:
            dobj = DataObj()
            dobj.set_empty("Streamer not properly initialized: did the subscription start?")
            return dobj

        return self.RTHandler.getNextData(vname)

    def __get_data_i(self, **kwargs):
        return self.daHandler.get_data(**kwargs)

    def clear_cache(self):
        return self.daHandler.clear_cache()

    def get_data(self, **kwargs):
        logger.debug("getdata of data source and type %s", self.dtype)

        try:
            if self.daHandler is None:
                dobj = DataObj()
                dobj.set_empty(self.dtype + "_DataHandler is null")
            else:
                varname = kwargs.get("varname")
                logger.debug(f"varname: {varname}")
                dobj = self.__get_data_i(**kwargs)

                if dobj.ydata is not None and len(dobj.ydata) > 0:
                    logger.debug(f"dtype: {dobj.ytype}")
                    logger.debug(f"actual dtype: {type(dobj.ydata)}")

        except ModuleNotFoundError:
            dobj = DataObj()
            dobj.set_empty("ModuleNotFound_" + self.dtype)
        logger.debug("exiting getdata")
        return dobj

    def __get_envelope_i(self, **kwargs):
        return self.daHandler.get_envelope(**kwargs)

    def get_envelope(self, **kwargs):
        ret = (None, None)
        try:
            if self.daHandler is None:
                dobj = DataEnvelope()
                dobj.set_empty(self.dtype + "_DataHandler is null")
            else:
                varname = kwargs.get("varname")
                logger.debug(f"varname: {varname}")
                ret = self.__get_envelope_i(**kwargs)

                if ret.errcode == 0 and ret.xdata is not None and len(ret.xdata) > 0:
                    logger.debug(f"dtype: {ret.ytype}")
                    logger.debug(f"actual dtype: {type(ret.ydata_min)}")

        except ModuleNotFoundError:
            logger.warning("ModuleNotFound_%s", self.dtype)
        return ret

    def get_pulse_list(self, **kwargs):
        return self.daHandler.get_pulses(**kwargs)

    def get_cbs_list(self, **kwargs):
        return self.daHandler.get_cbs_list(**kwargs)

    def get_var_list(self, **kwargs):
        return self.daHandler.get_var_list(**kwargs)

    def get_var_fields(self, **kwargs):
        return self.daHandler.get_var_fields(**kwargs)


# class to interface with data source - here UDA
class DataAccess:
    DEFAULT_DATA_SOURCES_CFG_FILE: str = 'mydatasources.cfg'

    def __init__(self):
        d = dSC.DataSourceConfig()
        self.proto: List[str] = d.get_supported_data_source()
        self.dslist: Dict[str, DataSource] = {}
        self.defaultds: Union[DataSource, None] = None
        self.confFile: str = ""

    def get_default_ds_name(self):
        if self.defaultds is None:
            return None
        else:
            return self.defaultds.name

    def load_config(self, conf_file=None):
        if conf_file is None:
            conf_file = os.environ.get('IPLOT_SOURCES_CONFIG')
            if conf_file is None:
                conf_file = self.DEFAULT_DATA_SOURCES_CFG_FILE
        self.confFile = conf_file
        try:
            return self.load_config_file(conf_file)
        except (OSError, IOError, FileNotFoundError) as _:
            if self.confFile == DataAccess.DEFAULT_DATA_SOURCES_CFG_FILE:
                return False
            conf_file = os.environ.get('IPLOT_SOURCES_CONFIG')
            if (conf_file is None) or (conf_file == self.confFile):
                conf_file = DataAccess.DEFAULT_DATA_SOURCES_CFG_FILE
            if self.confFile == conf_file:
                return False
            logger.warning(f"no {self.confFile} data source file, fallback to {conf_file}")
            return self.load_config(conf_file)

    def load_config_file(self, dspath):
        dskeys = []
        dname = ""
        with open(dspath) as f:
            for line in f:

                if line.rstrip().startswith("[") and line.rstrip().endswith("]"):
                    s = line.rstrip()
                    dname = s[s.find("[") + 1:s.find("]")]
                    ds = DataSource(name=dname)
                    self.dslist[dname] = ds

                if line.rstrip().startswith("conninfo") and dname != "":
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].set_connection_string(s)
                if line.rstrip().startswith("rturl") and dname != "":
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].set_rt_url(s)
                if line.rstrip().startswith("rtauth") and dname != "":
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].set_rt_auth(s)
                if line.rstrip().startswith("rtheaders") and dname != "":
                    s = line.rstrip().split("=", 1)[1]
                    self.dslist[dname].set_rt_headers(s)
                if line.rstrip().startswith("default") and dname != "":
                    s = line.rstrip().split("=", 1)[1].lower()
                    self.dslist[dname].set_default_ds(s == "true")

                if line.rstrip().startswith("varprefix") and dname != "":
                    s = line.rstrip().split("=", 1)[1]
                    logger.debug("found varprefix %s", s)
                    self.dslist[dname].set_var_prefix(s)

        # print("supported dslist ",self.dslist[0])
        for k, d in self.dslist.items():
            logger.info("data name=%s data type=%s connfino=%s", d.name, d.dtype, d.connectionString)

            if d.dtype in self.proto:
                d.connect()
                if d.connected:
                    dskeys.append(d)
            else:
                logger.info("data source not supported %s", d.name)

        # Check which data source to set by default
        for key in dskeys:
            if key.default:
                self.defaultds = key
                break

        # Set a default ds even if none is marked as default
        if not self.defaultds and dskeys:
            self.defaultds = dskeys[0]

        return len(dskeys) > 0

    def add_data_source(self, data_s=None):
        self.dslist[data_s.name] = data_s

    def get_data_source(self, data_s_name):
        logger.debug("entering getDataSource  %s", data_s_name)
        if data_s_name is None:
            if self.defaultds is not None:
                logger.info(" default source used ")
                return self.defaultds
            else:
                logger.error("DataSourceName is None and not default data source name has been defined")
                return None
        if data_s_name not in self.dslist.keys():
            logger.warning(" Data source %s not found", data_s_name)
            return None
        else:
            ds = self.dslist[data_s_name]
            if ds is None:
                logger.debug("Invalid data source pointer for ds name  %s", data_s_name)
            return ds

    def connect(self, data_s_name):
        for ds in self.dslist:
            if ds.name == data_s_name:
                return ds.connect()
        return None

    def get_data(self, data_s_name, **kwargs):
        # we can use the var prefix to get the data source while we introduce
        logger.debug("entering getdata  %s", data_s_name)
        if data_s_name is not None and data_s_name in self.dslist.keys():
            if self.dslist[data_s_name] is None:
                dobj = DataObj()

                dobj.set_empty("Invalid data source pointer for ds name " + data_s_name)
                logger.debug("Invalid data source pointer for ds name  %s", data_s_name)
                return dobj
            else:

                dobj = self.dslist[data_s_name].get_data(**kwargs)
                return dobj
        else:
            if data_s_name not in self.dslist.keys():
                logger.warning(" Invalid data source found %s ", data_s_name)
                dobj = DataObj()
                dobj.set_empty(f"Invalid data source name {data_s_name}")

                return dobj
            if self.defaultds is not None:
                logger.info(" default source used ")
                return self.defaultds.get_data(**kwargs)

        return None

    def start_subscription(self, data_s_name, **kwargs):
        if data_s_name is not None and data_s_name in self.dslist.keys():
            self.dslist[data_s_name].start_subscription(**kwargs)

    def stop_subscription(self, data_s_name):
        if data_s_name is not None and data_s_name in self.dslist.keys():
            logger.debug("stopSubscription A ")
            self.dslist[data_s_name].stop_subscription()

    def get_next_data(self, data_s_name, vname):
        if data_s_name is not None and data_s_name in self.dslist.keys():
            return self.dslist[data_s_name].get_next_data(vname)
        else:
            dobj = DataObj()
            dobj.set_empty(f"Invalid data source name {data_s_name}")
            return dobj

    def get_envelope(self, data_s_name, **kwargs):
        if data_s_name is not None and data_s_name in self.dslist.keys():
            if self.dslist[data_s_name] is None:
                denv = DataEnvelope()
                denv.set_empty(f"Invalid data source pointer for ds name {data_s_name}")

                return denv
            else:
                return self.dslist[data_s_name].get_envelope(**kwargs)
        else:
            if data_s_name not in self.dslist.keys():
                logger.warning(f"Invalid data source found {data_s_name}")
                denv = DataEnvelope()
                denv.set_empty(f"Invalid data source name {data_s_name}")

                return denv
            if self.defaultds is not None:
                logger.info("default source used ")
                return self.defaultds.get_envelope(**kwargs)

        return None

    def get_pulse_list(self, data_source_name, **kwargs):
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return None
        pulse_list = ds.get_pulse_list(**kwargs)
        return pulse_list

    def get_cbs_list(self, data_source_name, **kwargs):
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return None
        cbs_list = ds.get_cbs_list(**kwargs)
        return cbs_list

    def get_var_list(self, data_source_name, **kwargs):
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return None
        var_list = ds.get_var_list(**kwargs)
        return var_list

    def get_var_fields(self, data_source_name, **kwargs):
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return None
        return ds.get_var_fields(**kwargs)

    # TODO change to a better name
    def get_connected_data_sources(self):
        data_sources = [self.get_default_ds_name()]
        for ds_name, ds in self.dslist.items():
            if ds_name not in data_sources and ds.connected:
                data_sources.append(ds_name)
        return data_sources

    # TODO change to a better name
    def get_connected_data_sources2(self):
        data_sources = []
        for ds_name, ds in self.dslist.items():
            if ds.connected:
                data_sources.append(ds)
        return data_sources

    # Clear cache of all the dataSources
    def clear_cache(self):
        for ds in self.dslist.values():
            if ds.connected:
                ds.daHandler.clear_cache()
