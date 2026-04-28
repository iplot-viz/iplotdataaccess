# Description: Unit tests for NestedField / NestedDatatype helpers used by UDA introspection.

import pytest

uc = pytest.importorskip("uda_client_reader")  # Module top-level imports it.

from iplotDataAccess.nestedDatatype import (
    NestedDatatype,
    NestedField,
    is_graph_datatype,
    is_primitive_datatype,
)


class TestPrimitiveAndGraphDatatypePredicates:

    @pytest.mark.parametrize("name", ["int", "double", "FLOAT", "uint64", "STR", "char"])
    def test_is_primitive_datatype_recognises_known_names(self, name):
        assert is_primitive_datatype(name) is True

    @pytest.mark.parametrize("name", ["foo", "MyStruct", "SDNHeader", ""])
    def test_is_primitive_datatype_rejects_unknown_names(self, name):
        assert is_primitive_datatype(name) is False

    @pytest.mark.parametrize("name", ["int", "double", "FLOAT", "uint64"])
    def test_is_graph_datatype_recognises_numeric_types(self, name):
        assert is_graph_datatype(name) is True

    @pytest.mark.parametrize("name", ["STR", "char", "string", "bool"])
    def test_is_graph_datatype_rejects_non_numeric_types(self, name):
        assert is_graph_datatype(name) is False


class TestNestedField:

    def test_to_json_returns_expected_keys(self):
        f = NestedField("foo", "double", [1], units="V", description="d")
        out = f.to_json()
        assert out == {
            "type": "double",
            "dimensionality": [1],
            "units": "V",
            "description": "d",
        }


class TestNestedDatatype:

    def test_default_initial_state(self):
        dt = NestedDatatype("test")
        assert dt.name == "test"
        assert dt.fields == []
        assert dt.data_types == {}

    def test_add_field_with_primitive_type_succeeds(self):
        dt = NestedDatatype("test")
        assert dt.add_field("v", "double", [1], "V", "voltage") is True
        assert dt.exists_field("v") is True
        assert len(dt.fields) == 1

    def test_add_field_rejects_unknown_type(self):
        dt = NestedDatatype("test")
        assert dt.add_field("v", "Mystery", [1]) is False
        assert dt.fields == []

    def test_add_field_rejects_duplicate_name(self):
        dt = NestedDatatype("test")
        dt.add_field("v", "double", [1])
        assert dt.add_field("v", "double", [1]) is False
        assert len(dt.fields) == 1

    def test_exists_datatype_for_primitive_and_registered(self):
        dt = NestedDatatype("test")
        assert dt.exists_datatype("int") is True
        assert dt.exists_datatype("Custom") is False
        dt.add_data_type("Custom", NestedDatatype("Custom"))
        assert dt.exists_datatype("Custom") is True

    def test_add_data_type_is_idempotent(self):
        dt = NestedDatatype("test")
        first = NestedDatatype("Custom")
        dt.add_data_type("Custom", first)
        dt.add_data_type("Custom", NestedDatatype("Custom"))
        assert dt.data_types["Custom"] is first

    def test_load_uda_json_with_main_only(self):
        dt = NestedDatatype("test")
        dt.load_uda_json({
            "datatypes": [
                {"name": "main", "fields": [
                    {"name": "v", "type": "double", "multiplicity": 1, "unit": "V", "description": "voltage"}
                ]}
            ]
        })
        assert dt.exists_field("v")

    def test_load_uda_json_registers_nested_datatypes(self):
        dt = NestedDatatype("test")
        dt.load_uda_json({
            "datatypes": [
                {"name": "Header", "fields": [
                    {"name": "ts", "type": "uint64", "multiplicity": 1, "unit": "ns", "description": "time"}
                ]},
                {"name": "main", "fields": [
                    {"name": "hdr", "type": "Header", "multiplicity": 1, "unit": "", "description": ""}
                ]}
            ]
        })
        assert dt.exists_field("hdr")
        assert "Header" in dt.data_types

    def test_flat_datatype_inlines_primitive_fields_with_dim_1(self):
        dt = NestedDatatype("test")
        dt.load_uda_json({
            "datatypes": [
                {"name": "Header", "fields": [
                    {"name": "ts", "type": "uint64", "multiplicity": 1, "unit": "ns", "description": ""},
                    {"name": "id", "type": "int32", "multiplicity": 1, "unit": "", "description": ""},
                ]},
                {"name": "main", "fields": [
                    {"name": "hdr", "type": "Header", "multiplicity": 1, "unit": "", "description": ""}
                ]}
            ]
        })
        flat = dt.flat_datatype("flat")
        names = [f.name for f in flat.fields]
        assert "hdr/ts" in names
        assert "hdr/id" in names

    def test_flat_datatype_expands_multi_dimensional_fields(self):
        dt = NestedDatatype("test")
        dt.load_uda_json({
            "datatypes": [
                {"name": "Sample", "fields": [
                    {"name": "v", "type": "double", "multiplicity": 1, "unit": "", "description": ""}
                ]},
                {"name": "main", "fields": [
                    {"name": "samples", "type": "Sample", "multiplicity": 3, "unit": "", "description": ""}
                ]}
            ]
        })
        flat = dt.flat_datatype("flat")
        names = [f.name for f in flat.fields]
        assert "samples[0]/v" in names
        assert "samples[2]/v" in names

    def test_fields_to_json_strips_sdnheader_prefix(self):
        dt = NestedDatatype("test")
        dt.add_field("SDNHeader/ts", "uint64", [1], "ns", "time")
        out = dt.fields_to_json()
        assert "ts" in out
        assert out["ts"]["type"] == "uint64"
