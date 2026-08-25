"""Resampling of exported signals onto a common time grid.

The grid depends only on the export window and the chosen frequency, so every
variable lands on the same timestamps regardless of its own sampling. Samples
are folded into fixed-period buckets as the chunks arrive; buckets with data
hold the average (or the last sample, for integer signals), empty buckets
repeat the previous value.
"""

import numpy as np

NS_PER_SECOND = 1_000_000_000


def grid_period_ns(freq_hz):
    """Bucket period in nanoseconds for ``freq_hz``.

    Only frequencies that divide one second exactly are accepted: they are the
    ones whose grid points fall on round timestamps.
    """
    period, remainder = divmod(NS_PER_SECOND, int(freq_hz))
    if remainder or period <= 0:
        raise ValueError(f"Sampling frequency {freq_hz} Hz does not divide one second exactly")
    return period


def build_grid(start_ns, end_ns, freq_hz):
    """Grid origin, period and point count for the window ``[start_ns, end_ns]``.

    The start is floored and the end is ceiled to the whole second, so the grid
    points carry no sub-second offset yet the grid always covers the window:
    flooring the end would drop the samples past the last grid bucket whenever
    the window does not end on a round second.
    """
    start = int(start_ns) // NS_PER_SECOND * NS_PER_SECOND
    end = -(-int(end_ns) // NS_PER_SECOND) * NS_PER_SECOND
    if end < start:
        raise ValueError("Export window ends before it starts")
    period = grid_period_ns(freq_hz)
    return start, period, (end - start) // period + 1


def grid_times(start_ns, period_ns, index_from, index_to):
    """Grid timestamps (ns, uint64) for the bucket range ``[index_from, index_to)``."""
    return (np.arange(index_from, index_to, dtype=np.uint64) * np.uint64(period_ns)
            + np.uint64(start_ns))


class BucketAccumulator:
    """Folds one variable's time-ordered samples into grid buckets.

    Chunks arrive in time order, so a bucket can be closed as soon as a sample
    at or past its end shows up; only the partial sum/count and the last sample
    have to survive from one chunk to the next. Closed buckets are handed to
    ``sink(index, values)`` in order, ready to be written.

    ``average`` selects the bucket value: the mean of its samples, or the last
    sample for signals where a mean is meaningless (states, counters). ``seed``
    is the last archived value before the window, used to fill leading buckets;
    without one they are back-filled with the first value seen.
    """

    def __init__(self, count, average, sink, seed=None):
        self._count = int(count)
        self._average = bool(average)
        self._sink = sink
        self._carry = seed
        self._had_seed = seed is not None
        self._next = 0
        self._pending = None  # (bucket, sum, count, last) still open at a chunk boundary
        self._filled_runs = []  # [first, last] bucket ranges that repeated a value
        self._no_seed_lead = 0  # leading buckets back-filled from the first sample
        self._samples = 0

    @property
    def samples(self):
        return self._samples

    @property
    def filled_runs(self):
        return list(self._filled_runs)

    @property
    def no_seed_lead(self):
        return self._no_seed_lead

    def add(self, bucket_idx, values):
        """Fold one chunk, given each sample's bucket index (int64) and value."""
        keep = (bucket_idx >= 0) & (bucket_idx < self._count)
        bucket_idx = bucket_idx[keep]
        values = np.asarray(values, dtype=np.float64)[keep]
        if bucket_idx.size == 0:
            return
        self._samples += int(bucket_idx.size)

        # Segment the chunk by bucket; only the last segment can stay open.
        seg_starts = np.flatnonzero(np.r_[True, np.diff(bucket_idx) != 0])
        seg_ends = np.r_[seg_starts[1:], bucket_idx.size]
        buckets = bucket_idx[seg_starts]
        sums = np.add.reduceat(values, seg_starts)
        counts = (seg_ends - seg_starts).astype(np.int64)
        lasts = values[seg_ends - 1]

        # Merge the bucket left open by the previous chunk into its first segment.
        if self._pending is not None:
            p_bucket, p_sum, p_count, p_last = self._pending
            if buckets[0] == p_bucket:
                sums[0] += p_sum
                counts[0] += p_count
            else:
                buckets = np.r_[p_bucket, buckets]
                sums = np.r_[p_sum, sums]
                counts = np.r_[p_count, counts]
                lasts = np.r_[p_last, lasts]
            self._pending = None

        self._pending = (int(buckets[-1]), float(sums[-1]), int(counts[-1]), float(lasts[-1]))
        if buckets.size > 1:
            self._emit(buckets[:-1], sums[:-1], counts[:-1], lasts[:-1])

    def finish(self):
        """Close the open bucket and repeat the carry up to the end of the grid."""
        if self._pending is not None:
            buckets, sums, counts, lasts = (np.array([v]) for v in self._pending)
            self._pending = None
            self._emit(buckets.astype(np.int64), sums, counts.astype(np.int64), lasts)
        if self._next < self._count:
            if self._carry is None:
                return False  # nothing ever arrived and there was no seed
            self._fill(self._next, self._count)
            self._track_fill(self._next, self._count)
            self._next = self._count
        return True

    def _emit(self, buckets, sums, counts, lasts):
        first = int(buckets[0])
        if first > self._next:
            if self._carry is None:
                # No sample before the window: the leading buckets take the
                # first value seen rather than a fabricated one.
                self._carry = float(sums[0] / counts[0]) if self._average else float(lasts[0])
                self._no_seed_lead = first - self._next
            self._fill(self._next, first)
            self._track_fill(self._next, first)
            self._next = first

        span = int(buckets[-1]) - first + 1
        values = np.empty(span, dtype=np.float64)
        present = np.zeros(span, dtype=bool)
        rel = (buckets - first).astype(np.intp)
        present[rel] = True
        values[rel] = (sums / counts) if self._average else lasts

        # Forward-fill the holes between closed buckets with the last value;
        # the first bucket of the span always has samples, so every hole has
        # a value before it.
        if not present.all():
            pos = np.where(present, np.arange(span), -1)
            np.maximum.accumulate(pos, out=pos)
            values = values[pos]
            holes = np.flatnonzero(~present)
            run_starts = np.flatnonzero(np.r_[True, np.diff(holes) != 1])
            run_ends = np.r_[run_starts[1:], holes.size]
            for a, b in zip(run_starts, run_ends):
                self._track_fill(first + int(holes[a]), first + int(holes[b - 1]) + 1)

        self._sink(self._next, values)
        self._carry = float(values[-1])
        self._next = first + span

    def _fill(self, index_from, index_to):
        self._sink(index_from, np.full(index_to - index_from, self._carry, dtype=np.float64))

    def _track_fill(self, index_from, index_to):
        if self._filled_runs and self._filled_runs[-1][1] == index_from:
            self._filled_runs[-1][1] = index_to
        else:
            self._filled_runs.append([index_from, index_to])
