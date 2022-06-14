import sys
from enum import Enum

class DataType(Enum):
    DA_TYPE_FLOAT=1
    DA_TYPE_DOUBLE=2
    DA_TYPE_STRING=3
    DA_TYPE_LONG=4
    DA_TYPE_ULONG=5
    DA_TYPE_CHAR=6
    DA_TYPE_UCHAR=7
    DA_TYPE_INT=8
    DA_TYPE_UINT=9
    DA_TYPE_SHORT=10
    DA_TYPE_USHORT=11



class DataCore():

    def __init__(self,parent=None):
        self.xtype=None
        self.ytype=None
        self.xlabel=""
        self.ylabel=""
        self.xunit =""
        self.yunit =""
        self.drank=""
        self.errcode=0
        self.errdesc=None
        

    def setA(self,xtype,ytype,xlabel,ylabel,xunit,yunit,drank):
        if isinstance(xtype,DataType):
            self.xtype=xtype
        if isinstance(ytype,DataType):
            self.ytype=ytype
        self.xlabel=xlabel
        self.ylabel=ylabel
        self.xunit=xunit
        self.yunit=yunit
        self.drank=drank
        self.errcode=0
        self.errdesc=""

    
    
    def setEmpty(self, mess=None):
        self.errcode = -1
        self.errdesc = mess
       

    def clearData(self):
        self.xtype =""
        self.ytype =""
        self.xlabel =""
        self.ylabel =""
        self.xunit =""
        self.yunit =""
        
        self.drank=""
        self.errcode=0
        self.errdesc=""
        

    def setErr(self,errc,errd):
        self.errcode=errc
        self.errdesc=errd
       
    def getErr(self):
        return self.errcode, self.errdesc

class DataObj(DataCore):

    def __init__(self,parent=None):
        super().__init__(parent)
        self.xdata=None
        self.ydata=None
        
        

    
    
    def setData(self, data, type):
        if type == 1 :
            self.xdata=data
        else:
            self.ydata=data

    def setEmpty(self, mess=None):
        super().setEmpty(mess)
        self.xdata = []
        self.ydata = []

    def clearData(self):
        super().clearData()
        self.xdata=None
        self.ydata=None

class DataEnvelopeException(Exception):
    pass        
        
class DataEnvelope(DataCore):

    def __init__(self,parent=None):
        super().__init__(parent)
        self.xdata=None
        self.ydata_min=None
        self.ydata_max=None
        self.ydata_avg=None
        
    def setXData(self,xdata):
        self.xdata=xdata
        
    def setYData(self,datamin,datamax,datavg):
        
        if(len(datavg)==len(datamax) and len(datamax)==len(datamin)):
            self.ydata_min=datamin
            self.ydata_max=datamax
            self.ydata_avg=datavg
        else:
            raise DataEnveloppeException("Invalid Enveloppe min, max and avg should have the same shape")

    def setEmpty(self, mess=None):
        super().setEmpty(mess)
        self.xdata = []
        self.ydata_min = []
        self.ydata_max = []
        self.ydata_avg = []

    def clearData(self):
        super().clearData()
        self.xdata=None
        self.ydata_min=None
        self.ydata_max=None
        self.ydata_avg=None
        
   
    
    
