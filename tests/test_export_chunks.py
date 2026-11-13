"""The export reads its data in chunks in any thread: the UDA clients that can cancel a read set a SIGINT handler around
each one in UdaClientIterator.readDataChunk, which fails outside the main thread, and MINT exports in a worker thread."""
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
import pyarrow.parquet as pq

try:
    from iplotDataAccess.dataHandling.exportData import exportData
    uda_imported = True
except ImportError:
    uda_imported = False

T0 = 1_648_771_200_000_000_000


class _Reader:
    """Gives the samples of a variable in chunks, as the UDA reader does with ddContinueFrom and ddSamples."""

    def __init__(self, samples: int):
        self.samples = samples
        self.requests = []
        self._chunks = {}

    def fetchData(self, request):
        self.requests.append(request)
        fields = dict(part.split('=', 1) for part in request.split(',') if '=' in part)
        start, size = int(fields['ddContinueFrom']), int(fields['ddSamples'])
        handle = len(self._chunks)
        self._chunks[handle] = (start, min(start + size, self.samples))
        return handle

    def getSamplesNumber(self, handle):
        start, end = self._chunks[handle]
        return end - start

    def isLastChunk(self, handle):
        return self._chunks[handle][1] >= self.samples

    def releaseData(self, handle):
        pass

    def getUnitsY(self, handle):
        return "V"

    def getFetchedType(self, handle):
        return exportData.RAW_TYPE_DOUBLE

    def getTimeStampsAsLong(self, handle):
        start, end = self._chunks[handle]
        return np.arange(T0 + start, T0 + end, dtype=np.uint64)

    def getDataAsDouble(self, handle):
        start, end = self._chunks[handle]
        return np.arange(start, end, dtype=float)


def _client_that_reads_only_in_the_main_thread(*args, **kwargs):
    raise ValueError("signal only works in main thread of the main interpreter")


@unittest.skipUnless(uda_imported, "uda_client_reader package required")
class ExportChunksTest(unittest.TestCase):
    def test_the_export_reads_every_chunk_in_a_worker_thread(self):
        reader = _Reader(25)
        conn = exportData.connH()
        conn.UCR = reader
        target = os.path.join(tempfile.mkdtemp(), 'out.parquet')
        exportData.relative_start_ns = None
        exportData.file_format = 'parquet'
        outcome = {}

        def export():
            try:
                exportData.extractAndGenerateParquet({"VAR": "about"}, conn, None, T0, T0 + 25, target, chunkS=10)
            except Exception as e:
                outcome['error'] = e

        with patch.object(exportData.UdaClientIterator, 'readDataChunk', _client_that_reads_only_in_the_main_thread):
            thread = threading.Thread(target=export)
            thread.start()
            thread.join(30)

        self.assertNotIn('error', outcome)
        table = pq.read_table(target).to_pandas()
        self.assertEqual(table['anal_value'].tolist(), list(range(25)))
        self.assertEqual([r.split('ddContinueFrom=')[1] for r in reader.requests],
                         ['0,ddSamples=10', '10,ddSamples=10', '20,ddSamples=10'])
        os.remove(target)

    def test_a_read_that_fails_ends_the_chunks(self):
        reader = _Reader(25)
        reader.fetchData = lambda request: -1
        self.assertEqual(exportData.readDataChunks(reader, None, "variable=VAR", 10), -1)


if __name__ == '__main__':
    unittest.main()
