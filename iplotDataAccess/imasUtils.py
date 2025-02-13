import re

import imaspy as imas
import numpy as np
from iplotLogging import setupLogger
from imaspy.ids_primitive import (
    IDSPrimitive,
)

logger = setupLogger.get_logger(__name__)


def parse_idspath(idspath: str):
    """
    The function `parse_idspath` extracts the name and path components from a given IDS path string.

    Args:
        idspath (str): idspath like summary/fusion/power/value

    Returns:
        The `parse_idspath` function returns a tuple containing the `ids_name` and `ids_path` values
    parsed from the input `idspath` string. e.g. ids_name : summary and ids_path : fusion/power/value
    """
    ids_name = ""
    ids_path = None
    splitted_idspath = idspath.split("/", 1)
    if ":" in splitted_idspath[0]:
        splitted_idspath = idspath.split(":")
        ids_name = splitted_idspath[0]
        if len(splitted_idspath) == 2:
            ids_path_fragment = splitted_idspath[1]
            splitted_ids_path_fragment = ids_path_fragment.split("/", 1)
            if len(splitted_ids_path_fragment) == 2:
                ids_path = splitted_ids_path_fragment[1]
    else:
        ids_name = splitted_idspath[0]
        if len(splitted_idspath) == 2:
            ids_path = splitted_idspath[1]
    return ids_name, ids_path


def parse_slice_from_string(input_string):
    match = re.search(r"[\[\(]([-\d]*):([-\d]*):?([-\d]*)[\]\)]", input_string)

    start = end = step = None
    if match:
        start_str, end_str, step_str = match.groups()

        start = int(start_str) if start_str else None
        end = int(end_str) if end_str else None
        step = int(step_str) if step_str else None

    return slice(start, end, step)


def get_length_of_partial_field(ids, ids_path):
    partial_field = re.sub(r"[\[\(](t|[\d]*)[\]\)]", "", ids_path)
    partial_field = partial_field.split(".")[0]
    try:
        _inner_data = eval("ids." + partial_field)
        coordinate_partial = _inner_data
        coordinate_unit = ""
        if isinstance(_inner_data, IDSPrimitive):
            coordinate_partial = _inner_data.coordinates[0]
            coordinate_unit = _inner_data.coordinates[0].metadata.units
        return coordinate_partial, coordinate_unit
    except Exception as e:
        logger.error(
            f"{partial_field} path/value does not exist, hint: please check "
            f"length of an array, detailed error : {e}"
        )
        return None


def partial_get(ids, ids_path, coordinate_index=0):
    """
    The function `partial_get` retrieves partial data based on specified IDs and path from a given
    array.

    Args:
        ids: ids object
        ids_path: ids field path

    Returns:
        The function `partial_get` returns two arrays: `time_array` and `data`.
    """
    slice_object = parse_slice_from_string(ids_path)
    ids_path_for_eval = re.sub(
        r"[\[\(][^:\[\]\(\)]*:[^:\[\]\(\)]*[\]\)]", "(t)", ids_path
    )
    ids_path_for_eval = (
        ids_path_for_eval.replace("(", "[").replace(")", "]").replace("/", ".")
    )
    coordinate_partial, coordinate_unit = get_length_of_partial_field(
        ids, ids_path_for_eval
    )
    data = np.array([]).reshape(
        0,
    )
    start = slice_object.start if slice_object.start is not None else 0
    stop = (
        slice_object.stop if slice_object.start is not None else len(coordinate_partial)
    )
    step = slice_object.step if slice_object.step is not None else 1
    data_flag = True
    data_unit = ""
    coordinate = coordinate_partial
    for t in range(start, stop, step):
        try:
            _inner_data = eval("ids." + ids_path_for_eval)
            if data_flag:
                data_flag = False
                if isinstance(_inner_data, IDSPrimitive):
                    data_unit = _inner_data.metadata.units
                    if coordinate_index >= len(_inner_data.coordinates):
                        coordinate_index = 0
                    coordinate = _inner_data.coordinates[coordinate_index]
                    if isinstance(coordinate, IDSPrimitive):
                        coordinate_unit = coordinate.metadata.units
        except Exception as e:
            logger.error(
                f"{ids_path} path/value does not exist, hint: please check length"
                f"of arrays, detailed error : {e}"
            )
            return data, coordinate, data_unit, coordinate_unit
        if len(_inner_data.shape) == 0:
            data = np.append(data, _inner_data)
        elif len(_inner_data.shape) == 1:
            if data.size == 0:
                data = _inner_data
            else:
                data = np.vstack((data, _inner_data))
    data = np.array(data)
    return data, coordinate, data_unit, coordinate_unit


