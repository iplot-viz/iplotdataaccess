"""Unit tests for the resampled export path.

The grid and bucket logic are pure numpy and run everywhere; the writer and
callback tests drive the export module with a stub reader, so no UDA server or
network is needed.
"""
import io
import os
import tempfile
import unittest

import numpy as np

from iplotDataAccess.dataHandling.exportData import resampling

try:
    import h5py
    import pyarrow.parquet as pq
    from iplotDataAccess.dataHandling.exportData import exportData
    uda_imported = True
except ImportError:
    uda_imported = False

NS = resampling.NS_PER_SECOND
BASE_NS = 1_641_760_133_000_000_000  # a whole second


class GridTests(unittest.TestCase):
    def test_periods_are_exact_for_all_supported_frequencies(self):
        for freq, period in [(1, 10 ** 9), (10, 10 ** 8), (100, 10 ** 7),
                             (1000, 10 ** 6), (10000, 10 ** 5)]:
            self.assertEqual(resampling.grid_period_ns(freq), period)

    def test_rejects_frequency_not_dividing_one_second(self):
        with self.assertRaises(ValueError):
            resampling.grid_period_ns(3)

    def test_window_endpoints_land_on_whole_seconds(self):
        # The start is floored and the end is ceiled, so the grid stays on
        # round timestamps while still covering the whole window.
        start, period, count = resampling.build_grid(BASE_NS + 123_456_789,
                                                     BASE_NS + 10 * NS + 987_654_321, 10)
        self.assertEqual(start, BASE_NS)
        self.assertEqual(period, 10 ** 8)
        self.assertEqual(count, 111)
        times = resampling.grid_times(start, period, 0, count)
        self.assertEqual(times[0], BASE_NS)
        self.assertEqual(times[-1], BASE_NS + 11 * NS)

    def test_round_window_keeps_its_exact_endpoints(self):
        start, period, count = resampling.build_grid(BASE_NS, BASE_NS + 10 * NS, 10)
        self.assertEqual((start, count), (BASE_NS, 101))
        self.assertEqual(start + (count - 1) * period, BASE_NS + 10 * NS)

    def test_sub_second_window_still_covers_its_samples(self):
        # A window shorter than a second must not leave its samples past the
        # last grid bucket.
        start, period, count = resampling.build_grid(BASE_NS + 500_000_000,
                                                     BASE_NS + 900_000_000, 10)
        self.assertEqual(start, BASE_NS)
        self.assertEqual(count, 11)
        idx = (BASE_NS + 850_000_000 - start) // period
        self.assertLess(idx, count)

    def test_ten_minutes_at_ten_khz(self):
        start, period, count = resampling.build_grid(BASE_NS, BASE_NS + 600 * NS, 10000)
        self.assertEqual(count, 6_000_001)
        self.assertEqual(start + (count - 1) * period, BASE_NS + 600 * NS)


class _Sink:
    """Collects emitted buckets and exposes them as one contiguous array."""

    def __init__(self, count):
        self.data = np.full(count, np.nan)
        self.calls = []

    def __call__(self, index, values):
        self.calls.append((index, len(values)))
        self.data[index:index + len(values)] = values


