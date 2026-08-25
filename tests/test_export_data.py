"""Unit tests for the export writers' time column (absolute vs relative).

ChunkProcessingCallback is driven directly with a stub reader, so no UDA
server or network is needed; only the parquet/HDF5 writing is exercised.
"""
import os
import tempfile
import unittest

import h5py
import numpy as np
import pyarrow.parquet as pq

try:
    from iplotDataAccess.dataHandling.exportData import exportData
    uda_imported = True
except ImportError:
    uda_imported = False

BASE_NS = 1_641_760_133_123_456_789
TIMES_NS = np.array([BASE_NS, BASE_NS + 100_000_000, BASE_NS + 250_000_000],
                    dtype=np.uint64)
VALUES = np.array([1.0, 2.0, 3.0])


class _StubReader:
    def getUnitsY(self, handle):
        return "V"

    def getFetchedType(self, handle):
        return exportData.RAW_TYPE_DOUBLE

    def getTimeStampsAsLong(self, handle):
        return TIMES_NS

    def getDataAsDouble(self, handle):
        return VALUES


@unittest.skipUnless(uda_imported, "uda_client_reader not available for CI tests")
class ExportTimeColumnTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(self._reset_globals)

    @staticmethod
    def _reset_globals():
        exportData.relative_start_ns = None

    def _write_chunk(self, file_format, relative_start_ns, path):
        exportData.file_format = file_format
        exportData.relative_start_ns = relative_start_ns
        exportData.currVarname = "VAR-A"
        exportData.currVarDesc = "desc"
        if file_format == "parquet":
            exportData.dataWriter = exportData.createParquetFile(path)
        else:
            exportData.dataWriter = exportData.createH5file(
                path, {"VAR-A": "desc"}, str(BASE_NS), str(TIMES_NS[-1]))
        callback = exportData.ChunkProcessingCallback()
        callback.ProcessDataBlock(_StubReader(), 0, 0)
        if file_format == "parquet":
            exportData.dataWriter.writer.close()
        else:
            exportData.dataWriter.close()

    def test_parquet_absolute_keeps_ns_uint64(self):
        path = os.path.join(self.tmpdir.name, "abs.parquet")
        self._write_chunk("parquet", None, path)
        table = pq.read_table(path)
        self.assertEqual(table.schema.field('timestamp').type, 'uint64')
        np.testing.assert_array_equal(table['timestamp'].to_numpy(), TIMES_NS)

    def test_parquet_relative_writes_float_seconds(self):
        path = os.path.join(self.tmpdir.name, "rel.parquet")
        self._write_chunk("parquet", BASE_NS, path)
        table = pq.read_table(path)
        self.assertEqual(table.schema.field('timestamp').type, 'double')
        np.testing.assert_allclose(table['timestamp'].to_numpy(),
                                   [0.0, 0.1, 0.25], atol=1e-12)
        np.testing.assert_array_equal(table['anal_value'].to_numpy(), VALUES)

    def test_hdf5_absolute_keeps_ns_uint64(self):
        path = os.path.join(self.tmpdir.name, "abs.hdf5")
        self._write_chunk("hdf5", None, path)
        with h5py.File(path, 'r') as h5f:
            data = h5f["root/VAR-A/period_0/data"][()]
        self.assertEqual(data.dtype['time'], np.dtype('u8'))
        np.testing.assert_array_equal(data['time'], TIMES_NS)

    def test_hdf5_relative_writes_float_seconds(self):
        path = os.path.join(self.tmpdir.name, "rel.hdf5")
        self._write_chunk("hdf5", BASE_NS, path)
        with h5py.File(path, 'r') as h5f:
            data = h5f["root/VAR-A/period_0/data"][()]
        self.assertEqual(data.dtype['time'], np.dtype('f8'))
        np.testing.assert_allclose(data['time'], [0.0, 0.1, 0.25], atol=1e-12)
        np.testing.assert_array_equal(data['value'], VALUES)

    def test_generate_data_defaults_to_absolute(self):
        # relativeTime must stay opt-in so existing callers are unaffected.
        import inspect
        sig = inspect.signature(exportData.generateData)
        self.assertIn('relativeTime', sig.parameters)
        self.assertIs(sig.parameters['relativeTime'].default, False)


if __name__ == "__main__":
    unittest.main()
