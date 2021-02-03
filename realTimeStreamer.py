

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
	def __init__(self, url=None, headers=None, auth=None):
		self.urlX = url or 'http://io-ls-udaweb1.iter.org/dashboard/backend/sse'
		self.params = None
		self.username = None
		self.password = None
		self.auth = auth
		self.response = None
		self.client = None
		self.__status = "INIT"
		#self.headers = {'User-Agent': 'it_script_basic'}
		self.headers = headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
		###headers or {'REMOTE_USER': getpass.getuser(), 'User-Agent': 'python_client'}
		self.vardata={}
		self.maxsizeP=100
		self.maxsize=1000
		##logging.basicConfig(filename="/tmp/output_pro.log", format='%(asctime)s -%(levelname)s-%(funcName)s-%(message)s', datefmt='%Y-%m-%dT%H:%M:%S', level=logging.DEBUG)
		##self.logger = logging.getLogger(__name__)

	def __checkAndFillHeaders(self):
		for k, v in self.headers.items:
			if v == "$USERNAME":
				self.headers[k] = getpass.getuser()

	def __setParams(self, params=[]):
		if params is not None and len(params)>0:
			self.params = "variables="+",".join(params)

	def __convertType(self, utype):

		if utype == "D" or utype == "PD":
			return dc.DataType.DA_TYPE_DOUBLE

		elif utype == "L":
			return dc.DataType.DA_TYPE_LONG
		elif utype == "S" or utype == "PS":
			return dc.DataType.DA_TYPE_STRING

	def __parseData(self, data,counter):
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
		d.setA(xtype, ytype, xlabel, ylabel, xunit, yunit, drank)
		for i in range(int(line[ProtoHeader.NB_SMP.value])):
			xdata[i] = int(line[ProtoHeader.NB_SMP.value+i+1])*1000000
			ydata[i] = float(val[i+1].split(" ")[0])

		d.setData(xdata, 1)
		d.setData(ydata, 2)

		if len(self.vardata.keys()) == 0 or self.vardata.get(line[ProtoHeader.VARNAME.value]) is None:
			if line[ProtoHeader.VAL_DT.value].startswith(VarType.pon.value):
				self.vardata[line[ProtoHeader.VARNAME.value]] = deque([d], self.maxsizeP)
			else:
				self.vardata[line[ProtoHeader.VARNAME.value]] = deque([d], self.maxsize)
		else:
			self.vardata[line[ProtoHeader.VARNAME.value]].append(d)
			if counter % 10 == 0:
				logger.debug("queue length %d and timestamp %d and val=%f",
							 len(self.vardata[line[ProtoHeader.VARNAME.value]]), xdata[0], ydata[0])

	def getStatus(self):
		return self.__status

	def startSubscription(self, params=[]):
		if self.__status == "STARTED":
			logger.error("Subscription is already started, needs to be stopped first or launch a new RTStreamer")
			raise RTStreamerException(" Streamer already started")
		self.__setParams(params)
		url1 = self.urlX + '?' + self.params
		logger.debug(self.headers)

		#response = requests.get(url=url1, stream=True, headers=self.headers, auth=self.auth, timeout=None)
		try:
			self.response = requests.get(url=url1, stream=True, headers=self.headers, timeout=None)
		except ConnectionError as ce:
			logger.error("got connection error %s with errcode = %d ", ce, self.response.status_code)
			self.__status = "ERROR"
			raise RTStreamerException(" could not connect - see log for more details")
			#print(response.headers)

		self.client = sseclient.SSEClient(self.response)
		i = 0
		self.__status = "STARTED"
		for event in self.client.events():
			logger.debug("found new data %s",event.data)
			if self.__status == "STOPPING":
				break
			self.__parseData(event.data, i)
			if i < 1000:
				i = i + 1
		self.client.close()
		self.response.close()
		if self.vardata is not None:
			for k in self.vardata.keys():
				self.vardata[k].clear()
		self.__status = "STOPPED"

	def getNextData(self, vname=None):
		if vname is None:
			dobj = dc.DataObj()
			dobj.setEmpty("Varname is empty")
			return dobj
		if vname in self.vardata.keys():
			try:
				dobj = self.vardata[vname].popleft()
				logger.debug("timestamp %d and val=%f", dobj.xdata[0], dobj.ydata[0])
			except IndexError:
				dobj = dc.DataObj()
				dobj.setEmpty("No data found")
			return dobj
		else:
			dobj = dc.DataObj()
			dobj.setEmpty("varname not in the keys")
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



