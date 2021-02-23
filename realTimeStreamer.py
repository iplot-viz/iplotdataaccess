

import requests
import sseclient
import getpass
import numpy as np
from enum import Enum
from collections import deque
import access.dataCommon as dc
import time
import log.setupLogger as ls


logger = ls.get_logger(__name__)

class RTStreamerException(Exception):
    pass

class ProtoHeader(Enum):
	VARNAME=0
	TIME_DT=1
	VAL_DT=2
	NB_SMP=3


class VarType(Enum):
	pon="P"
	dan="D"
	sdn="S"


class RTStreamer:
	def __init__(self, url=None, headers=None, auth=None,udaA=None):
		self.urlX = url or 'http://io-ls-udaweb1.iter.org/dashboard/backend/sse'
		self.params = None
		self.origparams =[]
		self.origparams1 = []
		self.username = None
		self.password = None
		self.auth = auth
		self.response = None
		self.client = None
		self.__status = "INIT"
		self.__units = {}
		#self.headers = {'User-Agent': 'it_script_basic'}
		self.headers = headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
		###headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
		self.vardata={}

		self.maxsizeP=100
		self.maxsize=1000
		self.udaAccess=udaA
		self.__checkAndFillHeaders()

		##logging.basicConfig(filename="/tmp/output_pro.log", format='%(asctime)s -%(levelname)s-%(funcName)s-%(message)s', datefmt='%Y-%m-%dT%H:%M:%S', level=logging.DEBUG)
		##self.logger = logging.getLogger(__name__)

	def __checkAndFillHeaders(self):
		logger.debug("headers is %s and type is %s ",self.headers,type(self.headers))
		for k, v in self.headers.items():
			if v == "$USERNAME":
				self.headers[k] = getpass.getuser()

	def __setParams(self, params=[]):
		self.origparams1 = params
		if params is not None and len(params)>0:
			p1=set(params)
			self.params = "variables="+",".join(p1)
			if self.udaAccess is None:
				logger.warning(" no uda data access defined cannot get the units")
				return
			for s in p1:
				self.__units[s]=self.udaAccess.getUnit(s)



	def __convertType(self, utype):

		if utype == "D" or utype == "PD":
			return dc.DataType.DA_TYPE_DOUBLE

		elif utype == "L":
			return dc.DataType.DA_TYPE_LONG
		elif utype == "S" or utype == "PS":
			return dc.DataType.DA_TYPE_STRING

	def __checkIfduplicate(self,varname,params=[]):
		vKeysIdx=[]
		idx=0
		idx1=0

		if varname in params:
			#logger.debug("entering check duplicate vname=%s params=%s", varname, params)
			while idx < len(params):
				try :
					idx = params.index(varname,idx1)
					vKeysIdx.append(idx)
					idx1 = idx+1
				except ValueError as ve:
					idx = len(params) +10

		logger.debug("check duplicate %s %s %s",varname,params,vKeysIdx)
		return vKeysIdx

	def __createQueues(self,vkeys,vtype,data,params=[]):
		logger.debug("create XXX queue for vkeys=%s", vkeys)
		for i in range(len(vkeys)):
			sname=params[vkeys[i]]+'@'+str(vkeys[i])
			if self.vardata.get(sname) is not None:
				logger.debug("adding data to queue for vname=%s", sname)
				self.vardata[sname].append(data)
			else:
				logger.debug("create queue for vname=%s", sname)
				if vtype.startswith(VarType.pon.value):

					self.vardata[sname] = deque([data], self.maxsizeP)
				else:
					self.vardata[sname] = deque([data], self.maxsize)

	def __appendData(self,vkeys,d,params=[]):
		for i in range(len(vkeys)):
			sname=params[i]+'@'+str(i)
			self.vardata[sname].append(d)


	def __parseData(self, data,counter,params=[]):
		q = None
		if data.startswith("heartbeat"):
			return
		line = data.split(" ")

		xtype = dc.DataType.DA_TYPE_ULONG
		xlabel = "Time"
		ylabel = ""
		xunit = "ns"
		yunit = ""
		drank = 1

		ytype = self.__convertType(line[ProtoHeader.VAL_DT.value])
		if ytype == dc.DataType.DA_TYPE_STRING:
			logger.warning("string not currently supported for streaming, skipping")
			return

		val = data.split(" V ")
		xdata = np.zeros(int(line[ProtoHeader.NB_SMP.value]))
		ydata = np.zeros(int(line[ProtoHeader.NB_SMP.value]))
		d = dc.DataObj()
		yunit=self.__units.get(line[ProtoHeader.VARNAME.value])
		d.setA(xtype, ytype, xlabel, ylabel, xunit, yunit, drank)
		for i in range(int(line[ProtoHeader.NB_SMP.value])):
			xdata[i] = int(line[ProtoHeader.NB_SMP.value+i+1])*1000000
			ydata[i] = float(val[i+1].split(" ")[0])

		d.setData(xdata, 1)
		d.setData(ydata, 2)
		##logger.debug("before calling check duplocate")
		vkeys = self.__checkIfduplicate(line[ProtoHeader.VARNAME.value], params=params)
		self.__createQueues(vkeys,line[ProtoHeader.VAL_DT.value],d,params=params)

	def getStatus(self):
		return self.__status

	def startSubscription(self, params=[],origparams=[]):
		if self.__status == "STARTED":
			logger.error("Subscription is already started, needs to be stopped first or launch a new RTStreamer")
			raise RTStreamerException(" Streamer already started")
		self.__setParams(params)
		url1 = self.urlX + '?' + self.params
		logger.debug("starting sub header=%s and uri=%s",self.headers,url1)

		#response = requests.get(url=url1, stream=True, headers=self.headers, auth=self.auth, timeout=None)
		try:
			self.response = requests.get(url=url1, stream=True, headers=self.headers, timeout=None)
		except ConnectionError as ce:
			logger.error("got connection error %s with errcode = %d ", ce, self.response.status_code)
			self.__status = "ERROR"
			raise RTStreamerException(" could not connect - see log for more details")
			#print(response.headers)
		self.origparams=origparams
		paramsT = params
		logger.debug(" origparm %s  param=%s ", self.origparams,self.params)
		self.client = sseclient.SSEClient(self.response)
		i = 0
		self.__status = "STARTED"
		for event in self.client.events():
			logger.debug("found new data %s",event.data)
			if self.__status == "STOPPING":
				break
			self.__parseData(event.data, i,params=paramsT)
			if i < 1000:
				i = i + 1
		self.client.close()
		self.response.close()
		if self.vardata is not None:
			for k in self.vardata.keys():
				self.vardata[k].clear()
		self.__status = "STOPPED"

	def __getNextDataI(self,vname):
		idx=-1
		dobj = None
		try:
			#logger.debug(" vname=%s origparm %s  self=%s ", vname,self.origparams,self.origparams1)

			idx=self.origparams.index(vname)
			sname=self.origparams1[idx]+"@"+str(idx)
			if sname in self.vardata.keys():
				dobj = self.vardata[sname].popleft()
			else:
				dobj = dc.DataObj()
				dobj.setEmpty("varname not in the keys")

		except ValueError:
			dobj = dc.DataObj()
			dobj.setEmpty("Value error : varname not in the keys")
			logger.warning("invalid get next data call variable %s not in the list",vname)
		return dobj

	###expect orig name with expression -> handle the case where we subscribe to the same variable but different expressions are applied to them
	def getNextData(self, vname=None):
		#logger.debug("got a call vanme=%s",vname)
		if vname is None:
			dobj = dc.DataObj()
			dobj.setEmpty("Varname is empty")
			return dobj

		try:
			dobj = self.__getNextDataI(vname)
			logger.debug("vname=%s timestamp %d and val=%f", vname,dobj.xdata[0], dobj.ydata[0])
		except IndexError:
			dobj = dc.DataObj()
			dobj.setEmpty("No data found")
		#logger.debug("object err = %s ",dobj.errdesc)
		return dobj


	def stopSubscription(self):
		logger.warning("receving stop subscription")
		if self.__status == "STARTED":
			self.__status = "STOPPING"
			logger.warning(" stopping subscription %s",self.__status)
		else:
			if self.__status != "STOPPING":
				logger.warning("subscriber is being stopped or not started %s ", self.__status)
				return
		while self.__status != "STOPPED":
			time.sleep(0.1)

		logger.warning("subscriber is  stopped %s ", self.__status)



