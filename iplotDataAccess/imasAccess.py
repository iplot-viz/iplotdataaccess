import operator
import re
import numpy as np
import imas
import cachetools as ct
from iplotLogging import setupLogger
from data_dictionary import idsdef
from cachetools import cachedmethod
from iplotDataAccess.dataCommon import DataObj, DataType

logger = setupLogger.get_logger(__name__)


class IMASDataAccess:
    database = 'iter'
    user_or_path = 'public'
    imas_backend = imas.imasdef.MDSPLUS_BACKEND
    # imas_dd_units = imas.dd_units.DataDictionaryUnits()
    __input = None
    pulse = None
    run = None
    # user_or_path = 'public'
    # database     = 'iter'
    __isConnected = False
    dd = idsdef.IDSDef()
    access_cache = ct.LRUCache(maxsize=100)

    def connect_source(self, connection_string=""):
        # self.connection_string="database=ITER,user_or_path=public,backend=MDSPLUS"##
        myconn = connection_string.split(",")
        self.configure(list_i=myconn)
        # self.connect()
        return self.__input, self.__isConnected

    def configure(self, list_i=None):
        if list_i is None:
            list_i = []
        for s in list_i:
            if s.startswith("database"):
                temp = s.split("=")
                self.database = temp[1]
            if s.startswith("path"):
                temp = s.split("=")
                self.user_or_path = temp[1]
            if s.startswith("backend"):
                temp = s.split("=")
                if temp[1] == "MDSPLUS":
                    self.imas_backend = imas.imasdef.MDSPLUS_BACKEND
                if temp[1] == "MEMORY":
                    self.imas_backend = imas.imasdef.MEMORY_BACKEND
                if temp[1] == "HDF5":
                    self.imas_backend = imas.imasdef.HDF5_BACKEND
            if s.startswith("pulseIdent"):
                temp = s.split("=")[1]
                ret = temp.split("/")
                try:
                    self.pulse = int(ret[0])
                    if len(ret) == 2:
                        self.run = int(ret[1])
                    else:
                        self.run = 0
                except ValueError:
                    logger.error("got an invalid pulse identifier %s ", temp)
                    self.run = 0
                    self.pulse = 0

    def connect(self):
        try:
            if self.pulse is None or self.run is None:
                logger.warning("not connected to imas db,pulse or pulse is empty")
                self.__isConnected = False
                self.__input = None
                return
            self.__input = imas.DBEntry(self.imas_backend, self.database, self.pulse, self.run, self.user_or_path)
            [err, _] = self.__input.open()
            if err != 0:
                logger.warning("not connected to imas db")
                self.__isConnected = False
                self.__input = None

            else:
                logger.debug("connected to imas db")
            self.__isConnected = True
        except imas.UALBackendException as ual:
            logger.warning("issue with opening the file %s ", ual)
            self.__isConnected = False
            self.__input = None

    def is_connected(self):
        return self.__isConnected

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
        if kwargs.get("pulse"):
            mycfg.append("pulseIdent=" + kwargs.get("pulse"))
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
            print("found meta %s", metadata)
            dp = metadata["data_type"]
            ts = metadata["timebasepath"]
            print("found dp =%s and ts=%s ", dp, ts)
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
            print("ids res %s", res[-1], idsp)

            if len(res) == 1:
                dobj.set_data(self.__input.partial_get(ids_name=res[-1], data_path=""), 2)
            else:
                dobj.set_data(self.__input.partial_get(ids_name=res[-2], data_path=idsp), 2)
            if dobj.ydata is not None:
                dobj.set_data(self.__get_time_data(idsn=res[-2], idsp=idsp), 1)
                metadata = self.__get_metadata(res[-2], res[-1])
                dobj.yunit = self.__get_units(metadata)
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
                    print(dobj.ydata.ndim)
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
