import fnmatch
import re

import cachetools as ct
import iplotLogging.setupLogger as setupLog
import numpy as np
import pandas as pd
from pandas import DataFrame

from iplotDataAccess import dataCommon
from iplotDataAccess.dataSource import DS_PYUDA_TYPE, DataSource

logger = setupLog.get_logger(__name__)


class PyudaAccess(DataSource):
    """Data source for the UKAEA UDA servers (MAST, MAST-U) through pyuda.

    Signals are addressed by name (``ip``, ``ane_density``, ``/AMC/PLASMA_CURRENT``)
    and shot number. Time is relative to the shot, in seconds, so only the pulse
    access mode applies.
    """
    source_type = DS_PYUDA_TYPE
    DEFAULT_CACHE_SIZE = 100
    DEFAULT_PULSE_LIST_SIZE = 200
    DEFAULT_ENVELOPE_POINTS = 1000
    GENERIC_FOLDER = "GENERIC"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.host = config.get("host")
        self.port = config.get("port")
        # Shot whose signal list fills the variable tree; the latest shot when unset.
        self.list_shot = config.get("list_shot")
        self.pulse_list_size = int(config.get("pulse_list_size", self.DEFAULT_PULSE_LIST_SIZE))
        self.client = None
        self.connected = False
        self.signal_cache = ct.LRUCache(maxsize=self._cache_size(config))
        self._signal_list = None

    @classmethod
    def _cache_size(cls, config: dict) -> int:
        try:
            return max(1, int(config.get("cache_size", cls.DEFAULT_CACHE_SIZE)))
        except (TypeError, ValueError):
            return cls.DEFAULT_CACHE_SIZE

    def connect(self) -> bool:
        try:
            import pyuda
            if self.host:
                pyuda.Client.server = self.host
            if self.port:
                pyuda.Client.port = int(self.port)
            self.client = pyuda.Client()
            self.client.latest_shot()
            self.connected = True
        except Exception as e:
            logger.error("Could not connect to pyuda server %s:%s -> %s", self.host, self.port, e)
            self.errcode = -1
            self.errdesc = str(e)
            self.connected = False
        return self.connected

    def is_connected(self):
        return self.connected

    def clear_cache(self):
        self.signal_cache.clear()
        self._signal_list = None

    @staticmethod
    def parse_shot(pulse):
        """Return the shot number of a pulse such as ``30420`` or ``MAST/30420``, else None."""
        if pulse is None:
            return None
        text = str(pulse).strip()
        text = re.split(r"[/:]", text)[-1]
        try:
            return int(text)
        except ValueError:
            return None

    def latest_shot(self) -> int:
        return int(self.client.latest_shot())

    def _resolve_shot(self, pulse):
        shot = self.parse_shot(pulse)
        # 0 is the latest shot and -N the N-th one before it, as for CODAC UDA.
        if shot is not None and shot < 1:
            shot = self.latest_shot() + shot
        return shot

    def _fetch_signal(self, varname: str, shot: int):
        key = (varname, shot)
        if key not in self.signal_cache:
            self.signal_cache[key] = self.client.get(varname, shot)
        return self.signal_cache[key]

    def _get_series(self, **kwargs):
        """Return (time, data, signal, resolved_shot) cropped to [tsS, tsE], or raise ValueError."""
        varname = kwargs.get("varname")
        if not varname:
            raise ValueError("No variable name given")
        shot = self._resolve_shot(kwargs.get("pulse"))
        if shot is None:
            raise ValueError("PYUDA data sources need a pulse (shot) number")

        signal = self._fetch_signal(varname, shot)
        data = np.asarray(signal.data)
        if data.ndim != 1:
            raise ValueError(f"'{varname}' has {data.ndim} dimensions; only 1D signals are supported")
        time = signal.time
        if time is None:
            xdata = np.arange(len(data), dtype=float)
        else:
            xdata = np.asarray(time.data, dtype=float)

        mask = np.ones(len(xdata), dtype=bool)
        ts_s = kwargs.get("tsS")
        ts_e = kwargs.get("tsE")
        if ts_s is not None:
            mask &= xdata >= float(ts_s)
        if ts_e is not None:
            mask &= xdata <= float(ts_e)
        return xdata[mask], data[mask], signal, shot

    def _set_units(self, dobj, signal):
        time = signal.time
        dobj.xunit = (getattr(time, "units", "") if time is not None else "") or "s"
        dobj.yunit = getattr(signal, "units", "") or ""
        dobj.ylabel = getattr(signal, "label", "") or ""

    def get_data(self, **kwargs):
        dobj = dataCommon.DataObj()
        try:
            xdata, ydata, signal, shot = self._get_series(**kwargs)
        except Exception as e:
            logger.warning("pyuda get_data failed for %s -> %s", kwargs.get("varname"), e)
            dobj.set_err(-1, str(e))
            return dobj

        nbp = kwargs.get("nbp") or -1
        if 0 < nbp < len(xdata):
            step = int(np.ceil(len(xdata) / nbp))
            xdata = xdata[::step]
            ydata = ydata[::step]

        dobj.xdata = xdata
        dobj.ydata = ydata
        self._set_units(dobj, signal)
        if self.parse_shot(kwargs.get("pulse")) != shot:
            dobj.resolved_pulse = str(shot)
        return dobj

    def get_envelope(self, **kwargs):
        denv = dataCommon.DataEnvelope()
        try:
            xdata, ydata, signal, shot = self._get_series(**kwargs)
        except Exception as e:
            logger.warning("pyuda get_envelope failed for %s -> %s", kwargs.get("varname"), e)
            denv.set_empty(str(e))
            return denv

        nbp = kwargs.get("nbp") or -1
        if nbp <= 0:
            nbp = self.DEFAULT_ENVELOPE_POINTS
        bins = [b for b in np.array_split(np.arange(len(xdata)), min(nbp, len(xdata))) if len(b)]
        denv.set_x_data(np.array([xdata[b[0]] for b in bins]))
        denv.set_y_data(np.array([ydata[b].min() for b in bins]),
                        np.array([ydata[b].max() for b in bins]),
                        np.array([ydata[b].mean() for b in bins]))
        self._set_units(denv, signal)
        if self.parse_shot(kwargs.get("pulse")) != shot:
            denv.resolved_pulse = str(shot)
        return denv

    def get_pulses_df(self, pattern="*") -> DataFrame:
        """Return the shots that match ``pattern``, oldest first, in columns Pulse and Run.

        A plain shot number checks that this shot exists. Any other pattern is a glob
        applied to the most recent ``pulse_list_size`` shots.
        """
        columns = ["Pulse", "Run"]
        try:
            latest = self.latest_shot()
        except Exception as e:
            logger.error("pyuda could not get the latest shot -> %s", e)
            return pd.DataFrame(columns=columns)

        text = str(pattern or "*").strip()
        if text.isdigit():
            shot = int(text)
            shots = [shot] if 1 <= shot <= latest else []
        else:
            glob = text.split("/")[-1].split(":")[-1] or "*"
            first = max(1, latest - self.pulse_list_size + 1)
            shots = [s for s in range(first, latest + 1) if fnmatch.fnmatch(str(s), glob)]
        return pd.DataFrame({"Pulse": [str(s) for s in shots], "Run": [0] * len(shots)}, columns=columns)

    def search_pulses_df(self, text: str) -> DataFrame:
        """Return the recent shots that contain ``text``.

        A shot number also gives that shot and the shots that start with it and have
        up to two more digits (``3042`` gives 3042, 30420 to 30429 and 304200 to 304299).
        """
        text = str(text or "").strip()
        if not text:
            return self.get_pulses_df()
        if any(c in text for c in "*?["):
            return self.get_pulses_df(pattern=text)
        found = self.get_pulses_df(pattern=f"*{text}*")
        if text.isdigit() and int(text) > 0:
            latest = self.latest_shot()
            prefix = int(text)
            candidates = [prefix, *range(prefix * 10, prefix * 10 + 10), *range(prefix * 100, prefix * 100 + 100)]
            shots = [str(s) for s in candidates if s <= latest]
            found = pd.concat([found, pd.DataFrame({"Pulse": shots, "Run": [0] * len(shots)})])
        found = found.drop_duplicates(subset="Pulse")
        return found.sort_values("Pulse", key=lambda p: p.astype(int)).reset_index(drop=True)

    def get_pulse_info(self, pulse=None, run=None, **kwargs):
        shot = self.parse_shot(pulse)
        return {"shot": shot, "run": run, "latest_shot": self.latest_shot()}

    def _list_signals(self):
        if self._signal_list is None:
            shot = self.parse_shot(self.list_shot) or self.latest_shot()
            self._signal_list = list(self.client.list_signals(shot=shot))
        return self._signal_list

    def get_var_dict(self, pattern=".*", **kwargs) -> dict:
        """Return the signal names grouped by source alias: {ALIAS: {signal_name: ''}}.

        Signals that have a generic name (``IP``, ``BT``) also go in the GENERIC folder.
        """
        try:
            signals = self._list_signals()
        except Exception as e:
            logger.error("pyuda could not list signals -> %s", e)
            return {}

        regex = re.compile(pattern or ".*", re.IGNORECASE)
        tree = {}
        for item in signals:
            generic = getattr(item, "generic_name", "")
            if generic and regex.search(generic):
                tree.setdefault(self.GENERIC_FOLDER, {})[generic] = ""
            name = item.signal_name
            if not name or not regex.search(name):
                continue
            alias = (item.source_alias or "other").upper()
            tree.setdefault(alias, {})[name] = ""
        return {alias: dict(sorted(names.items())) for alias, names in sorted(tree.items())}

    def get_cbs_dict(self, **kwargs) -> dict:
        return self.get_var_dict()

    def get_var_fields(self, **kwargs):
        return {}
