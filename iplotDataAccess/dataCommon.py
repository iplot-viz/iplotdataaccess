from enum import Enum


class DataType(Enum):
    DA_TYPE_FLOAT = 1
    DA_TYPE_DOUBLE = 2
    DA_TYPE_STRING = 3
    DA_TYPE_LONG = 4
    DA_TYPE_ULONG = 5
    DA_TYPE_CHAR = 6
    DA_TYPE_UCHAR = 7
    DA_TYPE_INT = 8
    DA_TYPE_UINT = 9
    DA_TYPE_SHORT = 10
    DA_TYPE_USHORT = 11


class DataCore:

    def __init__(self):
        self.xtype = None
        self.ytype = None
        self.xlabel = ""
        self.ylabel = ""
        self.xunit = ""
        self.yunit = ""
        self.drank = ""
        self.errcode = 0
        self.errdesc = None

    def set_a(self, xtype, ytype, xlabel, ylabel, xunit, yunit, drank):
        if isinstance(xtype, DataType):
            self.xtype = xtype
        if isinstance(ytype, DataType):
            self.ytype = ytype
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.xunit = xunit
        self.yunit = yunit
        self.drank = drank
        self.errcode = 0
        self.errdesc = ""

    def set_empty(self, mess=None):
        self.errcode = -1
        self.errdesc = mess

    def clear_data(self):
        self.xtype = ""
        self.ytype = ""
        self.xlabel = ""
        self.ylabel = ""
        self.xunit = ""
        self.yunit = ""

        self.drank = ""
        self.errcode = 0
        self.errdesc = ""

    def set_err(self, errc, errd):
        self.errcode = errc
        self.errdesc = errd

    def get_err(self):
        return self.errcode, self.errdesc


class DataObj(DataCore):

    def __init__(self):
        super().__init__()

        self.xdata = []
        self.ydata = []

    def set_data(self, data, dtype):
        if dtype == 1:
            self.xdata = data
        else:
            self.ydata = data

    def set_empty(self, mess=None):
        super().set_empty(mess)
        self.xdata = []
        self.ydata = []

    def clear_data(self):
        super().clear_data()
        self.xdata = None
        self.ydata = None


class DataEnvelopeException(Exception):
    pass


class DataEnvelope(DataCore):

    def __init__(self):
        super().__init__()
        self.xdata = None
        self.ydata_min = None
        self.ydata_max = None
        self.ydata_avg = None

    def set_x_data(self, xdata):
        self.xdata = xdata

    def set_y_data(self, datamin, datamax, datavg):

        if len(datavg) == len(datamax) == len(datamin):
            self.ydata_min = datamin
            self.ydata_max = datamax
            self.ydata_avg = datavg
        else:
            raise DataEnvelopeException("Invalid Enveloppe min, max and avg should have the same shape")

    def set_empty(self, mess=None):
        super().set_empty(mess)
        self.xdata = []
        self.ydata_min = []
        self.ydata_max = []
        self.ydata_avg = []

    def clear_data(self):
        super().clear_data()
        self.xdata = None
        self.ydata_min = None
        self.ydata_max = None
        self.ydata_avg = None
