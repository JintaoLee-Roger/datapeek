"""Conservative read estimates; these are not measurements of disk traffic."""
import math
import time


def budget_bytes(options):
    value = options.get('max_read_mib', 256)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 4096:
        raise ValueError('max_read_mib must be between 1 and 4096')
    return int(value * 1024**2)


def estimate(data, key):
    import numpy as np
    if isinstance(data, EventView):
        return estimate(data.array, (data.event, *key))
    chunks = getattr(data, 'chunks', None)
    ranges = [range(k, k + 1) if isinstance(k, int) else range(*k.indices(n)) for n, k in zip(data.shape, key)]
    if any(len(r) == 0 for r in ranges):
        return 0
    if chunks:
        count = math.prod(len({i // c for i in r}) for r, c in zip(ranges, chunks))
        return count * math.prod(chunks) * np.dtype(data.dtype).itemsize
    if isinstance(data, np.memmap):
        # Count virtual pages touched by the requested samples, including element boundaries.
        offsets = np.array([0], dtype=np.int64)
        for r, stride in zip(ranges, data.strides):
            offsets = (offsets[:, None] + np.asarray(r, dtype=np.int64)[None, :] * stride).ravel()
        offsets += int(data.offset)
        pages = np.concatenate((offsets // 4096, (offsets + data.dtype.itemsize - 1) // 4096))
        return len(np.unique(pages)) * 4096
    if hasattr(data, 'read_region'):
        raise ValueError('Backend does not expose chunks; cannot estimate read cost')
    if not isinstance(data, np.ndarray):
        # Contiguous HDF5: conservative page estimate (layout/cache can change actual I/O).
        return min(math.prod(data.shape) * np.dtype(data.dtype).itemsize, math.prod(map(len, ranges)) * 4096)
    return math.prod(map(len, ranges)) * np.dtype(data.dtype).itemsize


def read_sample(data, key, budget, label):
    import numpy as np
    key = list(key)
    cost = estimate(data, key)
    while cost > budget:
        candidates = [i for i, k in enumerate(key) if isinstance(k, slice) and len(range(*k.indices(data.shape[i]))) > 1]
        if not candidates:
            raise ValueError(f'{label}: minimum read estimate {cost / 1024**2:.1f} MiB exceeds budget {budget / 1024**2:.1f} MiB; increase max_read_mib or rechunk data')
        axis = max(candidates, key=lambda i: len(range(*key[i].indices(data.shape[i]))))
        k = key[axis]
        key[axis] = slice(k.start, k.stop, (k.step or 1) * 2)
        cost = estimate(data, key)
    start = time.perf_counter()
    read = data.read_region if hasattr(data, 'read_region') else data.__getitem__
    # Copy forces mmap pages to be touched inside the measured read interval.
    values = np.array(read(tuple(key)), copy=True)
    elapsed = time.perf_counter() - start
    print(f'DataPeek read {label}: {elapsed:.4f}s; sampled={values.shape}; estimated read/decode={cost / 1024**2:.2f} MiB; output={values.nbytes / 1024**2:.2f} MiB', flush=True)
    return values, elapsed, cost


class EventView:
    """Keep an event lazy: sampling goes into the original Zarr selection."""
    def __init__(self, array, event, nt):
        self.array, self.event = array, event
        self.shape = (array.shape[1], nt)
        self.dtype = array.dtype
        # Include the event chunk amplification in the projected chunk estimate.
        self.chunks = (array.chunks[1] * array.chunks[0], array.chunks[2])

    def __getitem__(self, key):
        bounded = tuple(slice(*k.indices(n)) for k, n in zip(key, self.shape))
        return self.array[(self.event, *bounded)]
