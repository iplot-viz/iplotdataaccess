import copy
import json
import collections
import itertools

from iplotLogging import setupLogger
from uda_client_reader.uda_client_reader_python import UdaClientReaderPython

logger = setupLogger.get_logger(__name__)

primitive_types_set = {"bool", "char8", "char", "string", "int8", "int8_t", "uint8", "uint8_t", "int16", "int16_t",
                       "uint16", "uint16_t", "int32", "int32_t", "int", "int_t", "uint32", "uint32_t", "uint", "uint_t",
                       "int64", "int64_t", "uint64", "uint64_t", "float32", "float", "float64", "double", "STR", "INT8",
                       "UINT8", "INT16", "UINT16", "INT24", "UINT24", "INT32", "UINT32", "INT64", "UINT64", "FLOAT",
                       "DOUBLE"}

graph_types_set = {"int8", "int8_t", "uint8", "uint8_t", "int16", "int16_t", "uint16", "uint16_t", "int32", "int32_t",
                   "int", "int_t", "uint32", "uint32_t", "uint", "uint_t", "int64", "int64_t", "uint64", "uint64_t",
                   "float32", "float", "float64", "double", "INT8", "UINT8", "INT16", "UINT16", "INT24", "UINT24",
                   "INT32", "UINT32", "INT64", "UINT64", "FLOAT", "DOUBLE"}


def is_primitive_datatype(data_type_name):
    return data_type_name in primitive_types_set


def is_graph_datatype(data_type_name):
    return data_type_name in graph_types_set


class NestedField:

    def __init__(self, name: str, typename: str, dimensionality: list, units="", description=""):
        self.name = name
        self.typename = typename
        self.dimensionality = dimensionality
        self.description = description
        self.units = units

    def to_json(self):
        out = {
            'type': self.typename,
            'dimensionality': self.dimensionality,
            'units': self.units,
            'description': self.description
        }
        return out


class NestedDatatype:

    def __init__(self, name: str, data_types=None):
        if data_types is None:
            data_types = dict()
        self.flat_data_types = dict()
        self.data_types = data_types
        self.fields = []
        self.name = name

    def exists_field(self, field_name):
        return any(f.name == field_name for f in self.fields)

    def exists_datatype(self, typename):
        return is_primitive_datatype(typename) or typename in self.data_types

    def add_nested_field(self, jfield: NestedField):
        if self.exists_field(jfield.name):
            logger.error(
                f"addField. Error: adding field {self.name} to {jfield.name} datatype. It already exists")
            return False
        if not self.exists_datatype(jfield.typename):
            return False
        self.fields.append(jfield)
        return True

    def add_field(self, name: str, typename: str, dimensionality: list, units="", description=""):
        jfield = NestedField(name, typename, dimensionality, units, description)
        return self.add_nested_field(jfield)

    def add_data_type(self, typename, jtype):
        if self.exists_datatype(typename):
            return
        self.data_types[typename] = jtype

    def load_uda_json(self, json_type: dict):
        for datatype in json_type['datatypes']:
            if datatype['name'] == "main":
                for field in datatype['fields']:
                    mul = [field['multiplicity']]
                    self.add_field(field['name'], field['type'], mul, field['unit'], field['description'])
            else:
                data_type = NestedDatatype(datatype['name'], self.data_types)
                for field in datatype['fields']:
                    mul = [field['multiplicity']]
                    data_type.add_field(field['name'], field['type'], mul, field['unit'], field['description'])
                self.add_data_type(datatype['name'], data_type)

    def flat_datatype(self, name: str):
        data_type = NestedDatatype(name, self.data_types)
        for field in self.fields:
            if is_primitive_datatype(field.typename):
                data_type.add_nested_field(field)
            else:
                if field.typename not in self.flat_data_types:
                    self.flat_data_types[field.typename] = self.data_types[field.typename].flat_datatype(field.typename)
                ftype = self.flat_data_types[field.typename]
                combs = list(itertools.product(*[range(v) for v in field.dimensionality]))
                if field.dimensionality == [1]:
                    for ff in ftype.fields:
                        field_copy = copy.copy(ff)
                        field_copy.name = f'{field.name}/{ff.name}'
                        data_type.add_nested_field(field_copy)
                else:
                    for comb in combs:
                        s = ",".join(map(str, comb))
                        for ff in ftype.fields:
                            field_copy = copy.copy(ff)
                            field_copy.name = f'{field.name}[{s}]/{ff.name}'
                            data_type.add_nested_field(field_copy)
        return data_type

    def fields_to_json(self):
        out = {}
        for f in self.fields:
            f.name = f.name.replace('SDNHeader/', '')
            out[f.name] = f.to_json()
        return out

    def to_json(self):
        out = {"data_types": {}}
        for d in self.data_types:
            out['data_types'][d.name] = d.to_json()

        out['fields'] = self.fields_to_json()

        return out


if __name__ == "__main__":

    # --- DAN --
    # UCR = UdaClientReaderPython("4501as-hpc-0002.codac.iter.org", 3090)
    # -- SDN ---
    UCR = UdaClientReaderPython("localhost", 3090)
    if UCR.getErrorCode() != 0:
        print("Cannot create UdaClientReader. Error: {} {}".format(UCR.getErrorCode(), UCR.getErrorMsg()))
        exit()

    # --- DAN ---
    # metaJSON = UCR.getMetaTypeJSONCollapsed("CTRL-1", "-1")

    metaJSON = UCR.getMetaTypeJSONCollapsed("MAG-PFCS-CCR4:CN_RT_STAT", "-1")

    if UCR.getErrorCode() != 0:
        print("Response error: {}, {}", UCR.getErrorCode(), UCR.getErrorMsg())
        exit()
    js_nested = json.loads(metaJSON, object_pairs_hook=collections.OrderedDict)

    dt = NestedDatatype("test")
    dt.load_uda_json(js_nested)
    fdt = dt.flat_datatype("test2")
    json_fdt = fdt.to_json()
    print(json_fdt)
