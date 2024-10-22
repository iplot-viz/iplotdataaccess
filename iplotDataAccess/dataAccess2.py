import json
import os
from typing import Dict, List, Union, Type

from iplotDataAccess.dataSource2 import DataSource2
from iplotLogging import setupLogger

from iplotDataAccess.dataCommon import DataObj, DataEnvelope

logger = setupLogger.get_logger(__name__)

DS_CODAC_TYPE = "CODAC_UDA"
DS_IMAS_TYPE = "IMAS_UDA"
DS_CSV_TYPE = "CSV"


# class to interface with data source - here UDA
class DataAccess2:
    DEFAULT_DATA_SOURCES_CFG_FILE: str = 'mydatasources.cfg'

    def __init__(self):
        self.proto: Dict[str, Type[DataSource2]] = self.get_supported_data_source()
        self.ds_list: Dict[str, DataSource2] = {}
        self.default_ds: Union[DataSource2, None] = None

    @staticmethod
    def get_supported_data_source() -> Dict[str, Type[DataSource2]]:
        supported_data_sources = {}
        # Check CODAC UDA module is installed
        try:
            import uda_client_reader
            logger.info("module 'uda client reader' is installed")

            from iplotDataAccess.udaAccess2 import UdaAccess2
            logger.info("module 'uda client' is installed")
            supported_data_sources[DS_CODAC_TYPE] = UdaAccess2
        except ModuleNotFoundError:
            logger.error("module 'uda client' is not installed")

        try:
            import imas
            from iplotDataAccess import imasAccess2
            logger.info("module imas is installed")
            supported_data_sources[DS_IMAS_TYPE] = imasAccess
        except ModuleNotFoundError:
            logger.error("module 'imas' is not installed")

        try:
            from iplotDataAccess.csvAccess2 import CsvAccess2
            logger.info("module imas is installed")
            supported_data_sources[DS_CSV_TYPE] = CsvAccess2
        except ModuleNotFoundError:
            logger.error("module 'imas' is not installed")

        try:
            import sseclient
            logger.info("module sseclient is installed")
        except ModuleNotFoundError:
            logger.error("module 'sseclient' is not installed")

        return supported_data_sources

    def get_default_ds_name(self):
        if self.default_ds is None:
            return None
        else:
            return self.default_ds.name

    def load_config(self, conf_file=None) -> bool:
        conf_files = [conf_file, os.environ.get('IPLOT_SOURCES_CONFIG'), self.DEFAULT_DATA_SOURCES_CFG_FILE]
        # Remove None values
        conf_files = list(filter(None, conf_files))
        for ix, file in enumerate(conf_files):
            try:
                return self.load_config_file(file)
            except (OSError, IOError, FileNotFoundError) as _:
                if ix < len(conf_files) - 1:
                    logger.warning(f"Error loading {file} data source file, fallback to {conf_files[ix + 1]}")
        return False

    def load_config_file(self, dspath):
        with open('C:\\Users\\pmartin.INDRA\\ITER\\MINT_APP\\mydatasources2.cfg') as f:
            config = json.load(f)
            for ds_name, ds_config in config.items():
                if (ds_type := ds_config.get("type")) not in self.proto.keys():
                    logger.warning(f"{ds_name} has not a supported data source ->{ds_type}")
                    continue
                data_source = self.proto[ds_type](ds_name, ds_config)
                if data_source.connect():
                    self.ds_list[ds_name] = data_source

        # Check which data source to set by default
        # Set first DataSource that has default=true if no one has it, set the first one
        self.default_ds = next((ds for ds in self.ds_list.values() if ds.default), list(self.ds_list.values())[0])

        return bool(self.ds_list)

    # def add_data_source(self, data_s=None):
    #     self.ds_list[data_s.name] = data_s

    def get_data_source(self, data_s_name):
        logger.debug("entering getDataSource  %s", data_s_name)
        if data_s_name is None:
            if self.default_ds is not None:
                logger.info(" default source used ")
                return self.default_ds
            else:
                logger.error("DataSourceName is None and not default data source name has been defined")
                return None
        if data_s_name not in self.ds_list.keys():
            logger.warning(" Data source %s not found", data_s_name)
            return None
        else:
            ds = self.ds_list[data_s_name]
            if ds is None:
                logger.debug("Invalid data source pointer for ds name  %s", data_s_name)
            return ds

    def get_data(self, data_s_name, **kwargs):
        # we can use the var prefix to get the data source while we introduce
        logger.debug("entering getdata  %s", data_s_name)
        if data_s_name is not None and data_s_name in self.ds_list.keys():
            if self.ds_list[data_s_name] is None:
                dobj = DataObj()

                dobj.set_empty("Invalid data source pointer for ds name " + data_s_name)
                logger.debug("Invalid data source pointer for ds name  %s", data_s_name)
                return dobj
            else:

                dobj = self.ds_list[data_s_name].get_data(**kwargs)
                return dobj
        else:
            if data_s_name not in self.ds_list.keys():
                logger.warning(" Invalid data source found %s ", data_s_name)
                dobj = DataObj()
                dobj.set_empty(f"Invalid data source name {data_s_name}")

                return dobj
            if self.default_ds is not None:
                logger.info(" default source used ")
                return self.default_ds.get_data(**kwargs)

        return None

    def start_subscription(self, data_s_name, **kwargs):
        if data_s_name is not None and data_s_name in self.ds_list.keys():
            self.ds_list[data_s_name].start_subscription(**kwargs)

    def stop_subscription(self, data_s_name):
        if data_s_name is not None and data_s_name in self.ds_list.keys():
            logger.debug("stopSubscription A ")
            self.ds_list[data_s_name].stop_subscription()

    def get_next_data(self, data_s_name, vname):
        if data_s_name is not None and data_s_name in self.ds_list.keys():
            return self.ds_list[data_s_name].get_next_data(vname)
        else:
            dobj = DataObj()
            dobj.set_empty(f"Invalid data source name {data_s_name}")
            return dobj

    def get_envelope(self, data_s_name, **kwargs):
        if data_s_name is not None and data_s_name in self.ds_list.keys():
            if self.ds_list[data_s_name] is None:
                denv = DataEnvelope()
                denv.set_empty(f"Invalid data source pointer for ds name {data_s_name}")

                return denv
            else:
                return self.ds_list[data_s_name].get_envelope(**kwargs)
        else:
            if data_s_name not in self.ds_list.keys():
                logger.warning(f"Invalid data source found {data_s_name}")
                denv = DataEnvelope()
                denv.set_empty(f"Invalid data source name {data_s_name}")

                return denv
            if self.default_ds is not None:
                logger.info("default source used ")
                return self.default_ds.get_envelope(**kwargs)

        return None

    def get_pulse_list(self, data_source_name, **kwargs) -> List[str]:
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return []
        pulse_list = ds.get_pulses(**kwargs)
        return pulse_list

    def get_pulse_info(self, data_source_name, **kwargs):
        ds = self.get_data_source(data_source_name)
        if ds is None:
            return []
        pulse_info = ds.get_pulse_info(**kwargs)
        return pulse_info

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
        for ds_name, ds in self.ds_list.items():
            if ds_name not in data_sources and ds.connected:
                data_sources.append(ds_name)
        return data_sources

    # TODO change to a better name
    def get_connected_data_sources2(self):
        data_sources = []
        for ds_name, ds in self.ds_list.items():
            if ds.connected:
                data_sources.append(ds)
        return data_sources

    # Clear cache of all the dataSources
    def clear_cache(self):
        for ds in self.ds_list.values():
            if ds.connected:
                ds.daHandler.clear_cache()
