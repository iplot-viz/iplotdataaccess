# Description: Unit tests for DataType, DataCore, DataObj and DataEnvelope.

import pytest

from iplotDataAccess.dataCommon import (
    DataCore,
    DataEnvelope,
    DataEnvelopeException,
    DataObj,
    DataType,
)


class TestDataTypeEnum:

    def test_all_expected_members_exist(self):
        expected = {
            "DA_TYPE_FLOAT", "DA_TYPE_DOUBLE", "DA_TYPE_STRING",
            "DA_TYPE_LONG", "DA_TYPE_ULONG", "DA_TYPE_CHAR",
            "DA_TYPE_UCHAR", "DA_TYPE_INT", "DA_TYPE_UINT",
            "DA_TYPE_SHORT", "DA_TYPE_USHORT",
        }
        assert {m.name for m in DataType} == expected

    def test_values_are_unique(self):
        values = [m.value for m in DataType]
        assert len(values) == len(set(values))


class TestDataCore:

    def test_default_initial_state(self):
        core = DataCore()
        assert core.xtype is None
        assert core.ytype is None
        assert core.xlabel == ""
        assert core.ylabel == ""
        assert core.xunit == ""
        assert core.yunit == ""
        assert core.drank == ""
        assert core.errcode == 0
        assert core.errdesc is None
        assert core.resolved_pulse is None

    def test_set_a_assigns_known_types_and_clears_error(self):
        core = DataCore()
        core.set_err(-1, "previous")
        core.set_a(DataType.DA_TYPE_DOUBLE, DataType.DA_TYPE_FLOAT,
                   "t", "v", "s", "V", 1)
        assert core.xtype is DataType.DA_TYPE_DOUBLE
        assert core.ytype is DataType.DA_TYPE_FLOAT
        assert core.xlabel == "t"
        assert core.ylabel == "v"
        assert core.xunit == "s"
        assert core.yunit == "V"
        assert core.drank == 1
        assert core.errcode == 0
        assert core.errdesc == ""

    def test_set_a_ignores_non_datatype_values_for_xtype_ytype(self):
        core = DataCore()
        core.set_a("not_a_datatype", 42, "t", "v", "s", "V", 1)
        assert core.xtype is None
        assert core.ytype is None
        assert core.xlabel == "t"

    def test_set_empty_marks_error_with_message(self):
        core = DataCore()
        core.set_empty("boom")
        assert core.errcode == -1
        assert core.errdesc == "boom"

    def test_set_err_and_get_err_round_trip(self):
        core = DataCore()
        core.set_err(7, "explanation")
        assert core.get_err() == (7, "explanation")

    def test_clear_data_resets_metadata(self):
        core = DataCore()
        core.set_a(DataType.DA_TYPE_DOUBLE, DataType.DA_TYPE_DOUBLE,
                   "t", "v", "s", "V", 1)
        core.resolved_pulse = "pulse-1"
        core.clear_data()
        assert core.xlabel == ""
        assert core.yunit == ""
        assert core.errcode == 0
        assert core.resolved_pulse is None


class TestDataObj:

    def test_default_initial_state_has_empty_lists(self):
        d = DataObj()
        assert d.xdata == []
        assert d.ydata == []

    def test_set_data_with_dtype_1_assigns_xdata(self):
        d = DataObj()
        d.set_data([1, 2, 3], 1)
        assert d.xdata == [1, 2, 3]
        assert d.ydata == []

    def test_set_data_with_dtype_other_assigns_ydata(self):
        d = DataObj()
        d.set_data([10, 20, 30], 2)
        assert d.ydata == [10, 20, 30]
        assert d.xdata == []

    def test_set_empty_marks_error_and_resets_data(self):
        d = DataObj()
        d.set_data([1, 2], 1)
        d.set_data([3, 4], 2)
        d.set_empty("no data")
        assert d.errcode == -1
        assert d.errdesc == "no data"
        assert d.xdata == []
        assert d.ydata == []

    def test_clear_data_sets_arrays_to_none(self):
        d = DataObj()
        d.set_data([1, 2], 1)
        d.set_data([3, 4], 2)
        d.clear_data()
        assert d.xdata is None
        assert d.ydata is None
        assert d.errcode == 0


class TestDataEnvelope:

    def test_default_initial_state(self):
        env = DataEnvelope()
        assert env.xdata is None
        assert env.ydata_min is None
        assert env.ydata_max is None
        assert env.ydata_avg is None

    def test_set_x_data_assigns(self):
        env = DataEnvelope()
        env.set_x_data([0, 1, 2])
        assert env.xdata == [0, 1, 2]

    def test_set_y_data_with_matching_lengths(self):
        env = DataEnvelope()
        env.set_y_data([0, 0, 0], [1, 2, 3], [0.5, 1.0, 1.5])
        assert env.ydata_min == [0, 0, 0]
        assert env.ydata_max == [1, 2, 3]
        assert env.ydata_avg == [0.5, 1.0, 1.5]

    def test_set_y_data_raises_on_mismatched_lengths(self):
        env = DataEnvelope()
        with pytest.raises(DataEnvelopeException):
            env.set_y_data([0, 0], [1, 2, 3], [0.5, 1.0, 1.5])

    def test_set_empty_resets_arrays_and_marks_error(self):
        env = DataEnvelope()
        env.set_x_data([1, 2])
        env.set_y_data([0, 0], [1, 1], [0.5, 0.5])
        env.set_empty("nothing")
        assert env.errcode == -1
        assert env.errdesc == "nothing"
        assert env.xdata == []
        assert env.ydata_min == []
        assert env.ydata_max == []
        assert env.ydata_avg == []

    def test_clear_data_sets_arrays_to_none(self):
        env = DataEnvelope()
        env.set_x_data([1])
        env.set_y_data([0], [1], [0.5])
        env.clear_data()
        assert env.xdata is None
        assert env.ydata_min is None
        assert env.ydata_max is None
        assert env.ydata_avg is None