class BucketAccumulatorTests(unittest.TestCase):
    def _run(self, count, chunks, average=True, seed=None):
        sink = _Sink(count)
        acc = resampling.BucketAccumulator(count, average, sink, seed=seed)
        for idx, vals in chunks:
            acc.add(np.asarray(idx, dtype=np.int64), np.asarray(vals, dtype=float))
        completed = acc.finish()
        return acc, sink, completed

    def test_buckets_average_their_samples(self):
        acc, sink, _ = self._run(3, [([0, 0, 1, 2], [1.0, 3.0, 5.0, 7.0])])
        np.testing.assert_allclose(sink.data, [2.0, 5.0, 7.0])
        self.assertEqual(acc.filled_runs, [])

    def test_bucket_split_across_chunks_is_merged(self):
        # Bucket 1 receives samples from both chunks; its average must span them.
        acc, sink, _ = self._run(3, [([0, 1], [2.0, 10.0]),
                                     ([1, 1, 2], [20.0, 30.0, 4.0])])
        np.testing.assert_allclose(sink.data, [2.0, 20.0, 4.0])

    def test_empty_buckets_repeat_previous_value_and_are_tracked(self):
        acc, sink, _ = self._run(5, [([0, 4], [1.0, 9.0])])
        np.testing.assert_allclose(sink.data, [1.0, 1.0, 1.0, 1.0, 9.0])
        self.assertEqual(acc.filled_runs, [[1, 4]])

    def test_upsampling_repeats_between_sparse_samples(self):
        # A 1-in-10 data rate on the grid: nine repeats after every sample.
        idx = [0, 10]
        acc, sink, _ = self._run(20, [(idx, [1.0, 2.0])])
        np.testing.assert_allclose(sink.data[:11], [1.0] * 10 + [2.0])
        np.testing.assert_allclose(sink.data[11:], [2.0] * 9)

    def test_integer_mode_keeps_last_sample_of_bucket(self):
        acc, sink, _ = self._run(2, [([0, 0, 1], [1.0, 4.0, 2.0])], average=False)
        np.testing.assert_allclose(sink.data, [4.0, 2.0])

    def test_seed_fills_leading_buckets(self):
        acc, sink, _ = self._run(4, [([2, 3], [5.0, 6.0])], seed=1.5)
        np.testing.assert_allclose(sink.data, [1.5, 1.5, 5.0, 6.0])
        self.assertEqual(acc.filled_runs, [[0, 2]])
        self.assertEqual(acc.no_seed_lead, 0)

    def test_without_seed_leading_buckets_take_first_value(self):
        acc, sink, _ = self._run(4, [([2, 3], [5.0, 6.0])])
        np.testing.assert_allclose(sink.data, [5.0, 5.0, 5.0, 6.0])
        self.assertEqual(acc.no_seed_lead, 2)

    def test_trailing_buckets_carry_after_finish(self):
        acc, sink, completed = self._run(5, [([0], [3.0])])
        self.assertTrue(completed)
        np.testing.assert_allclose(sink.data, [3.0] * 5)
        self.assertEqual(acc.filled_runs, [[1, 5]])

    def test_no_data_and_no_seed_reports_incomplete(self):
        acc, sink, completed = self._run(3, [])
        self.assertFalse(completed)
        self.assertTrue(np.isnan(sink.data).all())

    def test_out_of_range_samples_are_dropped(self):
        acc, sink, _ = self._run(2, [([-1, 0, 1, 2], [9.0, 1.0, 2.0, 9.0])])
        np.testing.assert_allclose(sink.data, [1.0, 2.0])
        self.assertEqual(acc.samples, 2)


class _StubReader:
    """Feeds ProcessDataBlock with predefined (times, values) chunks."""

    def __init__(self, ytype, chunks, unit="V"):
        self.ytype = ytype
        self.chunks = chunks
        self.unit = unit
        self.current = 0

    def getUnitsY(self, handle):
        return self.unit

    def getFetchedType(self, handle):
        return self.ytype

    def getTimeStampsAsLong(self, handle):
        return np.asarray(self.chunks[self.current][0], dtype=np.uint64)

    def _values(self, handle):
        return np.asarray(self.chunks[self.current][1])

    getDataAsDouble = _values
    getDataAsFloat = _values
    getDataAsLong = _values


