import os
from concurrent.futures.process import ProcessPoolExecutor

import numpy as np
# from IPython.utils.tz import utcfromtimestamp
from iplotlib.proc.data import hash_code

"""
A simple wrapper providing UDA data cache.
For now we should only assume that data ranges are given by timestamps
"""

#TODO: Rename to accessHelper
class AccessHelper:

    async_enabled = False

    da = None
    query_no = 0
    use_cache = False
    zoom_support = True
    num_samples = 1000
    key_params = []  # only this param keys will be used when creating cache key
    cache = {}

    pool = ProcessPoolExecutor()  # Multiprocess uses separate GIL for every forked process
    # pool = ThreadPoolExecutor()

    # Formats values as relative/absolute timestapms for UDA request or pretty print string

    uda_ts = lambda self,signal,value : str(np.datetime64(value, 'ns')) if not (signal.ts_relative or value is None) else value
    str_ts = lambda self,signal,value : np.datetime64(value, 'ns') if not (signal.ts_relative or value is None) else value

    @staticmethod
    def get():
        return AccessHelper()

    def get_data(self, signal):
        print("[UDA {}] Get data: {} ts_start={} ts_end={} pulsenb={} nbsamples={}"
              .format(self.query_no, signal.varname, self.str_ts(signal, signal.ts_start), self.str_ts(signal, signal.ts_end),
                      signal.pulsenb, signal.dec_samples or self.num_samples))
        self.query_no += 1

        if self.async_enabled:
            return self.pool.submit(self._fetch_data, signal)
        else:
            return self._fetch_data(signal)

    def _fetch_data(self, signal):
        common_params = dict(dataSName=signal.datasource, varname=signal.varname, nbp=signal.dec_samples or AccessHelper.num_samples)
        np_nvl = lambda arr : np.empty(0) if arr is None else np.array(arr)

        if (signal.ts_start is not None and signal.ts_end is not None) or signal.pulsenb is not None:
            data_params = dict(pulse=signal.pulsenb, tsS=self.uda_ts(signal, signal.ts_start), tsE=self.uda_ts(signal, signal.ts_end),
                               tsFormat="relative" if signal.ts_relative else "absolute")

            if signal.envelope:
                (min, max) = AccessHelper.da.getEnvelope(**common_params, **data_params)

                xdata = np_nvl(min.xdata if min else None) if signal.ts_relative else np_nvl(min.xdata if min else None)


                return [np_nvl(xdata), np_nvl(min.ydata if min else None), np_nvl(max.ydata if max else None)], [min.xunit if min else None, min.yunit if min else None]
            else:
                raw = AccessHelper.da.getData(**common_params, **data_params)

                xdata = np_nvl(raw.xdata) if signal.ts_relative else np_nvl(raw.xdata).astype('int')
                print("\tUDA samples", len(xdata))
                return [xdata, np_nvl(raw.ydata)], [raw.xunit, raw.yunit]
        else:
            # print("RETURNING EMPTY DATA SET", type(np.empty(1)), type(np.empty(1).astype('datetime64[ns]')))
            return [np.empty(0) if signal.ts_relative else np.empty(0).astype('int'),np.empty(0).astype('double')], []

class CachingAccessHelper(AccessHelper):

    KEY_PROP_NAMES = ["varname", "ts_start", "ts_end", "pulsenb", "dec_samples", "datasource", "envelope", "ts_relative"]
    CACHE_PREFIX = "/tmp/cache_"

    def __init__(self,enable_cache=False):
        self.enable_cache = enable_cache

    @staticmethod
    def get():
        return CachingAccessHelper()

    def _fetch_data(self, signal):

        if self.enable_cache:
            cached = self._cache_fetch(signal)
            if cached is not None:
                print("HIT",self._cache_filename(signal))
                return cached
            else:
                print("MISS",self._cache_filename(signal))
                return self._cache_put(signal, super()._fetch_data(signal))
        else:
            return super()._fetch_data(signal)

    def _cache_filename(self, signal):
        return "{}{}.npy".format(self.CACHE_PREFIX,hash_code(signal, self.KEY_PROP_NAMES))

    def _cache_fetch(self, signal):
        filename = self._cache_filename(signal)
        return np.load(filename, allow_pickle=True) if os.path.isfile(filename) else None

    def _cache_put(self, signal, data):
        filename = self._cache_filename(signal)
        np.save(filename,data, allow_pickle=True)
        return data