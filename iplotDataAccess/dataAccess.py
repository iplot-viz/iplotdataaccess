import json
import os
import importlib.util
import importlib.resources as pkg_resources
from typing import Dict, List, Union, Type

from iplotDataAccess.dataSource import DataSource
from iplotLogging import setupLogger
from iplotDataAccess.dataCommon import DataObj, DataEnvelope

logger = setupLogger.get_logger(__name__)


# class to interface with data source - here UDA
class DataAccess:
    DEFAULT_DATA_SOURCES_CFG_FILE: str = 'mydatasources.cfg'

    def __init__(self):
        self.proto: Dict[str, Type[DataSource]] = self.get_supported_data_source()
        self.ds_list: Dict[str, DataSource] = {}
        self.default_ds: Union[DataSource, None] = None

    @staticmethod
    def get_supported_data_source() -> Dict[str, Type[DataSource]]:
        supported_data_sources = {}

        try:
            file_path = str(pkg_resources.files('iplotDataAccess').joinpath('data_sources.cfg'))
            with open(file_path, 'r') as file:

                data_sources = json.load(file)
                for key, value in data_sources.items():
                    try:
                        module = importlib.import_module(value['pymodule'])
                        imported_class = getattr(module, value['class'])
                        supported_data_sources[imported_class.source_type] = imported_class
                    except Exception as e:
                        logger.error(f"Error loading DataSource {key} -> {e}")

        except Exception as e:
            logger.error(f"Error loading DataSources config file ->{e}")

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

    def load_config_file(self, dspath: str) -> bool:
        with open(dspath) as f:
            try:
                config = json.load(f)
            except Exception as e:
                logger.warning(f"Wrong json format in {dspath} -> {e}")
                return False
            for ds_name, ds_config in config.items():
                ds_type = ds_config.get("type")
                ds_class = self.proto.get(ds_type)
                if not ds_class:
                    logger.warning(f"DataSource '{ds_name}' has an unsupported data source type-> {ds_type}")
                    continue
                try:
                    data_source = ds_class(ds_name, ds_config)
                    if data_source.connect():
                        self.ds_list[ds_name] = data_source
                except Exception as e:
                    logger.warning(f"Error importing class {ds_class} with error {e}")

        if self.ds_list:
            # Check which data source to set by default
            # Set first DataSource that has default=true if no one has it, set the first one
            self.default_ds = next(
                (ds for ds in self.ds_list.values() if ds.default),
                list(self.ds_list.values())[0])
            return True

        return False

    def get_data_source(self, data_s_name):
        logger.debug("entering getDataSource  %s", data_s_name)
        if data_s_name is None:
            if self.default_ds is not None:
                logger.info("default source used ")
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

    def get_connected_data_source_names(self) -> List[str]:
        data_sources = [self.get_default_ds_name()]
        for ds_name, ds in self.ds_list.items():
            if ds_name not in data_sources and ds.is_connected():
                data_sources.append(ds_name)
        return data_sources

    def get_connected_data_sources(self) -> List[DataSource]:
        data_sources = []
        for ds_name, ds in self.ds_list.items():
            if ds.is_connected():
                data_sources.append(ds)
        return data_sources

    # Clear cache of all the dataSources
    def clear_cache(self):
        for ds in self.ds_list.values():
            if ds.is_connected():
                ds.clear_cache()
