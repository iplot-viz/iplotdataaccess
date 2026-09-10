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
        # Optional controls metadata REST server publishing the variables
        # visible on HMI; widgets hide the related controls when a source
        # does not define one.
        self.controls_metadata = config.get("controlsmetadata")
        self._hmi_vars = None
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

    def get_archive_window(self, **kwargs):
        """Return archive data for a time window. Subclasses may override to
        apply caps or switch to envelope mode; ``env_nbp`` sizes that envelope
        fallback and is meaningless to a plain read."""
        kwargs.pop('env_nbp', None)
        return self.get_data(**kwargs)

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

    def get_hmi_var_dict(self, refresh: bool = False) -> dict:
        """Return the HMI variables published by the controls metadata server.

        Maps each variable name to a dict with keys ``description``, ``units``
        and ``type``. Returns an empty dict when the source has no
        controlsmetadata server configured or the request fails; the fetched
        list is cached until ``refresh`` is requested.
        """
        if not self.controls_metadata:
            return {}
        if self._hmi_vars is not None and not refresh:
            return self._hmi_vars

        import requests
        url = str(self.controls_metadata)
        if '://' not in url:
            url = f'http://{url}'
        try:
            # The controls metadata server lives inside the CODAC network:
            # bypass any http_proxy/https_proxy meant for external traffic.
            response = requests.get(f"{url.rstrip('/')}/variable_hmi", timeout=30,
                                    proxies={"http": None, "https": None})
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.error("Controls metadata request to %s failed: %s", url, exc)
            return {}

        self._hmi_vars = self._parse_hmi_body(body)
        return self._hmi_vars

    @staticmethod
    def _parse_hmi_body(body) -> dict:
        """Normalize the ``variable_hmi`` response into {name: metadata}.

        Accepts both a bare list of entries and a wrapper object holding one,
        and tolerates the unit/type key variants seen across REST endpoints.
        """
        if isinstance(body, dict):
            body = next((v for v in body.values() if isinstance(v, list)), None)
        if not isinstance(body, list):
            return {}

        result = {}
        for entry in body:
            if not isinstance(entry, dict):
                continue
            name = entry.get('variable') or entry.get('name')
            if not name:
                continue
            result[str(name)] = {
                'description': entry.get('description', ''),
                'units': entry.get('unit', entry.get('units', '')),
                'type': entry.get('data_type', entry.get('data type', entry.get('type', ''))),
            }
        return result

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
