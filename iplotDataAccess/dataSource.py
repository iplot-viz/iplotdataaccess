import copy
import time
from abc import ABC, abstractmethod
from typing import List

from pandas import DataFrame

from iplotDataAccess.dataCommon import DataObj, DataEnvelope
from iplotDataAccess.realTimeStreamer import RTStreamer, RTStreamerException
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

DS_CODAC_TYPE = "CODAC_UDA"
DS_IMASPY_TYPE = "IMASPY"
DS_CSV_TYPE = "CSV"

class RTHException(Exception):
    pass


class DataSource(ABC):
    source_type = None

    def __init__(self, name: str, config: dict):
        self.default = config.get("default", False)
        self.name = name
        # Stream config
        self.rtStatus = "UNEXISTING"
        self.errcode = 0
        self.rterrcode = 0
        self.errdesc = ""
        self.connectionString = None
        self.daHandler = None
        self.rth = None
        self.rta = None
        self.rtu = None
        self.MAX_ITER = 1000
        self.SLEEP_TO = 0.1

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Verify that derived class has 'source_type' defined
        if not hasattr(cls, 'source_type') or cls.source_type is None:
            raise TypeError(f"Class '{cls.__name__}' needs to define 'source_type'.")

    @abstractmethod
    def clear_cache(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def get_data(self, **kwargs) -> DataObj:
        pass

    @abstractmethod
    def get_envelope(self, **kwargs) -> DataEnvelope:
        pass

    @abstractmethod
    def search_pulses_df(self, text: str) -> DataFrame:
        pass

    @abstractmethod
    def get_pulse_info(self, **kwargs):
        pass

    @abstractmethod
    def get_pulses_df(self, **kwargs) -> DataFrame:
        pass

    @abstractmethod
    def get_cbs_dict(self, **kwargs) -> dict:
        pass

    @abstractmethod
    def get_var_dict(self, **kwargs) -> dict:
        pass

    def get_var_fields(self, **kwargs):
        pass

    def set_rt_headers(self, headers):
        self.rth = headers

    def set_rt_auth(self, auth):
        self.rta = auth

    def set_rt_url(self, url):
        self.rtu = url

    def set_rt_handler(self):
        myhd = {}
        if self.source_type != DS_CODAC_TYPE:
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

    @abstractmethod
    def connect(self) -> bool:
        if self.rtu is not None:
            try:
                logger.debug("setRHandler")
                self.set_rt_handler()
            except RTHException as rte:
                logger.error(" RTHException %s ", rte)
        return True

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
            except RTStreamerException:
                self.rtStatus = "ERROR"
                self.rterrcode = -2

    def stop_subscription(self):
        logger.debug("stopSubscription Y %s ", self.rtStatus)
        if self.rtStatus == "STARTED":
            try:
                logger.debug("stopSubscription Z ")
                self.RTHandler.stop_subscription()
                self.rtStatus = "STOPPED"
            except RTStreamerException as _:
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

        return self.RTHandler.get_next_data(vname)
