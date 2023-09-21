import numpy as np
from enum import Enum
from collections import deque
import iplotDataAccess.dataCommon as dc
import time
import iplotLogging.setupLogger as ls
logger = ls.get_logger(__name__)
try:
	import requests

except ModuleNotFoundError:
	logger.warning("import'requests' is not installed")


try:
	import sseclient
	print("sseclient is installed")
except ModuleNotFoundError:
	logger.warning("import'sseclient' is not installed")

try:
	import getpass
except ModuleNotFoundError:
	logger.warning("import getpass is not installed")




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
		logger.debug(f'create queues for vkeys={vkeys}')
		for vk in vkeys:
			sname = params[vk] + '@' + str(vk)
			if self.vardata.get(sname) is not None:
				logger.debug("adding data to queue for vname=%s", sname)
				self.vardata[sname].append(data)
			else:
				logger.debug(f'create queue for vname={sname}')
				if vtype.startswith(VarType.pon.value):
					self.vardata[sname] = deque([data], self.maxsizeP)
				else:
					self.vardata[sname] = deque([data], self.maxsize)

	def __parseData(self, data, params=[]):
		q = None
		if data.startswith("heartbeat"):
			return
		line = data.split(" ")
		if len(line) == 1:  # If data is only one token, it is only time
			return
		num_samples = int(line[ProtoHeader.NB_SMP.value])
		xtype = dc.DataType.DA_TYPE_ULONG
		xlabel = "Time"
		ylabel = ""
		xunit = "ns"
		yunit = ""
		drank = 1
		ytype = ""
		try:
			ytype = self.__convertType(line[ProtoHeader.VAL_DT.value])
		except IndexError as ie:
			logger.warning("index error for line %s", line)
			return
		if ytype == dc.DataType.DA_TYPE_STRING:
			logger.warning("string not currently supported for streaming, skipping")
			return

		if line[ProtoHeader.VAL_DT.value].startswith("E"):
			logger.warning(f"Event message for line {line}")
			return
		if line[ProtoHeader.VAL_DT.value] in ['PD', 'PS']:
			val = data.split(" V ")
		else:
			val = data.split()
			val = [" ".join(val[:4])] + [" ".join(val[i:i + 2]) for i in range(4, len(val), 2)]
		##TODO
		###protect the code in case of event mixing up
		# ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513472231 ', '0.421761 NO_ALARM NO_ALARM']
		# ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513480496 ', '0.333320 NO_ALARM NO_ALARM']
		# ['UTIL-HV-S22-BUS3:TOTAL_POWER L PD 1 1631513492192 ', '0.000000 NO_ALARM NO_ALARM']
		# ['UTIL-HV-S22:TOTAL_POWER_LC13 L PD 2 1629706018897 1629706018901  E[9] Connected ', '0.000000 NO_ALARM NO_ALARM']
		# ['UTIL-HV-S22:TOTAL_POWER_LC13 L PD 2 1629706018897 1629706018901  E[9] Connected ', '0.000000 NO_ALARM NO_ALARM']
		if len(val) < num_samples + 1:
			logger.warning("sline mixing event and data skipping %s", val)
			return
		xdata = np.zeros(num_samples, dtype='uint64')
		ydata = np.zeros(num_samples)
		d = dc.DataObj()
		yunit = self.__units.get(line[ProtoHeader.VARNAME.value])
		d.setA(xtype, ytype, xlabel, ylabel, xunit, yunit, drank)
		for i in range(num_samples):
			xdata[i] = int(line[ProtoHeader.NB_SMP.value + i + 1]) * 1000000
			ydata[i] = float(val[i + 1].split(" ")[0])

		d.setData(xdata, 1)
		d.setData(ydata, 2)
		##logger.debug("before calling check duplocate")
		vkeys = self.__checkIfduplicate(line[ProtoHeader.VARNAME.value], params=params)
		self.__createQueues(vkeys, line[ProtoHeader.VAL_DT.value], d, params=params)

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
		self.__status = "STARTED"
		try:
			for event in self.client.events():
				logger.debug(f'found new data {event.data}')
				if self.__status == "STOPPING":
					logger.info("receiving stop request")
					break
				self.__parseData(event.data, params=paramsT)
		except ConnectionError as ce:
			self.__status = "ERROR"
			raise RTStreamerException(" connection lost - see log for more details")
		self.client.close()
		self.response.close()
		if self.vardata is not None:
			for k in self.vardata.keys():
				self.vardata[k].clear()
		self.__status = "STOPPED"

	def __getNextDataI(self,vname):
		idx = -1
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
			# logger.debug("invalid get next data call variable %s not in the list",vname)
		except IndexError:
			dobj = dc.DataObj()
			dobj.setEmpty("Index error : varname not in the keys")
			# logger.debug("invalid get next data call variable %s no data in the list",vname)

		return dobj

	###expect orig name with expression -> handle the case where we subscribe to the same variable but different expressions are applied to them
	def getNextData(self, vname=None):
		#logger.debug("got a call vanme=%s",vname)
		if vname is None:
			dobj = dc.DataObj()
			dobj.setEmpty("Varname is empty")
			return dobj

		dobj = self.__getNextDataI(vname)
		if len(dobj.xdata) == 0:
			dobj = dc.DataObj()
			dobj.setEmpty("No data found")
		else:
			logger.debug(f'vname={vname} timestamp {dobj.xdata} and val={dobj.ydata}')
		return dobj


	def stopSubscription(self):
		logger.debug("receving stop subscription")
		if self.__status == "STARTED":
			self.__status = "STOPPING"
			logger.debug('stopping subscription')
		elif self.__status != "STOPPING":
			logger.warning(f'ignored stopping subscription because of status of {self.__status}')
