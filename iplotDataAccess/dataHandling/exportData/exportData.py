from uda_client_reader.UdaClientIterator import *
import numpy as np
import csv
import h5py
import os
import pyarrow as pa
import pyarrow.parquet as pq
import shutil
import tempfile
from datetime import datetime, timezone
from time import gmtime, strftime
import socket

from iplotDataAccess.dataHandling.exportData import resampling


##from influxdb_client import InfluxDBClient
##from influxdb_client.client.write_api import SYNCHRONOUS

# When set, exported timestamps are float seconds relative to this origin
# (ns since epoch) instead of absolute nanosecond counts.
relative_start_ns = None


class Info:
    pass


class result:
    pass


class connH:
    pass


class pqtCtnt:
    pass


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class DataExportError(Error):
    """Exception raised for errors occuring while exporting the data.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


def connectUDA(udaHost, port=3090):
    UdaConn = connH()
    UCR = UdaClientReaderPython(udaHost, port)
    if UCR.getErrorCode() != 0:
        UdaConn.UCR = None
        UdaConn.errd = "Could not connect to the UDA server"
        UdaConn.errc = -1
    else:
        UCR.resetAll()
        UdaConn.UCR = UCR
        UdaConn.errd = "OK"
        UdaConn.errc = 0
    return UdaConn


def createParquetFile(parquetFile):
    parquetContent = pqtCtnt
    time_type = pa.uint64() if relative_start_ns is None else pa.float64()
    parquetContent.ponvar_schema = pa.schema([
        ('timestamp', time_type),
        ('varname', pa.string()),
        ('description', pa.string()),
        ('unit', pa.string()),
        ('anal_value', pa.float64()),
        ('digit_value', pa.uint16())])
    parquetContent.writer = pq.ParquetWriter(parquetFile, parquetContent.ponvar_schema)
    return parquetContent


def getAndFillData(varn, res, vlist, dataW, conn, chunkS):
    query = "variable=%s,startTime=%s,endTime=%s,decSamples=-1" % (varn, res.s1, res.e1)
    CallbackFct = ChunkProcessingCallback()
    UdaClientIterator.readDataChunk(conn.UCR, CallbackFct, query, chunkS)


def extractAndGenerateParquet(varMap, conn, logfile, startT, endT, parquetFile, chunkS=50000,
                              progressCallback=None):
    res = result()
    res.errc = -1
    res.s1 = startT
    res.e1 = endT
    res.chunkSize = chunkS
    global currVarname
    global currVarDesc
    global dataWriter

    dataWriter = createParquetFile(parquetFile)

    for varn in varMap:
        if progressCallback is not None:
            progressCallback(varn)
        currVarname = varn
        currVarDesc = varMap[varn]
        getAndFillData(varn, res, varMap, dataWriter, conn, chunkS)

    dataWriter.writer.close()


def createH5file(h5file, varmap, start, end):
    dts = strftime("%Y-%m-%d %H:%M:%S", gmtime())
    h5f = h5py.File(h5file, 'w')
    h5f.attrs['server_hostname'] = socket.gethostname()
    h5f.attrs['logo'] = "exportUtility"
    h5f.attrs['data_model'] = "1.0"
    h5f.attrs['date_time'] = dts
    h5f.attrs['start_time'] = start
    h5f.attrs['end_time'] = end
    h5f.flush()
    dtD = np.dtype([('time', 'u8'), ('val', 'f8')])
    dtI = np.dtype([('time', 'u8'), ('val', 'i8')])
    droot = h5f.create_group("/root")
    for varn in varmap:
        dvar = droot.create_group(varn)
        dperiod = dvar.create_group("period_0")
        # dataD=dperiod.create_dataset("dataD",dtype=dtD,chunks=True,maxshape=(None))
        # dataI=dperiod.create_dataset("dataI",dtype=dtI,chunks=True,maxshape=(None))
    h5f.flush()
    return h5f


def extractAndGenerateH5(varMap, conn, logfile, startT, endT, h5File, chunkS=50000,
                         progressCallback=None):
    res = result()
    res.errc = -1
    res.s1 = startT
    res.e1 = endT
    res.chunkSize = chunkS

    global currVarname
    global currVarDesc
    global period_counter
    global dataWriter

    dataWriter = createH5file(h5File, varMap, res.s1, res.e1)

    for varn in varMap:
        if progressCallback is not None:
            progressCallback(varn)
        currVarname = varn
        currVarDesc = varMap[varn]
        period_counter = 0
        getAndFillData(varn, res, varMap, dataWriter, conn, chunkS)

    dataWriter.close()


class ChunkProcessingCallback(UdaClientCallback):
    def ProcessDataBlock(self, reader, handle, firstChunkSample):
        global currVarname
        global currVarDesc
        global dataWriter
        global file_format
        global period_counter
        time_type = 'u8' if relative_start_ns is None else 'f8'
        dtD = np.dtype([('time', time_type), ('value', 'f8')])
        dtF = np.dtype([('time', time_type), ('value', 'f4')])
        dtI = np.dtype([('time', time_type), ('value', 'i8')])
        currlen = 0
        dset = None
        yunits = reader.getUnitsY(handle)
        ytype = reader.getFetchedType(handle)
        timeV = reader.getTimeStampsAsLong(handle)
        if timeV is not None and relative_start_ns is not None:
            # Subtract in int64 before dividing so no precision is lost.
            timeV = (np.asarray(timeV, dtype=np.int64) - relative_start_ns) / 1e9
        currlen = len(timeV)

        if ytype == RAW_TYPE_DOUBLE:
            var_ana = reader.getDataAsDouble(handle)
            var_dig = np.full(currlen, 0, dtype=np.uint16)
            data_val = np.zeros(currlen, dtype=dtD)
            data_val['time'] = timeV
            data_val['value'] = var_ana
        elif ytype == RAW_TYPE_FLOAT:
            var_dig = reader.getDataAsFloat(handle)
            var_ana = np.full(currlen, 0, dtype=np.uint16)
            data_val = np.zeros(currlen, dtype=dtF)
            data_val['time'] = timeV
            data_val['value'] = var_dig
        else:
            var_dig = reader.getDataAsLong(handle)
            var_ana = np.full(currlen, 0, dtype=np.float64)
            data_val = np.zeros(currlen, dtype=dtI)
            data_val['time'] = timeV
            data_val['value'] = var_dig

        if timeV is not None:

            if file_format == "parquet":
                varN = np.full(currlen, currVarname)
                varD = np.full(currlen, currVarDesc)
                varU = np.full(currlen, yunits)
                batch = pa.RecordBatch.from_arrays([timeV, varN, varD, varU, var_ana, var_dig],
                                                   schema=dataWriter.ponvar_schema)
                table = pa.Table.from_batches([batch])
                dataWriter.writer.write_table(table)
            else:  # hdf5
                g = dataWriter["root/" + currVarname + "/period_0/"]
                if firstChunkSample == 0:

                    if file_format.startswith('hdf5'):
                        g.attrs['unit'] = yunits
                        dset = g.create_dataset("data", data=data_val, chunks=True, maxshape=(None,))

                else:
                    # print("before dset 1")
                    dset = g["data"]
                    # print("before dset 2")
                    dlen = dset.len()
                    # print("before dset 3")
                    dset.resize((dlen + currlen,))
                    # print("before dset 4")
                    dset[-currlen:] = data_val
                    # print("before dset 5")
                    dataWriter.flush()

        return 0


# Bucket value and column type per fetched type: analog signals average, and
# integer signals keep the last sample of the interval, whose mean would be
# meaningless for states or counters.
_RESAMPLE_KIND = {
    RAW_TYPE_DOUBLE: ('f8', True),
    RAW_TYPE_FLOAT: ('f4', True),
}

_TIME_STRIPE = 1_000_000


def _resampled_time_column(grid_start, period, index_from, index_to):
    times = resampling.grid_times(grid_start, period, index_from, index_to)
    if relative_start_ns is None:
        return times
    # Relative resampled times count from the grid origin, so the first grid
    # point is exactly 0.0 even when the raw window start carried nanoseconds.
    return (times.astype(np.int64) - grid_start) / 1e9


def _iso_utc(t_ns):
    return datetime.fromtimestamp(t_ns / 1e9, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')


class _ResampledParquetWriter:
    """One row per grid point: a time column plus one column per variable.

    Parquet writes every column of a row group together while variables are
    exported one at a time, so each finished column lands in a memory-mapped
    scratch file and the table is assembled in stripes on close.
    """

    def __init__(self, parquet_file, grid):
        self.grid = grid
        self.file = parquet_file
        self.columns = {}  # varname -> (memmap, target dtype)
        self.tmpdir = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(parquet_file)))

    def add_variable(self, varn, dtype, unit):
        path = os.path.join(self.tmpdir, f"col{len(self.columns)}.npy")
        column = np.lib.format.open_memmap(path, mode='w+', dtype=np.float64,
                                           shape=(self.grid[2],))
        self.columns[varn] = (column, dtype, unit)
        return column

    def close(self):
        grid_start, period, count = self.grid
        time_type = pa.uint64() if relative_start_ns is None else pa.float64()
        fields = [pa.field('timestamp', time_type)]
        fields += [pa.field(varn, pa.from_numpy_dtype(np.dtype(dtype)),
                            metadata={'unit': unit or ''})
                   for varn, (column, dtype, unit) in self.columns.items()]
        schema = pa.schema(fields)
        writer = pq.ParquetWriter(self.file, schema)
        try:
            for i in range(0, count, _TIME_STRIPE):
                j = min(i + _TIME_STRIPE, count)
                arrays = [pa.array(_resampled_time_column(grid_start, period, i, j))]
                arrays += [pa.array(column[i:j].astype(dtype))
                           for varn, (column, dtype, unit) in self.columns.items()]
                writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
        finally:
            writer.close()
            self.columns.clear()
            shutil.rmtree(self.tmpdir, ignore_errors=True)


class _ResampledH5Writer:
    """A time dataset plus one value-only dataset per variable under /root."""

    def __init__(self, h5file, grid, startT, endT, freq_hz):
        self.grid = grid
        self.h5f = h5py.File(h5file, 'w')
        self.h5f.attrs['server_hostname'] = socket.gethostname()
        self.h5f.attrs['logo'] = "exportUtility"
        self.h5f.attrs['data_model'] = "1.0"
        self.h5f.attrs['date_time'] = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        self.h5f.attrs['start_time'] = startT
        self.h5f.attrs['end_time'] = endT
        self.h5f.attrs['sampling_frequency_hz'] = freq_hz
        self.root = self.h5f.create_group("/root")
        grid_start, period, count = grid
        time_dset = self.root.create_dataset(
            "time", shape=(count,),
            dtype='u8' if relative_start_ns is None else 'f8')
        time_dset.attrs['unit'] = 'ns' if relative_start_ns is None else 's'
        for i in range(0, count, _TIME_STRIPE):
            j = min(i + _TIME_STRIPE, count)
            time_dset[i:j] = _resampled_time_column(grid_start, period, i, j)
        self.datasets = {}

    def add_variable(self, varn, dtype, unit):
        dset = self.root.create_dataset(varn, shape=(self.grid[2],), dtype=dtype)
        dset.attrs['unit'] = unit
        self.datasets[varn] = dset
        return _H5ColumnSink(dset, np.dtype(dtype))

    def close(self):
        self.h5f.close()


class _H5ColumnSink:
    def __init__(self, dset, dtype):
        self.dset = dset
        self.dtype = dtype

    def __setitem__(self, key, values):
        self.dset[key] = values.astype(self.dtype)


class _LastValueCallback(UdaClientCallback):
    """Captures the single sample of a last-value look-back reply."""

    def __init__(self):
        self.value = None
        self.ytype = None
        self.unit = None

    def ProcessDataBlock(self, reader, handle, firstChunkSample):
        timeV = reader.getTimeStampsAsLong(handle)
        if timeV is None or len(timeV) == 0:
            return 0
        self.ytype = reader.getFetchedType(handle)
        self.unit = reader.getUnitsY(handle)
        if self.ytype == RAW_TYPE_DOUBLE:
            self.value = float(reader.getDataAsDouble(handle)[-1])
        elif self.ytype == RAW_TYPE_FLOAT:
            self.value = float(reader.getDataAsFloat(handle)[-1])
        else:
            self.value = float(reader.getDataAsLong(handle)[-1])
        return 0


def _last_value_before(conn, varn, startT):
    """Last archived sample before the window, to seed the leading intervals.

    Asks the server for a single last-decimated sample over [0, startT), which
    is cheap however far back it lies. Any failure just means no seed.
    """
    query = "variable=%s,startTime=0,endTime=%s,decSamples=1,decType=last" % (varn, startT)
    callback = _LastValueCallback()
    try:
        UdaClientIterator.readDataChunk(conn.UCR, callback, query, 16)
    except Exception:
        return None
    if callback.value is None:
        return None
    return callback


class _ResampleChunkCallback(UdaClientCallback):
    """Folds each incoming chunk of one variable into the grid buckets."""

    def __init__(self, varn, grid, writer, seed):
        self.varn = varn
        self.grid = grid
        self.writer = writer
        self.seed = seed
        self.acc = None

    def ProcessDataBlock(self, reader, handle, firstChunkSample):
        timeV = reader.getTimeStampsAsLong(handle)
        if timeV is None or len(timeV) == 0:
            return 0
        ytype = reader.getFetchedType(handle)
        if ytype == RAW_TYPE_DOUBLE:
            values = reader.getDataAsDouble(handle)
        elif ytype == RAW_TYPE_FLOAT:
            values = reader.getDataAsFloat(handle)
        else:
            values = reader.getDataAsLong(handle)
        grid_start, period, count = self.grid
        idx = (np.asarray(timeV, dtype=np.int64) - grid_start) // period
        if self.acc is None:
            # Create the column with the first in-range sample; a variable
            # whose reply never lands on the grid must not leave an empty one.
            if not ((idx >= 0) & (idx < count)).any():
                return 0
            dtype, average = _RESAMPLE_KIND.get(ytype, ('i8', False))
            sink = self.writer.add_variable(self.varn, dtype, reader.getUnitsY(handle))
            seed_value = self.seed.value if self.seed is not None else None

            def store(index, vals, _sink=sink):
                _sink[index:index + len(vals)] = vals

            self.acc = resampling.BucketAccumulator(count, average, store,
                                                    seed=seed_value)
        self.acc.add(idx, values)
        return 0


def _finalize_resampled(varn, callback, writer, grid, rlog):
    grid_start, period, count = grid

    def span(index_from, index_to):
        return (f"{_iso_utc(grid_start + index_from * period)} to "
                f"{_iso_utc(grid_start + index_to * period)}")

    acc = callback.acc
    if acc is not None:
        acc.finish()
        rlog.write(f"{varn}: {acc.samples} samples into {count} intervals\n")
        if acc.no_seed_lead:
            rlog.write(f"{varn}: no earlier sample; first value used for the "
                       f"{acc.no_seed_lead} leading intervals\n")
        for index_from, index_to in acc.filled_runs:
            rlog.write(f"{varn}: no data {span(index_from, index_to)} "
                       f"({index_to - index_from} intervals, previous value repeated)\n")
        return
    seed = callback.seed
    if seed is not None:
        # Nothing in the window at all: the whole column repeats the last
        # value archived before it.
        dtype, _ = _RESAMPLE_KIND.get(seed.ytype, ('i8', False))
        sink = writer.add_variable(varn, dtype, seed.unit)
        for i in range(0, count, _TIME_STRIPE):
            j = min(i + _TIME_STRIPE, count)
            sink[i:j] = np.full(j - i, seed.value)
        rlog.write(f"{varn}: no data in the window; value before it repeated "
                   f"across all {count} intervals\n")
    else:
        rlog.write(f"{varn}: skipped, no data in the window and none before it\n")


def extractAndGenerateResampled(varMap, conn, startT, endT, outFile, freq_hz, chunkS,
                                progressCallback=None):
    grid = resampling.build_grid(startT, endT, freq_hz)
    if file_format == 'parquet':
        writer = _ResampledParquetWriter(outFile, grid)
    else:
        writer = _ResampledH5Writer(outFile, grid, startT, endT, freq_hz)
    with open(f"{outFile}.resampling.log", 'wt') as rlog:
        rlog.write(f"Resampled export at {freq_hz} Hz: {grid[2]} intervals of "
                   f"{grid[1]} ns from {_iso_utc(grid[0])}\n")
        for varn in varMap:
            if progressCallback is not None:
                progressCallback(varn)
            seed = _last_value_before(conn, varn, startT)
            callback = _ResampleChunkCallback(varn, grid, writer, seed)
            query = "variable=%s,startTime=%s,endTime=%s,decSamples=-1" % (varn, startT, endT)
            UdaClientIterator.readDataChunk(conn.UCR, callback, query, chunkS)
            _finalize_resampled(varn, callback, writer, grid, rlog)
    writer.close()


def generateData(logfile, conn, csvfile, formatType, startTime, endTime, outputFolder, chunkS=100000,
                 progressCallback=None, relativeTime=False, resampleFreq=None):
    """`progressCallback`, if given, is invoked with the variable name as each variable starts exporting.

    With `relativeTime`, timestamps are written as float seconds relative to
    `startTime` instead of absolute nanosecond counts.

    With `resampleFreq` (Hz), every variable is resampled onto the common time
    grid spanning the window at that frequency and the output is pivoted: one
    time column/dataset plus one column/dataset per variable. Intervals with
    data hold the average (integer signals keep their last sample), empty
    intervals repeat the previous value, and the affected ranges are listed in
    a `.resampling.log` file next to the output. Relative timestamps then
    count from the grid origin (the window start floored to the second)."""
    global file_format
    global relative_start_ns
    try:
        relative_start_ns = int(startTime) if relativeTime else None
        varMap = readcsvFile(csvfile, logfile)
        file_format = formatType.strip()
        ###csv variable with description
        if resampleFreq:
            extractAndGenerateResampled(varMap, conn, startTime, endTime, outputFolder,
                                        int(resampleFreq), chunkS, progressCallback)
        elif formatType == 'parquet':
            ret = extractAndGenerateParquet(varMap, conn, logfile, startTime, endTime, outputFolder, chunkS,
                                            progressCallback)
        else:
            ret = extractAndGenerateH5(varMap, conn, logfile, startTime, endTime, outputFolder, chunkS,
                                       progressCallback)
        return True, ""
    except DataExportError as dee:
        return False, dee.message

    except Exception as exc:
        return False, repr(exc)


def readcsvFile(pathtocsv, logfile):
    csvheader = ['variable name', 'description']
    varMap = {}
    try:

        with open(pathtocsv, 'rt') as csvfile:
            variableReader = csv.reader(csvfile, delimiter=",")
            for row in variableReader:
                if (len(row) == 2):
                    varMap[row[0]] = row[1]
                elif logfile is not None:
                    logfile.write("cannot parse row " + row[0] + " : skipping")
    except FileNotFoundError:
        raise DataExportError("CSV_Error", "CSV file not found")

    except Exception as exc:
        raise DataExportError("CSV_Error", "Error while parsing the csv file" + repr(exc))

    return varMap


def closeUDA(iRet):
    del iRet.UCR
