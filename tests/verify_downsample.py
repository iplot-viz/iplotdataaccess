#!/usr/bin/env python3
"""Verify that a DAN 1Hz export is the 1-second block-average of a native export.

Model tested:
    bin i  = [t0 + i*1s, t0 + (i+1)*1s)      (left-closed, forward-looking)
    value  = unweighted arithmetic mean of the native samples in the bin
    gaps   = forward-fill of the previous bin value, then back-fill at the head

Usage:
    ./verify_downsample.py native.hdf5 downsampled.hdf5
"""
import sys
import numpy as np
import h5py

NS = 1_000_000_000


def read_native(path):
    out = {}
    with h5py.File(path, "r") as f:
        for var in f["root"]:
            g = f[f"root/{var}"]
            # concatenate all period_* groups
            ts, vs = [], []
            for period in sorted(g):
                # A variable with no samples leaves its period group empty.
                if "data" not in g[period]:
                    continue
                d = g[f"{period}/data"][:]
                ts.append(d["time"].astype(np.int64))
                vs.append(d["value"].astype(np.float64))
            if not ts:
                continue
            t = np.concatenate(ts)
            v = np.concatenate(vs)
            order = np.argsort(t, kind="stable")
            out[var] = (t[order], v[order])
    return out


def read_downsampled(path):
    with h5py.File(path, "r") as f:
        t = f["root/time"][:].astype(np.int64)
        data = {k: f[f"root/{k}"][:].astype(np.float64)
                for k in f["root"] if k != "time"}
    return t, data


def block_average(t_native, v_native, grid):
    """Mean per [grid[i], grid[i]+1s) bin; NaN where the bin is empty."""
    n = len(grid)
    idx = (t_native - grid[0]) // NS
    keep = (idx >= 0) & (idx < n)
    idx, v = idx[keep], v_native[keep]

    count = np.zeros(n, dtype=np.int64)
    total = np.zeros(n, dtype=np.float64)
    np.add.at(count, idx, 1)
    np.add.at(total, idx, v)

    mean = np.full(n, np.nan)
    mean[count > 0] = total[count > 0] / count[count > 0]
    return mean, count, int((~keep).sum())


def fill_gaps(a):
    out = a.copy()
    for i in range(1, len(out)):
        if np.isnan(out[i]):
            out[i] = out[i - 1]
    for i in range(len(out) - 2, -1, -1):
        if np.isnan(out[i]):
            out[i] = out[i + 1]
    return out


def main(native_path, ds_path):
    grid, ref = read_downsampled(ds_path)
    native = read_native(native_path)

    step = np.unique(np.diff(grid))
    print(f"grid: {len(grid)} points, step(s) = {step / NS}, "
          f"whole-second aligned = {bool((grid % NS == 0).all())}")

    ok = True
    for var, expected in ref.items():
        if var not in native:
            print(f"{var}: MISSING from native file")
            ok = False
            continue

        t, v = native[var]
        mean, count, dropped = block_average(t, v, grid)
        rebuilt = fill_gaps(mean)

        diff = np.abs(rebuilt - expected)
        exact = int((rebuilt.view(np.uint64) == expected.view(np.uint64)).sum())
        real = count > 0
        bad_real = int((diff[real] > 0).sum())

        print(f"\n{var}")
        print(f"  native samples      : {len(t)} (outside grid: {dropped})")
        print(f"  populated bins      : {int(real.sum())}/{len(grid)}  "
              f"max samples/bin: {int(count.max())}")
        print(f"  bit-exact points    : {exact}/{len(grid)}")
        print(f"  mismatched real bins: {bad_real}   max |err|: {diff.max():.3e}")
        if bad_real:
            ok = False
            where = np.where(real & (diff > 0))[0][:10]
            for i in where:
                print(f"    bin {i}: got {expected[i]!r} expected {rebuilt[i]!r}")
        gap_bad = np.where(~real & (diff > 0))[0]
        if gap_bad.size:
            print(f"  gap-filled bins differing: {gap_bad.size} "
                  f"(indices {gap_bad[:10]}{'...' if gap_bad.size > 10 else ''})")

    print("\nRESULT:", "consistent" if ok else "discrepancies found")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