def get_slice(xdata, ydata, time_start: float = None, time_end: float = None):
    """
    The function `get_slice` takes input data along with optional time boundaries and returns a sliced
    portion of the data within the specified time range.

    Args:
        xdata: `xdaya` numpy array
        ydata: `ydata` numpy array
        time_start (float): The `time_start` parameter in the `get_slice` function is used to specify the
    starting time for slicing the data.
        time_end (float): The `time_end` parameter in the `get_slice` function is used to specify the end
    time for slicing the data.

    Returns:
        The function `get_slice` returns the sliced `xdata` and `ydata` based on the specified time range
    (`time_start` and `time_end`).
    """
    if xdata is not None and len(xdata) != 0:
        if time_start is None:
            time_start = xdata[0]
        if time_end is None:
            time_end = xdata[-1]
    else:
        return xdata, ydata
    idx = np.where((xdata >= time_start) & (xdata <= time_end))
    xdata_sliced = xdata[idx]
    if ydata.ndim == 1:
        ydata_sliced = ydata[idx]
    elif ydata.ndim == 2:
        ydata_sliced = ydata[:][idx]
    elif ydata.ndim == 3:
        ydata_sliced = ydata[:][:][idx]
    return xdata_sliced, ydata_sliced


def parse_string_to_dict(input_string):
    """
    The function `parse_string_to_dict` takes a string of key-value pairs separated by commas and
    returns a dictionary with the keys and values.

    Args:
        input_string: Please provide me with the input_string so that I can help you parse it into a
    dictionary.

    Returns:
        The function `parse_string_to_dict` returns a dictionary where the keys and values are extracted
    from the input string.
    """
    pairs = input_string.split(",")

    result_dict = {}
    for pair in pairs:
        key, value = pair.split("=", 1)
        result_dict[key] = value

    return result_dict


def get_ids_types():
    """
    This function returns list of strings corresponding to all ids types for each IDSName object in the imas module.

    Returns:
        The function `get_ids_types()` is returning a list of values of all the `value` attributes of the `IDSName`
        objects in the `imas` module.
    """
    factory = imas.IDSFactory()
    return factory.ids_names()


def get_available_ids_and_times(db_entry_object) -> list:
    """
    The function `get_available_ids_and_times` retrieves available IDS names and corresponding time
    arrays from a given `db_entry_object`.

    Args:
        db_entry_object: The `db_entry_object` parameter.

    Returns:
        a list of tuples. Each tuple contains an IDS name and a corresponding time array.
    """

    result = []

    for _ids_name in get_ids_types():
        occurrence_list = db_entry_object.list_all_occurrences(_ids_name)

        if len(occurrence_list) == 0:
            continue

        for occurrence in occurrence_list:
            time_array = None
            try:
                ids_object = db_entry_object.get(
                    _ids_name, occurrence=occurrence, lazy=True, autoconvert=False
                )
                homogeneous_time = ids_object.ids_properties.homogeneous_time
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_UNKNOWN:
                    time_array = []
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_HETEROGENEOUS:
                    time_array = [np.NaN]
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_HOMOGENEOUS:
                    time_array = ids_object.time.value
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_INDEPENDENT:
                    time_array = [np.NINF]
            except Exception as e:
                time_array = []
                logger.exception(
                    f"ERROR! IDS {_ids_name} (occurrence: {occurrence}) : Reading time array fails due to the following problem: {e}"
                )
            if time_array is not None and len(time_array):
                result.append((_ids_name, len(time_array)))
    return result
