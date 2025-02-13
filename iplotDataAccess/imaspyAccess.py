import re

import imaspy as imas
import numpy as np
from imaspy.ids_primitive import IDSNumericArray, IDSPrimitive
from iplotLogging import setupLogger
from scipy.interpolate import interp1d

from iplotDataAccess.dataCommon import DataEnvelope, DataObj
from iplotDataAccess.imasDBMaster import IMASDBMaster
from iplotDataAccess.imasUtils import (
    get_available_ids_and_times,
    get_slice,
    parse_idspath,
    parse_string_to_dict,
    partial_get,
)

logger = setupLogger.get_logger(__name__)
IMAS_ATTR = ["documentation", "data_type", "units", "dimension"]


class IMASPYDataAccess:
    def __init__(self):
        self.uri = None
        self.connection = None
        self.errcode = 0
        self.errdesc = ""

    def connect_source(self, connection_string=""):
        """
        The `connect_source` function in Python connects to a data entry using a connection string(uri).

        Args:
            connection_string: The `connect_source` method is used to establish a connection to a data
        source based on the provided `connection_string`. The `connection_string` parameter should
        contain uri.

        Returns:
            The `connect_source` method is returning a boolean value `True`.
        """
        self.uri = ""
        if connection_string.startswith("imas:"):
            self.uri = connection_string
        else:
            attributes = parse_string_to_dict(connection_string)
            backend = (
                attributes["backend"] if "backend" in attributes.keys() else "mdsplus"
            )
            user = attributes["user"] if "user" in attributes.keys() else "public"
            database = (
                attributes["database"] if "database" in attributes.keys() else "ITER"
            )
            version = attributes["version"] if "version" in attributes.keys() else "3"
            pulse_ident = (
                attributes["pulseIdent"] if "pulseIdent" in attributes.keys() else "0/0"
            )
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
        # TODO This is required by calling function. after connect function it should report
        return True

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
                f"can not connect, uri is not set, set uri using connect_source method {e}"
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

    @property
    def is_connected(self):
        if self.connection:
            return True
        else:
            return False

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
        ids_name, ids_fragment = parse_idspath(ids_path)
        ids = self.connection.get(ids_name, lazy=True, autoconvert=False)

        x_dict = {}
        y_dict = {}
        ids_fragment = (
            ids_fragment.replace("(", "[").replace(")", "]").replace("/", ".")
        )
        node = None
        coordinate = None
        coordinate_index = 0
        ydata = np.array([])
        ylabel = ids_path
        yunit = xunit = xlabel = errdesc = ""
        xdata = np.array([])
        errcode = 0

        if ":" in ids_fragment:
            if ids.ids_properties.homogeneous_time == 1:
                ydata, xdata, yunit, xunit = partial_get(ids, ids_fragment)
                ydata = np.transpose(ydata)
            else:
                errcode = -1
                errdesc = "Non homogeneous time"
                logger.error(f"Non homogeneous time {ids_path} ")
        else:
            try:
                node = eval("ids." + ids_fragment)
            except Exception as e:
                errcode = -1
                errdesc = f"ids path is not present {ids_path}"
                logger.exception(
                    f"given ids path {ids_path}  is not available, excepion detailed {e}"
                )
            if isinstance(node, IDSNumericArray):
                if not node.has_value:
                    errcode = -1
                    errdesc = "Values are not present for {ids_path}"
                    logger.error(f"data for {ids_path}  is not available.")
                else:
                    ydata = node.value
                    yunit = node.metadata.units

                    coordinate = node.coordinates[coordinate_index]
                    if isinstance(coordinate, IDSPrimitive):
                        xdata = coordinate.value
                        xunit = coordinate.metadata.units
                        xlabel = f"{ids_name}/{coordinate.metadata.path}"
        xdata, ydata = get_slice(xdata, ydata, time_start, time_end)
        x_dict["object"] = coordinate
        x_dict["values"] = xdata
        x_dict["unit"] = xunit
        x_dict["name"] = xlabel

        y_dict["object"] = node
        y_dict["values"] = ydata
        y_dict["unit"] = yunit
        y_dict["name"] = ylabel

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
                self.connect_source(connection_string=pulse_ident)
            else:
                self.connect_source(connection_string="pulseIdent=" + pulse_ident)
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

    def get_cbs_list(self, pattern=".*"):
        return self.get_dd_fields(pattern)

    def get_var_list(self, pattern=".*"):
        return self.get_dd_fields(pattern)

    def get_pulse_info(self, pulse, run, version="3"):
        """
        The function `get_pulse_info` retrieves a list of available IDs and times if a connection is
        established.

        Returns:
            The `ids_list` will be returned
        """
        uri = (
            f"imas:hdf5?user=public;shot={pulse};" f"run={run};database=ITER;version=3"
        )
        entry = imas.DBEntry(uri, "r")
        ids_list = None
        if entry:
            ids_list = get_available_ids_and_times(entry)

        return ids_list

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

    # TODO implement pulse and run filter
    def get_pulses(
        self,
        **kwargs,
    ):
        pulse = kwargs["pulse"] if "pulse" in kwargs.keys() else ""
        run = kwargs["run"] if "run" in kwargs.keys() else ""
        user = kwargs["user"] if "user" in kwargs.keys() else "public"
        database = kwargs["database"] if "database" in kwargs.keys() else "ITER"
        version = kwargs["version"] if "version" in kwargs.keys() else "3"
        backends = kwargs["backends"] if "backends" in kwargs.keys() else "mdsplus"
        pulses = IMASDBMaster.get_database_files(
            pulse=pulse,
            run=run,
            user=user,
            database=database,
            version=version,
            backends=backends,
        )
        return pulses
