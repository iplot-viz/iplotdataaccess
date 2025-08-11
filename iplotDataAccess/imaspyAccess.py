try:
    import imaspy as imas
except ImportError:
    import imas


import os
import re
from functools import lru_cache

import numpy as np
import pandas as pd
from iplotLogging import setupLogger
from pandas import DataFrame

from iplotDataAccess.dataCommon import DataEnvelope, DataObj
from iplotDataAccess.dataSource import DataSource
from iplotDataAccess.imasDBMaster import IMASDBMaster
from iplotDataAccess.imasUtils import (
    InvalidImasError,
    parse_idspath,
    parse_slice_from_string,
    partial_get,
)

logger = setupLogger.get_logger(__name__)
IMAS_ATTR = ["documentation", "data_type", "units", "dimension"]

if not hasattr(imas, "ids_defs"):
    raise InvalidImasError(
        """
[ERROR] Detected an outdated version of the 'imas' module.

The installed 'imas' package appears to be an incompatible legacy version of the high-level
Python interface of the IMAS Access Layer.

To resolve this, remove / unload this version and re-install using:

    pip install imas-python

or load the appropriate environment module on your system, e.g.

    module load IMAS-Python

More info: https://pypi.org/project/imas-python/
"""
    )


class IMASPYDataAccess(DataSource):
    source_type = "IMASPY"

    def __init__(self, name: str, config: dict):
        super().__init__(name=name, config=config)
        self.uri = ""
        self.pulse_list = None
        self.set_uri(config)
        self.connection = None
        self.connected = False

    def set_uri(self, config: dict | str):
        if type(config) is dict:
            backend = config.get("backend", "hdf5")
            user = config.get("user", "public")
            database = config.get("database", "ITER")
            version = config.get("version", "3")
            pulse_ident = config.get("pulseIdent", "134174/117")
            try:
                ret = pulse_ident.split("/")
                pulse = int(ret[0])
                if len(ret) == 2:
                    run = int(ret[1])
                else:
                    run = 0
                self.uri = (
                    f"imas:{backend.lower()}?user={user};shot={pulse};"
                    f"run={run};database={database};version={version}"
                )
            except Exception as e:
                self.errcode = -1
                self.errdesc = "Received an invalid pulse identifier"
                logger.exception(f"Received an invalid pulse identifier {e}")
        elif type(config) is str:
            self.uri = config
        else:
            logger.error(f"Wrong type of config {type(config)}")

    def connect(self):
        """
        The `connect` function attempts to establish a connection using the provided URI and handles
        potential errors accordingly.

        Returns:
            The `connect` method will return a boolean value. If the connection is successfully
        established, it will return `True`. If there is an error during the connection process, it will
        return `False`.
        """
        if self.uri is None or self.uri == "":
            logger.error(
                "can not connect, uri is not set, set uri using connect_source method"
            )
            self.errcode = -1
            self.errdesc = "uri is not set"
            self.connection = None
            return False
        try:
            self.connection = imas.DBEntry(uri=self.uri, mode="r")
            return True
        except Exception as e:
            self.errcode = -1
            self.errdesc = "IMAS connection error"
            logger.exception(f"IMAS connection error: {e}")
            self.connection = None
            return False

    def is_connected(self):
        return self.connection is not None

    def clear_cache(self):
        # TODO implement
        pass

    def get_cbs_dict(self, pattern=".*"):
        return self.get_dd_fields(pattern)

    def get_var_dict(self, pattern=".*"):
        return self.get_dd_fields(pattern)

    def search_pulses_df(self, text) -> DataFrame:
        return self.get_pulses_df(pulse=text)

    def get_time(self, ids_name):
        try:
            ids = self.connection.get(ids_name, lazy=True, autoconvert=False)
            homogeneous_time = ids.ids_properties.homogeneous_time
            if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_HOMOGENEOUS:
                _time_value = ids.time.value
                if len(_time_value) != 0:
                    return _time_value
            return None
        except Exception as e:
            logger.exception(f"Error getting time for {ids_name}: {e}")
            return None

    def get_values(self, ids_path, time_start: float = None, time_end: float = None):
        """
        The function `get_values` retrieves data based on the provided `ids_path`, handles different
        cases for data retrieval, and returns dictionaries containing x and y data along with error
        information.

        Args:
            ids_path: The `ids_path` parameter
            time_start (float): The `time_start` parameter
            time_end (float): The `time_end` parameter
        Returns:
            The function `get_values` returns two dictionaries `x_dict` and `y_dict`, along with `errcode`
        and `errdesc`. The `x_dict` contains information about the x-axis data, including the object,
        values, unit, and name. The `y_dict` contains information about the y-axis data, including the
        object, values, unit, and name. The `err
        """
        uri_dict = parse_idspath(ids_path)
        occurrence = uri_dict["occurrence"] or 0
        ids_name = uri_dict["ids_name"]
        ids_path = uri_dict["ids_path"]
        if time_start is not None or time_end is not None:
            _time = self.get_time(ids_name)
            if time_start is None and _time is not None:
                time_start = _time[0]
            if time_end is None and _time is not None:
                time_end = _time[-1]
            ids = self.connection.get_sample(
                ids_name, time_start, time_end, lazy=True,  occurrence=occurrence, autoconvert=False
            )
        else:
            ids = self.connection.get(
                ids_name, lazy=True, occurrence=occurrence, autoconvert=False
            )

        x_dict = {}
        y_dict = {}

        node = None
        coordinate = None
        coordinate_index = 0
        ydata = np.array([])
        ylabel = ids_path
        yunit = xunit = xlabel = errdesc = ""
        xdata = np.array([])
        errcode = 0

        if ":" in ids_path:
            if ids.ids_properties.homogeneous_time == 1:
                slice_object = parse_slice_from_string(ids_path)
                ydata, xdata, yunit, xunit = partial_get(ids, ids_path)

                x_dict["object"] = xdata

                x_dict["unit"] = xunit
                if isinstance(xdata, imas.ids_primitive.IDSNumericArray):
                    x_dict["name"] = xdata.metadata.name
                    x_dict["values"] = xdata.value
                else:
                    x_dict["name"] = xlabel
                    x_dict["values"] = xdata

                y_dict["object"] = ydata
                y_dict["values"] = ydata
                y_dict["unit"] = yunit
                y_dict["name"] = ylabel
            else:
                errcode = -1
                errdesc = "Non homogeneous time"
                logger.error(f"Non homogeneous time {ids_path} ")
        else:
            try:
                node = ids[ids_path]
            except Exception as e:
                errcode = -1
                errdesc = f"ids path is not present {ids_path}"
                logger.exception(
                    f"given ids path {ids_path}  is not available, excepion detailed {e}"
                )
            if isinstance(node, imas.ids_primitive.IDSNumericArray):

                if not node.has_value:
                    errcode = -1
                    errdesc = f"Values are not present for {ids_path}"
                    logger.error(f"data for {ids_path}  is not available.")
                else:
                    ydata = node.value
                    yunit = node.metadata.units

                    coordinate = node.coordinates[coordinate_index]

                    if isinstance(coordinate, np.ndarray):
                        xdata = coordinate
                    elif isinstance(coordinate, int):
                        _coordinate = node.coordinates[coordinate]
                        if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive,imas.ids_primitive.IDSNumericArray)):
                            if _coordinate.has_value is True:
                                coordinate = _coordinate
                    elif coordinate and isinstance(coordinate, str):
                        _coordinate = ids[coordinate]
                        if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                            if _coordinate.has_value is True:
                                coordinate = _coordinate
                    else:
                        for _coordinate in node.coordinates:
                            if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                                if _coordinate.has_value is True:
                                    coordinate = _coordinate
                                    break
                                else:
                                    continue

                    if isinstance(coordinate, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                        xdata = coordinate.value
                        xunit = coordinate.metadata.units
                        xlabel = f"{ids_name}/{coordinate.metadata.path}"
            if (
                coordinate is None
                or isinstance(coordinate, int)
                or (
                    isinstance(coordinate, imas.ids_primitive.IDSNumericArray)
                    and coordinate.has_value is False
                )
            ):
                logger.error(
                    "Coordinates are empty, creating default array, you can also provide custom coordinates"
                )
                coordinate = xdata = np.arange(len(ydata))
                xlabel = "Index"
                xunit = "-"

            x_dict["object"] = coordinate
            x_dict["values"] = xdata
            x_dict["unit"] = xunit
            x_dict["name"] = xlabel

            y_dict["object"] = node
            y_dict["values"] = ydata
            y_dict["unit"] = yunit
            y_dict["name"] = ylabel

        def _first(arr):
            if (
                isinstance(arr, (np.ndarray, imas.ids_primitive.IDSNumericArray))
                and arr.size > 0
            ):
                return arr.flat[0]
            return "N/A"

        def _last(arr):
            if (
                isinstance(arr, (np.ndarray, imas.ids_primitive.IDSNumericArray))
                and arr.size > 0
            ):
                return arr.flat[-1]
            return "N/A"

        logger.info(
            f"{'-' * 80}\n"
            f"Accessed data from IMASPY DATA Source for IDS Path: {ids_name}/{ids_path} \n"
            f"X: shape={np.shape(x_dict['values'])}, unit={x_dict['unit']}, label={x_dict['name']}, values=[{_first(x_dict['values'])}, {_last(x_dict['values'])}] \n"
            f"Y: shape={np.shape(y_dict['values'])}, unit={y_dict['unit']}, label={y_dict['name']}, values=[{_first(y_dict['values'])}, {_last(y_dict['values'])}] \n"
            f"errcode={errcode}, errdesc={errdesc}\n"
            f"{'-' * 80}\n"
        )
        return x_dict, y_dict, errcode, errdesc

    def get_data_object(
        self, ids_path, time_start: float = None, time_end: float = None
    ):
        """
        This function retrieves data values and metadata from a specified path and time range, and
        returns a DataObj object containing the extracted information.

        Args:
            ids_path: The `ids_path` parameter
            time_start (float): The `time_start` parameter
            time_end (float): The `time_end` parameter

        Returns:
            An instance of the `DataObj` class with the specified data values and attributes set based on
        the input parameters provided to the `get_data_object` method.
        """
        x_dict, y_dict, errcode, errdesc = self.get_values(
            ids_path, time_start, time_end
        )
        data_obj = DataObj()
        data_obj.ydata = y_dict["values"]
        data_obj.ylabel = y_dict["name"]
        data_obj.yunit = y_dict["unit"]

        data_obj.xdata = x_dict["values"]
        data_obj.xlabel = x_dict["name"]
        data_obj.xunit = x_dict["unit"]
        data_obj.errcode = errcode
        data_obj.errdesc = errdesc

        return data_obj

    def _get_empty_data_object(self):
        data_obj = DataObj()

        data_obj.xdata = np.array([])
        data_obj.ydata = np.array([])
        data_obj.errcode = self.errcode
        data_obj.errdesc = self.errdesc
        return data_obj

    def get_data(self, **kwargs):
        """
        The `get_data` function retrieves data based on input parameters such as ids path, time
        range, URI, and pulse identifier.

        Returns:
            The `get_data` method returns a `DataObj` object with attributes `xdata`, `ydata`, `errcode`,
        and `errdesc` populated based on the input parameters provided in the `kwargs`. If there are any
        errors encountered during the process, an error message is logged, and a `DataObj` object with
        empty arrays and error details is returned.
        """
        ids_path = ""
        time_start = time_end = None

        if kwargs.get("varname"):
            ids_path = kwargs.get("varname")
        if kwargs.get("tsS"):
            try:
                time_start = float(kwargs.get("tsS"))
            except ValueError as e:
                logger.error("Invalid value for tsS: %s", e)
                self.errcode = -1
                self.errdesc = "Invalid value for tsS:"
                return self._get_empty_data_object()
        if kwargs.get("tsE"):
            try:
                time_end = float(kwargs.get("tsE"))
            except ValueError as e:
                logger.error("Invalid value for tsE: %s", e)
                self.errcode = -1
                self.errdesc = "Invalid value for tsE:"
                return self._get_empty_data_object()
        if kwargs.get("uri"):
            self.uri = kwargs.get("uri")
            self.connect()
        if kwargs.get("pulse"):
            pulse_ident = kwargs.get("pulse")
            if pulse_ident.startswith("imas:"):
                self.set_uri(pulse_ident)
            else:
                self.set_uri({"pulseIdent": pulse_ident})
            self.connect()
        if self.connection:
            data_obj = self.get_data_object(ids_path, time_start, time_end)
            return data_obj
        else:
            return self._get_empty_data_object()

    def get_dd_fields(self, pattern=".*"):
        """
        The function `get_dd_fields` recursively extracts fields from an IMAS data dictionary based on a
        specified pattern.

        Args:
            pattern: The `pattern` parameter in the `get_dd_fields` method is used to filter the fields
        based on a regular expression pattern. The method will return only the fields that match the
        specified pattern. If no pattern is provided, the default pattern is set to `.*`, which matches
        any string. Defaults to .*

        Returns:
            The `get_dd_fields` method returns a dictionary containing the fields and attributes of
        elements that match the specified pattern in the IMAS data dictionary. The dictionary includes
        nested structures for child elements as well.
        """

        def get_child(element, path, pattern):
            children = {}
            child_returned = False
            for attr in IMAS_ATTR:
                if attr in element.attrib:
                    children[attr] = element.attrib[attr]
                    if attr == "data_type" and children["data_type"][-1] == "D":
                        children["dimension"] = children["data_type"][-2]

            for child in element.findall("./field"):
                child_name = child.attrib["name"]
                new_child = get_child(child, path + "-" + child_name, pattern)
                if new_child:
                    children[child_name] = new_child
                    child_returned = True

            if re.match(pattern, path) or child_returned:
                return children

        tree = imas.dd_zip.dd_etree()
        root = tree.getroot()

        all_children = {}
        for ids in root.findall("IDS"):
            id_name = ids.attrib["name"]
            child = get_child(ids, id_name, pattern)
            if re.match(pattern, id_name) or child:
                all_children[id_name] = get_child(ids, id_name, pattern)

        return all_children

    def get_pulse_info(self, pulse, run):
        """
        The function `get_pulse_info` retrieves a list of available IDs and times if a connection is
        established.

        Returns:
            The `ids_list` will be returned
        """
        if self.pulse_list is not None:
            filtered = self.pulse_list[
                (self.pulse_list["pulse"] == pulse) & (self.pulse_list["run"] == run)
            ]
            if not filtered.empty:
                return filtered.iloc[0].dropna().to_string()
            else:
                return None

    def close(self):
        """
        The `close` function closes a connection and resets related attributes.
        """
        if self.connection:
            self.connection.close()
        self.uri = None
        self.connection = None
        self.errcode = 0
        self.errdesc = ""

    # TODO Need to think from science perspective
    # TODO as we already have ranges defined for the values
    # TODO how to use this feature better way
    def get_envelope(self, **kwargs):
        dobj = self.get_data(**kwargs)
        denv = DataEnvelope()
        denv.xdata = dobj.xdata
        denv.ydata_min = dobj.ydata - 0.5  # dummy
        denv.ydata_max = dobj.ydata + 0.5  # dummy
        denv.ydata_avg = dobj.ydata  # dummy
        return denv

    @lru_cache(maxsize=10)
    def get_pulses_df(
        self,
        **kwargs,
    ) -> pd.DataFrame:
        pulse = kwargs["pulse"] if "pulse" in kwargs.keys() else ""
        if self.pulse_list is None:
            logger.info(
                "retriving list of pulses for imaspy data source, please wait..."
            )

            directory_list = [os.environ["IMAS_HOME"] + "/shared/imasdb/ITER/3"]
            directory_list.append(os.environ["IMAS_HOME"] + "/shared/imasdb/ITER/4")
            import time

            start_time = time.perf_counter()
            scenarioDescriptionObj = IMASDBMaster(directory_list=directory_list)
            df = scenarioDescriptionObj.get_dataframes_from_files(
                extension=".yaml", add_obsolete=False
            )
            df["date"] = df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")

            df["ref_name"] = df["ref_name"].str.slice(0, 50)
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            logger.info(f"Retrieved list of pulses in: {execution_time:.6f} seconds")
            df_sorted = df.sort_values(by=["pulse", "run"])
            self.pulse_list = df_sorted
        pulses_df = self.pulse_list[
            self.pulse_list["pulse"].astype(str).str.startswith(pulse)
        ][
            [
                "pulse",
                "run",
                "ref_name",
                "ip",
                "b0",
                "fuelling",
                "confinement",
                "workflow",
                "date",
            ]
        ].astype(
            str
        )

        pulses_df["key"] = pulses_df["pulse"] + pulses_df["run"]
        pulses_df.set_index("key", inplace=True)
        return pulses_df
