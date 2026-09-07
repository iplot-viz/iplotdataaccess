"""Cross-checks the resampled HDF5 export against the independent verifier.

verify_downsample rebuilds the block averages straight from a native export,
so the resampled writer is validated against a second implementation of the
same model, files included. Sample values are multiples of 0.25: their sums
are exact in floating point, which keeps the comparison bit-exact even for
buckets split across chunks, where the two implementations accumulate in a
different order.
"""
import io
import os
import tempfile
import unittest

import numpy as np

try:
    import h5py
    from iplotDataAccess.dataHandling.exportData import exportData
    uda_imported = True
except ImportError:
    uda_imported = False

from verify_downsample import block_average, fill_gaps, read_downsampled, read_native

BASE_NS = 1_641_760_133_000_000_000
NS = 1_000_000_000


def _write_native_h5(path, varn, times, values):
    """Native-layout file as the plain exporter writes it."""
    dt = np.dtype([('time', 'u8'), ('value', 'f8')])
    data = np.zeros(len(times), dtype=dt)
    data['time'] = times
    data['value'] = values
    with h5py.File(path, 'w') as h5f:
        g = h5f.create_group(f"/root/{varn}/period_0")
        g.create_dataset("data", data=data, chunks=True, maxshape=(None,))


@unittest.skipUnless(uda_imported, "uda_client_reader not available for CI tests")
class DownsampleVerifierTest(unittest.TestCase):
    """Drives the resampled writer and verifies it with verify_downsample."""

    GRID = (BASE_NS, NS, 11)  # 10 s at 1 Hz

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(self._reset_globals)
        exportData.file_format = "hdf5"

    @staticmethod
    def _reset_globals():
        exportData.relative_start_ns = None

    def _export_resampled(self, varn, chunks, seed=None):
        path = os.path.join(self.tmpdir.name, "downsampled.hdf5")
        writer = exportData._ResampledH5Writer(path, self.GRID, str(BASE_NS),
                                               str(BASE_NS + 10 * NS), 1)
        callback = exportData._ResampleChunkCallback(varn, self.GRID, writer, seed)
        reader = _ChunkedStubReader(chunks)
        for i in range(len(chunks)):
            reader.current = i
            callback.ProcessDataBlock(reader, 0, 0)
        exportData._finalize_resampled(varn, callback, writer, self.GRID, io.StringIO())
        writer.close()
        return path

    def _native_samples(self):
        # 4 Hz signal with a 3-second gap and a bucket split across chunks:
        # values are multiples of 0.25 so any summation order is exact.
        times, values = [], []
        for second in (0, 1, 2, 6, 7, 8, 9):
            for k in range(4):
                times.append(BASE_NS + second * NS + k * 250_000_000)
                values.append(second + k * 0.25)
        return np.array(times, dtype=np.uint64), np.array(values)

    def test_resampled_file_matches_the_independent_rebuild(self):
        times, values = self._native_samples()
        native_path = os.path.join(self.tmpdir.name, "native.hdf5")
        _write_native_h5(native_path, "VAR-A", times, values)

        # Split mid-second so bucket 1 spans both chunks.
        cut = 6
        ds_path = self._export_resampled(
            "VAR-A", [(times[:cut], values[:cut]), (times[cut:], values[cut:])])

        grid, ref = read_downsampled(ds_path)
        np.testing.assert_array_equal(
            grid, np.arange(self.GRID[2], dtype=np.int64) * NS + BASE_NS)
        t_nat, v_nat = read_native(native_path)["VAR-A"]
        mean, count, dropped = block_average(t_nat, v_nat, grid)
        rebuilt = fill_gaps(mean)

        self.assertEqual(dropped, 0)
        np.testing.assert_array_equal(rebuilt, ref["VAR-A"])

    def test_seed_only_changes_the_leading_gap(self):
        # The export seeds leading buckets with the value archived before the
        # window; the verifier back-fills them instead. Both must agree on
        # every bucket at or after the first sample.
        times, values = self._native_samples()
        shifted = times + np.uint64(2 * NS)  # first sample at second 2
        keep = shifted <= BASE_NS + 10 * NS
        shifted, values = shifted[keep], values[keep]

        seed = exportData._LastValueCallback()
        seed.value, seed.ytype, seed.unit = -1.5, exportData.RAW_TYPE_DOUBLE, "V"
        ds_path = self._export_resampled("VAR-A", [(shifted, values)], seed=seed)

        grid, ref = read_downsampled(ds_path)
        mean, count, _ = block_average(shifted.astype(np.int64), values, grid)
        rebuilt = fill_gaps(mean)

        first_real = int(np.argmax(count > 0))
        np.testing.assert_array_equal(rebuilt[first_real:], ref["VAR-A"][first_real:])
        np.testing.assert_array_equal(ref["VAR-A"][:first_real], -1.5)


class _ChunkedStubReader:
    def __init__(self, chunks):
        self.chunks = chunks
        self.current = 0

    def getUnitsY(self, handle):
        return "V"

    def getFetchedType(self, handle):
        return exportData.RAW_TYPE_DOUBLE

    def getTimeStampsAsLong(self, handle):
        return np.asarray(self.chunks[self.current][0], dtype=np.uint64)

    def getDataAsDouble(self, handle):
        return np.asarray(self.chunks[self.current][1])


if __name__ == "__main__":
    unittest.main()
