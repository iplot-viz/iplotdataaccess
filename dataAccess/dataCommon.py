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



class DataObj():

    def __init__(self,parent=None):
        self.xtype=None
        self.ytype=None
        self.xlabel=""
        self.ylabel=""
        self.xunit =""
        self.yunit =""
        self.xdata=None
        self.ydata=None
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

    def setData(self, data, type, myprocList=None, myprocName=None):
        if type == 1 :
            
            self.xdata=data
        else:
            self.ydata=data
            #if myprocList!=None and myprocName!=None:
             #   self.xdata=myprocList[myprocName])

    def setEmpty(self, mess=None):
        self.errcode = -1
        self.errdesc = mess
        self.xdata = []
        self.ydata = []

    def clearData(self):
        self.xtype =""
        self.ytype =""
        self.xlabel =""
        self.ylabel =""
        self.xunit =""
        self.yunit =""
        self.xdata=None
        self.ydata=None
        self.drank=""
        self.errcode=0
        self.errdesc=""

    def setErr(self,errc,errd):
        self.errcode=errc
        self.errdesc=errd
       
    def getErr(self):
        return self.errcode, self.errdesc
    
