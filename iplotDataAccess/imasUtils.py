import re

try:
    import imaspy as imas
except ImportError:
    import imas
import numpy as np
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)


class InvalidImasError(Exception):
    pass


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


def parse_idspath(ids_fragment: str):
    result = {}

    ids_name = ""
    ids_path = None
    occurrence = None

    splitted_ids_fragment = ids_fragment.split("/", 1)
    if ":" in splitted_ids_fragment[0]:
        splitted_ids_fragment = ids_fragment.split(":", 1)
        ids_name = splitted_ids_fragment[0]
        if len(splitted_ids_fragment) == 2:
            ids_path_fragment = splitted_ids_fragment[1]
            splitted_ids_path_fragment = ids_path_fragment.split("/", 1)
            if splitted_ids_path_fragment[0].isdigit():
                occurrence = int(splitted_ids_path_fragment[0])
            if len(splitted_ids_path_fragment) == 2:
                ids_path = splitted_ids_path_fragment[1]
    else:
        ids_name = splitted_ids_fragment[0]
        if len(splitted_ids_fragment) == 2:
            ids_path = splitted_ids_fragment[1]
    result["occurrence"] = occurrence
    result["ids_name"] = ids_name
    result["ids_path"] = ids_path
    return result


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
    partial_field = ids_path
    match = re.match(r"^(.*)\[t\]\.(.*)", ids_path)
    if match:
        partial_field = match.group(1)
    try:
        _inner_data = eval("ids." + partial_field)
        coordinate_partial = None
        coordinate_unit = ""
        if isinstance(_inner_data, imas.ids_primitive.IDSPrimitive) or isinstance(
            _inner_data, imas.ids_struct_array.IDSStructArray
        ):
            coordinate_partial = _inner_data.coordinates[0]
            if isinstance(coordinate_partial, imas.ids_primitive.IDSPrimitive):
                coordinate_unit = coordinate_partial.metadata.units
        return coordinate_partial, coordinate_unit
    except Exception as e:
        logger.error(
            f"{partial_field} path/value does not exist, hint: please check "
            f"length of an array, detailed error : {e}"
        )
        return None


def partial_get(ids, ids_path, custom_coordinate=None):
    slice_object = parse_slice_from_string(ids_path)
    ids_path_for_eval = re.sub(r"[\[\(][^()\[\]]*:[^()\[\]]*[\]\)]", "(t)", ids_path)
    ids_path_for_eval = (
        ids_path_for_eval.replace("(", "[").replace(")", "]").replace("/", ".")
    )
    coordinate_partial, coordinate_unit = get_length_of_partial_field(
        ids, ids_path_for_eval
    )
    data = np.array([]).reshape(
        0,
    )
    array_data = []
    start = slice_object.start if slice_object.start is not None else 0
    stop = (
        slice_object.stop if slice_object.stop is not None else len(coordinate_partial)
    )
    step = slice_object.step if slice_object.step is not None else 1
    data_flag = True
    data_unit = ""
    coordinate = None
    for t in range(start, stop, step):
        try:
            _inner_data = eval("ids." + ids_path_for_eval)
            if data_flag:
                data_flag = False
                if isinstance(_inner_data, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                    data_unit = _inner_data.metadata.units
                    if custom_coordinate and custom_coordinate.sdigit():
                        _coordinate = _inner_data.coordinates[custom_coordinate]
                        if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive), imas.ids_primitive.IDSNumericArray):
                            if _coordinate.has_value is True and coordinate is None:
                                coordinate = _coordinate
                    elif custom_coordinate and isinstance(custom_coordinate, str):
                        _coordinate = eval("ids." + custom_coordinate)
                        if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                            if _coordinate.has_value is True and coordinate is None:
                                coordinate = _coordinate
                    else:
                        for _coordinate in _inner_data.coordinates:
                            
                            if isinstance(_coordinate, (imas.ids_primitive.IDSPrimitive, imas.ids_primitive.IDSNumericArray)):
                                if _coordinate.has_value is True and coordinate is None:
                                    coordinate_unit = _coordinate.metadata.units
                                    coordinate = _coordinate
                                    break
                                else:
                                    continue
                            else:
                                if coordinate is None:
                                    coordinate = _coordinate
                                    coordinate_unit = "Indices"
        except Exception as e:
            logger.error(
                f"{ids_path} path/value does not exist, hint: please check length of arrays, detailed error : {e}"
            )
            return data, coordinate, data_unit, coordinate_unit
        if isinstance(
            _inner_data,
            (
                imas.ids_structure.IDSStructure,
                imas.ids_struct_array.IDSStructArray,
                imas.ids_primitive.IDSNumericArray,
            ),
        ):
            array_data.append(_inner_data)
        elif isinstance(_inner_data, imas.ids_primitive.IDSString0D):
            array_data.append(_inner_data.value)
        else:
            if len(_inner_data.shape) == 0:
                data = np.append(data, _inner_data)
            elif len(_inner_data.shape) == 1:
                if data.size == 0:
                    data = _inner_data
                else:
                    data = np.vstack((data, _inner_data))
    if len(array_data) == 0:
        data = np.stack(data, axis = 0)
    else:
        data = np.stack(array_data, axis = 0)

    # Transpose data if its first dimension does not match the coordinate's length
    if coordinate is not None and hasattr(coordinate, "shape") and hasattr(data, "shape"):
        if len(data.shape) == 2 and len(coordinate.shape) == 1:
            if data.shape[0] != coordinate.shape[0] and data.shape[1] == coordinate.shape[0]:
                data = data.T
    return data, coordinate, data_unit, coordinate_unit


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
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_HETEROGENEOUS:
                    time_array = [np.NaN]
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_HOMOGENEOUS:
                    time_array = ids_object.time.value
                if homogeneous_time == imas.ids_defs.IDS_TIME_MODE_INDEPENDENT:
                    time_array = [np.NINF]
            except Exception as e:
                time_array = []
                logger.exception(
                    f"ERROR! IDS {_ids_name} (occurrence: {occurrence}) : "
                    f"Reading time array fails due to the following problem: {e}"
                )
            if time_array is not None and len(time_array):
                result.append((_ids_name, len(time_array)))
    return result
