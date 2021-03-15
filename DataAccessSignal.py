from dataclasses import dataclass
import numpy as np
from iplotlib.access.AccessHelper import CachingAccessHelper
from iplotlib.core.Signal import ArraySignal
from iplotlib.proc.data import hash_code


@dataclass
class DataAccessSignal(ArraySignal):

    varname: str = None
    pulsenb: int = None
    ts_start: int = None
    ts_end: int = None
    dec_samples: int = None
    ts_relative: bool = False
    datasource: str = None
    envelope: bool = False

    def __post_init__(self):
        super().__post_init__()
        self.units = []
        self.data = []
        if self.ts_start is not None:
            self.ts_start = np.datetime64(self.ts_start, 'ns').astype('int').item() if isinstance(self.ts_start, str) else self.ts_start

        if self.ts_end is not None:
            self.ts_end = np.datetime64(self.ts_end, 'ns').astype('int').item() if isinstance(self.ts_end, str) else self.ts_end

        if self.title is None:
            self.title = self.varname or ''

        if self.pulsenb is not None:
            self.title += ':'+str(self.pulsenb)

        self.data_hash = None
        self.data = None

    def __str__(self):
        return "{}({}{}{}{}{})".format(self.__class__.__name__, self.varname,
                                     ', pulsenb='+str(self.pulsenb) if self.pulsenb is not None else "",
                                     ', ts_start='+str(np.datetime64(self.ts_start, 'ns')) if not(self.ts_start is None or self.ts_relative) else "",
                                     ', ts_end='+str(np.datetime64(self.ts_end, 'ns')) if not (self.ts_end is None or self.ts_relative) else "",
                                     ', dec_samples='+str(self.dec_samples))

    def get_data(self):
        cur_hash = self.calculate_data_hash()
        if self.data_hash != cur_hash:
            self.data_hash = cur_hash
            uda_record = CachingAccessHelper.get().get_data(self)
            self.units = uda_record[1]
            self.data = uda_record[0]

        return self.data

    def calculate_data_hash(self):
        # This hashcode is used to determine if we should perform new UDA request or not
        return hash_code(self, ["ts_start", "ts_end", "dec_samples","pulsenb"])

    def update_ranges(self, ranges):
        self.ts_start = ranges[0][0].astype('int').item() if isinstance(ranges[0][0], np.generic) else ranges[0][0]
        self.ts_end = ranges[0][1].astype('int').item() if isinstance(ranges[0][0], np.generic) else ranges[0][0]

    def pick(self, sample):
        if self.data is not None and sample is not None and len(self.data) > 0 and len(self.data[0]) > 0:
            lengths = [len(self.data[i]) if self.data[i] is not None else None for i in range(len(self.data))]

            if not all(e == lengths[0] for e in lengths):
                return None

            needle = sample.astype(self.data[0][0].dtype.name)

            if needle is not None:
                index = np.searchsorted(self.data[0], needle)

                if index == len(self.data[0]):
                    index = len(self.data[0])-1

                if index > 0 and abs(self.data[0][index-1]-needle) < abs(self.data[0][index]-needle):
                    return [self.data[i][index-1] for i in range(len(self.data))]

                return [self.data[i][index] for i in range(len(self.data))]

        return None