@unittest.skipUnless(uda_imported, "uda_client_reader not available for CI tests")
class ResampledExportTests(unittest.TestCase):
    GRID = (BASE_NS, 10 ** 8, 21)  # 2 s at 10 Hz

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(self._reset_globals)
        exportData.file_format = "parquet"

    @staticmethod
    def _reset_globals():
        exportData.relative_start_ns = None

    def _drive(self, writer, varn, reader, seed=None, rlog=None):
        callback = exportData._ResampleChunkCallback(varn, self.GRID, writer, seed)
        for i in range(len(reader.chunks)):
            reader.current = i
            callback.ProcessDataBlock(reader, 0, 0)
        exportData._finalize_resampled(varn, callback, writer, self.GRID,
                                       rlog if rlog is not None else io.StringIO())

    def test_parquet_is_pivoted_with_one_column_per_variable(self):
        path = os.path.join(self.tmpdir.name, "out.parquet")
        writer = exportData._ResampledParquetWriter(path, self.GRID)
        analog = _StubReader(exportData.RAW_TYPE_DOUBLE,
                             [([BASE_NS, BASE_NS + 5 * 10 ** 7], [1.0, 3.0]),
                              ([BASE_NS + 2 * 10 ** 9], [5.0])])
        state = _StubReader(exportData.RAW_TYPE_LONG,
                            [([BASE_NS, BASE_NS + 10 ** 9], [7, 8])], unit="")
        self._drive(writer, "VAR-A", analog)
        self._drive(writer, "STATE-B", state)
        writer.close()

        table = pq.read_table(path)
        self.assertEqual(table.column_names, ['timestamp', 'VAR-A', 'STATE-B'])
        self.assertEqual(table.schema.field('timestamp').type, 'uint64')
        self.assertEqual(table.schema.field('VAR-A').type, 'double')
        self.assertEqual(table.schema.field('STATE-B').type, 'int64')
        self.assertEqual(table.num_rows, 21)
        times = table['timestamp'].to_numpy()
        self.assertEqual(times[0], BASE_NS)
        self.assertEqual(times[-1], BASE_NS + 2 * 10 ** 9)
        var_a = table['VAR-A'].to_numpy()
        # Bucket 0 averages its two samples, the gap repeats it, the last
        # bucket holds the final sample.
        self.assertAlmostEqual(var_a[0], 2.0)
        np.testing.assert_allclose(var_a[1:20], 2.0)
        self.assertAlmostEqual(var_a[20], 5.0)
        state_b = table['STATE-B'].to_numpy()
        self.assertEqual(state_b[0], 7)
        self.assertEqual(state_b[10], 8)
        self.assertEqual(state_b[20], 8)

    def test_hdf5_has_time_and_one_value_dataset_per_variable(self):
        path = os.path.join(self.tmpdir.name, "out.hdf5")
        exportData.file_format = "hdf5"
        writer = exportData._ResampledH5Writer(path, self.GRID, str(BASE_NS),
                                               str(BASE_NS + 2 * NS), 10)
        analog = _StubReader(exportData.RAW_TYPE_FLOAT,
                             [([BASE_NS], [1.5])])
        self._drive(writer, "VAR-A", analog)
        writer.close()

        with h5py.File(path, 'r') as h5f:
            self.assertEqual(h5f.attrs['sampling_frequency_hz'], 10)
            times = h5f["root/time"][()]
            self.assertEqual(times.dtype, np.dtype('u8'))
            self.assertEqual(times[0], BASE_NS)
            values = h5f["root/VAR-A"][()]
            self.assertEqual(values.dtype, np.dtype('f4'))
            np.testing.assert_allclose(values, 1.5)
            self.assertEqual(h5f["root/VAR-A"].attrs['unit'], "V")

    def test_relative_time_counts_from_grid_origin(self):
        path = os.path.join(self.tmpdir.name, "rel.parquet")
        exportData.relative_start_ns = BASE_NS + 123  # raw start carries ns
        writer = exportData._ResampledParquetWriter(path, self.GRID)
        self._drive(writer, "VAR-A",
                    _StubReader(exportData.RAW_TYPE_DOUBLE, [([BASE_NS], [1.0])]))
        writer.close()

        table = pq.read_table(path)
        self.assertEqual(table.schema.field('timestamp').type, 'double')
        times = table['timestamp'].to_numpy()
        self.assertEqual(times[0], 0.0)
        self.assertAlmostEqual(times[-1], 2.0)

    def test_variable_without_data_repeats_the_seed(self):
        path = os.path.join(self.tmpdir.name, "seed.parquet")
        writer = exportData._ResampledParquetWriter(path, self.GRID)
        seed = exportData._LastValueCallback()
        seed.value, seed.ytype, seed.unit = 4.25, exportData.RAW_TYPE_DOUBLE, "A"
        rlog = io.StringIO()
        callback = exportData._ResampleChunkCallback("VAR-A", self.GRID, writer, seed)
        exportData._finalize_resampled("VAR-A", callback, writer, self.GRID, rlog)
        writer.close()

        table = pq.read_table(path)
        np.testing.assert_allclose(table['VAR-A'].to_numpy(), 4.25)
        self.assertIn("value before it repeated", rlog.getvalue())

    def test_variable_without_data_or_seed_is_skipped_and_logged(self):
        path = os.path.join(self.tmpdir.name, "skip.parquet")
        writer = exportData._ResampledParquetWriter(path, self.GRID)
        rlog = io.StringIO()
        callback = exportData._ResampleChunkCallback("VAR-A", self.GRID, writer, None)
        exportData._finalize_resampled("VAR-A", callback, writer, self.GRID, rlog)
        self.assertEqual(writer.columns, {})
        self.assertIn("skipped", rlog.getvalue())
        writer.close()

    def test_gap_log_groups_consecutive_intervals(self):
        writer = exportData._ResampledParquetWriter(
            os.path.join(self.tmpdir.name, "log.parquet"), self.GRID)
        rlog = io.StringIO()
        self._drive(writer, "VAR-A",
                    _StubReader(exportData.RAW_TYPE_DOUBLE,
                                [([BASE_NS, BASE_NS + 2 * NS], [1.0, 2.0])]),
                    rlog=rlog)
        writer.close()
        lines = rlog.getvalue().splitlines()
        self.assertEqual(len([ln for ln in lines if "no data" in ln]), 1)
        self.assertIn("(19 intervals, previous value repeated)", lines[1])

    def test_generate_data_defaults_to_no_resampling(self):
        import inspect
        sig = inspect.signature(exportData.generateData)
        self.assertIn('resampleFreq', sig.parameters)
        self.assertIsNone(sig.parameters['resampleFreq'].default)


if __name__ == "__main__":
    unittest.main()
