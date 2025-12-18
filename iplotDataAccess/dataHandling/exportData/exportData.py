from uda_client_reader.UdaClientIterator import *
import numpy as np
import csv
import h5py
import pyarrow as pa
import pyarrow.parquet as pq
from time import gmtime, strftime
import socket
##from influxdb_client import InfluxDBClient
##from influxdb_client.client.write_api import SYNCHRONOUS


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
    parquetContent.ponvar_schema = pa.schema([
        ('timestamp', pa.uint64()),
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


def extractAndGenerateParquet(varMap, conn, logfile, startT, endT, parquetFile, chunkS=50000):
    res = result()
    res.errc = -1
    res.s1 = conn.UCR.convertTimeISOToNs(startT)
    res.e1 = conn.UCR.convertTimeISOToNs(endT)
    res.chunkSize = chunkS
    global currVarname
    global currVarDesc
    global dataWriter

    dataWriter = createParquetFile(parquetFile)

    for varn in varMap:
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


def extractAndGenerateH5(varMap, conn, logfile, startT, endT, h5File, chunkS=50000):
    res = result()
    res.errc = -1
    res.s1 = conn.UCR.convertTimeISOToNs(startT)
    res.e1 = conn.UCR.convertTimeISOToNs(endT)
    res.chunkSize = chunkS

    global currVarname
    global currVarDesc
    global period_counter
    global dataWriter

    dataWriter = createH5file(h5File, varMap, res.s1, res.e1)

    for varn in varMap:
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
        dtD = np.dtype([('time', 'u8'), ('value', 'f8')])
        dtI = np.dtype([('time', 'u8'), ('value', 'i8')])
        currlen = 0
        dset = None
        yunits = reader.getUnitsY(handle)
        ytype = reader.getFetchedType(handle)
        timeV = reader.getTimeStampsAsLong(handle)
        currlen = len(timeV)
        # print(" processing function and varname="+currVarname+" first "+str(firstChunkSample))

        if ytype == RAW_TYPE_DOUBLE:
            var_ana = reader.getDataAsDouble(handle)
            var_dig = np.full(currlen, 0, dtype=np.uint16)
            data_val = np.zeros(currlen, dtype=dtD)
            data_val['time'] = timeV
            data_val['value'] = var_ana
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
                        # print(" time "+str(data_val['time'][0])+ " value "+str(data_val['value'][0]))
                        if ytype == RAW_TYPE_DOUBLE:

                            dset = g.create_dataset("data", data=data_val, chunks=True, maxshape=(None,))
                        else:

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


def generateData(logfile, conn, csvfile, formatType, startTime, endTime, outputFolder, chunkS=100000):
    global file_format
    try:
        varMap = readcsvFile(csvfile, logfile)
        file_format = formatType.strip()
        ###csv variable with description
        if formatType == 'parquet':
            parquetFile = outputFolder + "/data.parquet"
            ret = extractAndGenerateParquet(varMap, conn, logfile, startTime, endTime, parquetFile, chunkS)
        else:
            h5File = outputFolder + "/data.h5"
            ret = extractAndGenerateH5(varMap, conn, logfile, startTime, endTime, h5File, chunkS)
        return True
    except DataExportError as dee:
        print("Failed to export data :" + dee.message)
        return False

    except Exception as exc:
        print("Failed to export data :" + repr(exc))
        return False


def readcsvFile(pathtocsv, logfile):
    csvheader = ['variable name', 'description']
    varMap = {}
    try:

        with open(pathtocsv, 'rt') as csvfile:
            variableReader = csv.reader(csvfile, delimiter=",")
            for row in variableReader:
                if (len(row) == 2):
                    varMap[row[0]] = row[1]
                else:
                    logfile.write("cannot parse row " + row[0] + " : skipping")
    except FileNotFoundError:
        raise DataExportError("CSV_Error", "CSV file not found")

    except Exception as exc:
        raise DataExportError("CSV_Error", "Error while parsing the csv file" + repr(exc))

    return varMap


def closeUDA(iRet):
    del iRet.UCR
