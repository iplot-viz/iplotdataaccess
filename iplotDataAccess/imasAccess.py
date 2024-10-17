import operator
import re
import numpy as np
import imas
import os
import sys
from typing import List, Union
import xml.etree.ElementTree as ET

import cachetools as ct
from PySide6.QtCore import QDir
from iplotLogging import setupLogger
try:
    from data_dictionary import idsdef as idsdd
except ImportError:
    from data_dictionary import idsinfo as idsdd

from cachetools import cachedmethod
from iplotDataAccess.dataCommon import DataObj, DataType

logger = setupLogger.get_logger(__name__)

CBS_ATTR = ['documentation', 'data_type', 'units', 'dimension']


class IMASDataAccess:
    database = 'iter'
    user_or_path = 'public'
    imas_backend = imas.imasdef.MDSPLUS_BACKEND
    pulse = None
    run = None
    uri = None
    __input = None
    __isConnected = False
    try:
        dd = idsdd.IDSDef()
    except AttributeError:
        dd = idsdd.IDSInfo()
    access_cache = ct.LRUCache(maxsize=100)

    def __init__(self):
        self.idsdef_path = self.getIdsDefXml()

    def connect_source(self, connection_string=""):
        if connection_string.startswith("imas:"):
            self.uri = connection_string
        else:
            myconn = connection_string.split(",")
            self.configure(list_i=myconn)
        # self.connect()
        return self.__input, self.__isConnected

    def configure(self, list_i=None):
    	self.uri=None
    	if list_i is None:
    		list_i = []
    		return
    	for s in list_i:
    		if s.startswith("uri"):
    			self.uri = s.split("=", 1)[1]
    			break
    		if s.startswith("database"):
    			self.database = s.split("=")[1]
    		if s.startswith("path"):
    			self.user_or_path = s.split("=")[1]
    		if s.startswith("backend"):
    			temp = s.split("=")
    			if temp[1] == "MDSPLUS":
    				self.backend = imas.imasdef.MDSPLUS_BACKEND
    			if temp[1] == "MEMORY":
    				self.backend = imas.imasdef.MEMORY_BACKEND
    			if temp[1] == "HDF5":
    				self.backend = imas.imasdef.HDF5_BACKEND
    		if s.startswith("pulseIdent"):
    			temp = s.split("=")[1]
    			ret = temp.split("/")
    			try:
    				logger.info(" ret %s",ret)
    				self.pulse = int(ret[0])
    				if len(ret) == 2:
    					self.run = int(ret[1])
    				else:
    					self.run = 0
    				logger.info(" ret %s",ret)
    			except ValueError:
    				logger.error("got an invalid pulse identifier %s ", temp)
    				self.run = 0
    				self.pulse = 0

    def connect(self):
        try:
            if self.uri is None:
                self.uri = imas.DBEntry.build_uri_from_legacy_parameters(
                    backend_id=self.backend,
                    pulse=self.pulse,
                    run=self.run,
                    db_name=self.database,
                    user_name=self.user_or_path,
                    data_version="3",
                )
            logger.info(f"IMAS URI = {self.uri}")
            self.__input = imas.DBEntry(uri=self.uri, mode="r")
            [err, _] = self.__input.open()
            if err != 0:
                logger.warning("not connected to imas db")
                self.__isConnected = False
                self.__input = None
            else:
                logger.debug("connected to imas db")
            self.__isConnected = True
        except (TypeError, UnboundLocalError) as e:
            logger.warning("not connected to imas db, URI is invalid or empty")
            self.__isConnected = False
            self.__input = None
            return
        except imas.UALBackendException as ual:
            logger.warning("issue with opening the file %s ", ual)
            self.__isConnected = False
            self.__input = None
            return

    def is_connected(self):
        return self.__isConnected

    def get_pulses(self, pulse='*', run='????', **kwargs):
        run_path = '0'
        user = 'public'
        db = 'ITER'
        version = '3'

        path: str
        if user == 'public':
            path = QDir().rootPath() + QDir(os.getenv('IMAS_HOME','work/imas')+'/shared/imasdb').path()

        path = QDir().separator().join([path, self.database, str(version)])
        path = QDir.cleanPath(path)

        glob = f'1*'
        idss = QDir(path)
        idss.setNameFilters([glob])
        plist=[]
        for i in idss.entryList():
            runt=QDir(path+"/"+i)
            runF=runt.entryList()
            for run in runF:
                try :
                    int(run)
                    plist.append(i+"_"+run)
                except ValueError:
                    #logger.warning("discarding the . folder")
                    pass
                
        return plist

    def get_pulse_info(self, pulse, run):
        db = 'ITER'
        user = 'public'
        logger.info("in get pulse info %s",pulse)
        input_imas = imas.DBEntry(self.backend, self.database, pulse, run, user)
        error = input_imas.open()
        if error[0] < 0:
            print("Data entry not valid: ", error)
            return

        ids_list = []
        ids_list_complete = self.getIDSNames()

        for ids_name in ids_list_complete:
            t = input_imas.get_node(ids_name, 'ids_properties/homogeneous_time')
            if t != -999999999:
                t = len(input_imas.get_node(ids_name, 'time'))
                ids_list.append([ids_name, str(t)])

        input_imas.close()

        return ids_list

    def get_var_list(self, pattern='.*'):
        return self.get_cbs_list(pattern)

    def getIDSNames(self) -> Union[List, None]:
        if self.idsdef_path is not None:
            tree = ET.parse(self.idsdef_path)
            root = tree.getroot()
            idsnames = [ids.attrib["name"] for ids in root.findall("IDS")]
            return idsnames
        return None

    def get_varasdasda(self, sep=':', pattern='*', times='0'):
        return self.getIDSNames()

    def getIdsDefXml(self) -> Union[str, None]:
        idsdef_path = ""
        if "IMAS_PREFIX" in os.environ:
            imaspref = os.environ["IMAS_PREFIX"]
            idsdef_path = f"{imaspref}/include/IDSDef.xml"

        if not idsdef_path:
            logger.error("Error while trying to access IDSDef.xml, make sure you've loaded IMAS module")
            return None
        return idsdef_path

    def get_cbs_list(self, pattern='.*'):
        def get_child(element, path, pattern):
            children = {}
            child_returned = False
            for attr in CBS_ATTR:
                if attr in element.attrib:
                    children[attr] = element.attrib[attr]
                    if attr == "data_type" and children["data_type"][-1] == "D":
                        children["dimension"] = children["data_type"][-2]

            for child in element.findall("./field"):
                child_name = child.attrib['name']
                new_child = get_child(child, path + '-' + child_name, pattern)
                if new_child:
                    children[child_name] = new_child
                    child_returned = True

            if re.match(pattern, path) or child_returned:
                return children

        tree = ET.parse(self.idsdef_path)
        root = tree.getroot()

        all_children = {}
        for ids in root.findall("IDS"):
            id_name = ids.attrib['name']
            child = get_child(ids, id_name, pattern)
            if re.match(pattern, id_name) or child:
                all_children[id_name] = get_child(ids, id_name, pattern)

        return all_children

    def get_ids_names(self, root):
        return [ids.attrib["name"] for ids in root.findall("IDS")]

    def list_ids_fields(self, root):
        search_result = {}
        for ids in root.findall("IDS"):
            is_top_node = False
            top_node_name = ""
            search_result_for_ids = {}
            for field in ids.iter("./field"):
                attributes = {}

                if "units" in field.attrib.keys():
                    attributes["units"] = field.attrib["units"]
                    if "as_parent" in attributes["units"]: # go up the AoS until we find the real unit:
                        for sfield in reversed(fieldlist):
                            if "units" in sfield.attrib.keys():
                                if "as_parent" not in sfield.attrib["units"]:
                                    attributes["units"] = sfield.attrib["units"]
                                    break
                    attributes["units"] = field.attrib["units"]
                if "documentation" in field.attrib.keys():
                    attributes["documentation"] = field.attrib["documentation"]
                if "data_type" in field.attrib.keys():
                    attributes["data_type"] = field.attrib["data_type"]

                field_path = re.sub("\(([^:][^itime]*?)\)", "(:)", field.attrib["path_doc"])
                if "timebasepath" in field.attrib.keys():
                    field_path = re.sub("\(([:]*?)\)$", "(itime)", field_path)
                search_result_for_ids[field_path] = attributes
                if not is_top_node:
                    is_top_node = True
                    top_node_name = ids.attrib["name"]
            if top_node_name:  # add to dict only if something is found
                search_result[top_node_name] = search_result_for_ids
        return search_result

    def clear_cache(self):
        self.access_cache.clear()

    @cachedmethod(operator.attrgetter('access_cache'))
    def get_data(self, **kwargs):
        mycfg = []
        varname = ""
        tsS = None
        tsE = None
        if kwargs.get("varname"):
            varname = kwargs.get("varname")
            # if varprefix is not None and len(varprefix) > 0:
            #     varname = varname1.replace(varprefix, "", 1)
            # else:
            #     varname = varname1
        if kwargs.get("uri"):
            mycfg.append("uri=" + kwargs.get("uri"))
            self.configure(mycfg)
        if kwargs.get("pulse"):
        	logger.info("get a pulse %s",kwargs.get("pulse"))
        	pulseId = kwargs.get("pulse")
        	if pulseId.startswith("imas:"):
        		mycfg.append("uri=" + pulseId)
        	else:
        		mycfg.append("pulseIdent=" + pulseId)
        	self.configure(mycfg)
        if kwargs.get("tsS"):
            tsST = kwargs.get("tsS")
            try:
                tsS = float(tsST)
            except ValueError as e:
                logger.error("Invalid value for tsS: %s", e)
                dobj = DataObj()
                return dobj

        if kwargs.get("tsE"):
            tsET = kwargs.get("tsE")
            try:
                tsE = float(tsET)
            except ValueError as e:
                logger.error("Invalid value for tsE: %s", e)
                dobj = DataObj()
                return dobj
        self.connect()
        return self.get_data_i(varname, tsS, tsE)

    @staticmethod
    def __get_units(meta):
        # this function does not work if we provide indexes on array so indices should be removed ...
        try:
            units = meta["units"]
        except KeyError as _:
            units = ""
        return units

    def __get_metadata(self, idsn, idsp):
        # this function does not work if we provide indexes on array so indices should be removed ...
        idsp1 = re.sub("([(\[]).*?([)\]])", "", idsp)
        logger.debug("get unit for  %s", idsp1)
        metadata = self.dd.query(idsn, idsp1)

        return metadata

    def __get_time_data(self, idsn, idsp):
        timevec = []
        try:
            time_type = self.__input.partial_get(ids_name=idsn, data_path="ids_properties/homogeneous_time")
            if time_type == 1:
                dpath = "time"
            else:
                # dpath=idsp[0:idsp.rfind("/")] + "/time"
                dpath = idsp.rpartition("/")[0] + "/time"
            timevec = self.__input.partial_get(ids_name=idsn, data_path=dpath)

        except AttributeError as err:
            logger.error("Invalid attribute: %s", err)
        except NameError as ne:
            logger.error("Invalid attribute: %s", ne)
        except imas.hli_exception.ALException as ale:
            logger.error("Invalid attribute: %s", ale)

        return timevec

    def get_data_i(self, idspath_o=None, ts_s=None, ts_e=None):
        dobj = DataObj()
        if idspath_o is None:
            return dobj

        idspath_1 = idspath_o.replace('[', '(')
        idspath = idspath_1.replace(']', ')')
        if idspath.startswith("/"):
            res = idspath.split("/", 2)

        else:
            res = idspath.split("/", 1)

        logger.debug("res=%s", res)

        if not self.is_connected():
            self.connect()
        if not self.is_connected():
            dobj.xdata = []
            dobj.ydata = []
            return dobj
        # first we need to know if we are accessing an array of structure time dependent or not...

        try:
            level1 = res[-1].split("/", 1)
            metadata = self.__get_metadata(res[-2], level1[0])
            # print("found meta %s", metadata)
            dp = metadata["data_type"]
            ts = metadata["timebasepath"]
            # print("found dp =%s and ts=%s ", dp, ts)
            if dp == "struct_array" and ts == "time":
                if re.search(r'\(:\)|\(0\)|\(\d+\)', level1[0]):
                    idsp = '/'.join(level1)
                else:
                    idsp = level1[0] + "(:)/" + level1[1]
            else:
                idsp = res[-1]
        except KeyError as _:
            idsp = res[-1]
        except IndexError as _:
            logger.error(f"unexpected combination for ids data retrieval ={res}")
            dobj.xdata = []
            dobj.ydata = []
            return dobj
        dobj.set_a(DataType.DA_TYPE_FLOAT, DataType.DA_TYPE_FLOAT, 'Time', '', '', '', 1)
        try:
            # print("ids res %s", res[-1], idsp)

            if len(res) == 1:
                dobj.set_data(self.__input.partial_get(ids_name=res[-1], data_path=""), 2)
            else:
                dobj.set_data(self.__input.partial_get(ids_name=res[-2], data_path=idsp), 2)
            if dobj.ydata is not None:
                dobj.set_data(self.__get_time_data(idsn=res[-2], idsp=idsp), 1)
                metadata = self.__get_metadata(res[-2], res[-1])
                dobj.yunit = self.__get_units(metadata)
                if "as_parent" in dobj.yunit: # we go up until we find the parent unit:
                    res_up = res[-1]
                    while "as_parent" in dobj.yunit:
                        res_up = res_up.rpartition("/")[0]
                        meta_up = self.__get_metadata(res[-2], res_up)
                        dobj.yunit = self.__get_units(meta_up)
                time_type = self.__input.partial_get(ids_name=res[-2], data_path="ids_properties/homogeneous_time")
                if time_type == 0:  # time under each data (heterogenous)
                    dpath = res[-1].rpartition('/')[0] + "/time"
                elif time_type == 1:  # global time (homogenous)
                    dpath = "time"
                else:  # static (no time)
                    dpath = ""
                metaTime = self.__get_metadata(res[-2], dpath)
                dobj.xunit = self.__get_units(metaTime)

                if dobj.yunit is not None:
                    logger.debug(" found unit %s", dobj.yunit)
                if dobj.xdata is None:
                    logger.debug(" xdata is NONE ")
                else:
                    logger.debug(" xdata is NOT NONE %d ", len(dobj.xdata))
                if ts_e is not None or ts_s is not None:
                    if ts_e is None:
                        ts_e = dobj.xdata[-1]
                    if ts_s is None:
                        ts_s = dobj.xdata[0]

                    idx = np.where((dobj.xdata >= ts_s) & (dobj.xdata <= ts_e))
                    # newidx=np.where((dobj.xdata >= tsS) & (dobj.xdata <= tsE))
                    dobj.xdata = dobj.xdata[idx]
                    # newidx=[slice(None)] * (dobj.ydata.ndim - 1) + [idx]
                    # this extracts the last dimension
                    # print("ndim: ", dobj.ydata.ndim)
                    if dobj.ydata.ndim == 1:
                        dobj.ydata = dobj.ydata[idx]
                    elif dobj.ydata.ndim == 2:
                        dobj.ydata = dobj.ydata[:][idx]
                    elif dobj.ydata.ndim == 3:
                        dobj.ydata = dobj.ydata[:][:][idx]

            else:
                dobj.xdata = []
                dobj.ydata = []

            dobj.errcode = 0
            # The database is being closed after each signal
            # Should not close memory backend otherwise database is destroyed
            if self.imas_backend != imas.imasdef.MEMORY_BACKEND:
                self.close()

        except AttributeError as err:
            logger.debug("Invalid attribute: %s", err)
            dobj.errcode = -1
            dobj.errdescr = "Invalid IDS path"
            dobj.ydata = []
            dobj.xdata = []
        except NameError as ne:
            logger.debug("Invalid name: %s", ne)
            dobj.errcode = -1
            dobj.errdescr = "Invalid IDS path"
            dobj.ydata = []
            dobj.xdata = []
        except imas.hli_exception.ALException as ale:
            logger.debug("Invalid hli exc: %s", ale)
            dobj.errcode = -1
            dobj.errdescr = "Invalid IDS path"
            dobj.ydata = []
            dobj.xdata = []
        except ValueError as ve:
            logger.debug("Invalid hli exc: %s", ve)
            dobj.errcode = -1
            dobj.errdescr = "Invalid IDS path"
            dobj.ydata = []
            dobj.xdata = []
        return dobj

    def close(self):
        if self.is_connected():
            self.__input.close()
            self.__isConnected = False

    def get_envelope(self, **kwargs):
        dmin = self.get_data(**kwargs)
        dmax = dmin
        logger.debug("envelope function returning %d", len(dmin))
        return dmin, dmax
