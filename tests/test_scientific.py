"""Check axis orientation and bounded reads using coordinate-encoded data."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from datapeek.scientific import draw, render_scientific, draw_array
from datapeek.sources import open_array

def render_custom(path, options):
    with open_array(path,options,'personal:geoscience.py:geoscience',reader_paths=[str(Path(__file__).resolve().parents[1]/'examples/readers')]) as (data,resolved,title,axis,dt):
        return draw_array(data,resolved,title,axis,dt)


class ScientificTests(unittest.TestCase):
    def test_volume_axes_and_positions(self):
        data = np.arange(4*5*6).reshape(4, 5, 6)
        fig = draw(data, {'slices': ['iline', 'xline', 'time'], 'iline': 1, 'xline': 2, 'time': 3}, 'test', volume=True)
        for ax, expected in zip(fig.axes, (data[1].T, data[:, 2].T, data[:, :, 3])):
            np.testing.assert_array_equal(ax.images[0].get_array(), expected)
        with self.assertRaises(ValueError):
            draw(data, {'slices': ['time'], 'time': 6}, 'test', volume=True)

    def test_volume_never_reads_full_cube(self):
        class Lazy:
            shape = (40, 50, 60)
            dtype = np.dtype('float32')
            chunks = (4, 5, 6)
            def read_region(self, key):
                assert sum(isinstance(k, int) for k in key) == 1
                assert all(k == slice(None) for k in key if isinstance(k, slice))
                return np.zeros(tuple(len(range(*k.indices(n))) for k, n in zip(key, self.shape) if isinstance(k, slice)))
        draw(Lazy(), {'max_pixels': 16}, 'lazy', volume=True)

    def test_das_orientation(self):
        data = np.arange(30).reshape(6, 5)
        fig = draw(data, {'kind':'das'}, 'test', time_axis=0)
        np.testing.assert_array_equal(fig.axes[0].images[0].get_array(), data.T)
        self.assertEqual(fig.axes[0].get_xlabel(), 'Time index')

    def test_dat_layout_and_size(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test_h6x5x4.dat'
            data = np.arange(120, dtype='<f4').reshape(4, 5, 6)
            data.tofile(path)
            fig = render_custom(path, {})
            np.testing.assert_array_equal(fig.axes[0].images[0].get_array(), data[2].T)
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'byte size'):
                render_custom(path, {})

    def test_zarr_directory_and_dataset(self):
        import zarr
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.zarr'
            group = zarr.open_group(str(path), mode='w')
            data = np.arange(120, dtype='float32').reshape(4, 5, 6)
            group.create_array('imp', data=data)
            group.create_array('rgt', data=data + 100)
            fig = render_scientific(path, {'dataset': 'rgt'})
            np.testing.assert_array_equal(fig.axes[0].images[0].get_array(), data[2].T + 100)

    def test_large_volume_defaults_to_iline(self):
        calls = []
        class Lazy:
            shape = (10000, 200, 300)
            dtype = np.dtype('float32')
            chunks = (1, 20, 30)
            def read_region(self, key):
                calls.append(key)
                self.assert_key = key
                return np.zeros((200, 300))
        draw(Lazy(), {}, 'default', volume=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 5000)
        self.assertIsInstance(calls[0][1], slice)
        self.assertIsInstance(calls[0][2], slice)

    def test_chunk_budget_reduces_selection_before_read(self):
        from datapeek.sampling import read_sample, estimate
        class Lazy:
            shape = (1000, 1000)
            dtype = np.dtype('float32')
            chunks = (10, 10)
            def __getitem__(self, key):
                self.key = key
                return np.zeros(tuple(len(range(*k.indices(n))) for k, n in zip(key, self.shape)))
        data = Lazy()
        values, _, cost = read_sample(data, (slice(None), slice(None)), 100_000, 'budget')
        self.assertLessEqual(cost, 100_000)
        self.assertLess(values.size, 1000 * 1000)
        self.assertEqual(cost, estimate(data, data.key))

    def test_oversize_npz_rejected_before_array_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'large.npz'
            np.savez_compressed(path, data=np.zeros((1024, 1024), dtype='float32'))
            with self.assertRaisesRegex(ValueError, 'cannot be randomly sampled'):
                render_scientific(path, {'max_read_mib': 1})

    def test_event_sampling_is_lazy(self):
        from datapeek.sampling import EventView, read_sample
        class Array:
            shape = (10, 1000, 1000)
            chunks = (1, 10, 10)
            dtype = np.dtype('float32')
            def __getitem__(self, key):
                self.key = key
                return np.zeros(tuple(len(range(*k.indices(n))) for k, n in zip(key[1:], self.shape[1:])))
        array = Array()
        view = EventView(array, 3, 800)
        read_sample(view, (slice(None, None, 4), slice(None, None, 4)), 128 * 1024**2, 'event')
        self.assertEqual(array.key, (3, slice(0, 1000, 4), slice(0, 800, 4)))

    def test_unreadable_chunk_budget_is_error(self):
        from datapeek.sampling import read_sample
        class Array:
            shape = (1000, 1000)
            chunks = (1000, 1000)
            dtype = np.dtype('float32')
            def __getitem__(self, key):
                raise AssertionError('must reject before reading')
        with self.assertRaisesRegex(ValueError, 'minimum read estimate'):
            read_sample(Array(), (slice(None), slice(None)), 1000, 'budget')

    def test_small_volume_defaults_to_three_full_slices(self):
        data = np.arange(4*5*6).reshape(4, 5, 6)
        fig = draw(data, {}, 'small', volume=True)
        self.assertEqual(len(fig.axes), 4)  # three slices and colorbar
        for ax, expected in zip(fig.axes, (data[2].T, data[:, 2].T, data[:, :, 3])):
            np.testing.assert_array_equal(ax.images[0].get_array(), expected)

    def test_explicit_slices_override_size_policy(self):
        data = np.arange(4*5*6).reshape(4, 5, 6)
        fig = draw(data, {'large_volume_gb': 0.000000001, 'slices': ['xline', 'time']}, 'override', volume=True)
        self.assertEqual(len(fig.axes), 3)
        np.testing.assert_array_equal(fig.axes[0].images[0].get_array(), data[:, 2].T)

    def test_das_chunk_selects_its_own_event(self):
        import zarr
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'das' / 'earthquake' / 'part_00.zarr'
            group = zarr.open_group(str(path), mode='w', zarr_format=2)
            data = np.arange(3*4*5, dtype='float32').reshape(3, 4, 5)
            group.create_array('data', data=data, chunks=(1, 4, 5))
            group.attrs['dims'] = 'event_channel_time'
            for index in range(3):
                chunk = path / 'data' / f'{index}.0.0'
                self.assertTrue(chunk.is_file())
                fig = render_custom(chunk, {'event': 2})
                np.testing.assert_array_equal(fig.axes[0].images[0].get_array(), data[index])
            with self.assertRaisesRegex(ValueError, 'individual DAS event'):
                render_custom(path, {})
