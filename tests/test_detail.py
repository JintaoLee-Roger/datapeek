import base64
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from datapeek.colors import color_limits
from datapeek.detail import DetailSession


def values(result):
    return np.frombuffer(base64.b64decode(result['data']),dtype='<f4').reshape(result['shape'])


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'volume.npy'
        self.array=np.arange(20*30*40,dtype='float32').reshape(20,30,40)-10000
        np.save(self.path,self.array)
        self.session=DetailSession(self.path,{})
        self.addCleanup(self.session.close)

    def test_three_directions_and_roi(self):
        for axis,expected in [('iline',self.array[3].T),('xline',self.array[:,3].T),('time',self.array[:,:,3])]:
            result=self.session.sample({'axis':axis,'index':3,'xrange':[5,10],'yrange':[6,12]})
            np.testing.assert_array_equal(values(result),expected[6:13,5:11])
            self.assertFalse(result['sampled'])
            self.assertEqual(result['displayAspect'],expected.shape[1]/expected.shape[0])

    def test_slice_is_reused_for_zoom_and_color(self):
        self.session.sample({'axis':'iline','index':3})
        self.session.read=lambda key: self.fail('must reuse full slice')
        result=self.session.sample({'axis':'iline','index':3,'xrange':[5,10],'yrange':[6,12],'vmin':-2,'vmax':5})
        self.assertEqual((result['vmin'],result['vmax']),(-2,5))

    def test_invalid_ranges_and_indices(self):
        for request in ({'index':999},{'axis':'wrong'},{'xrange':[0,float('nan')]},{'vmin':1,'vmax':-1}):
            with self.assertRaises(ValueError):self.session.sample(request)

    def test_memory_cache_limit(self):
        self.session.cache_bytes=self.array[0].nbytes
        for index in range(3):self.session.sample({'index':index})
        self.assertEqual(list(self.session.cache),[(0,2)])

    def test_das_zoom_reads_region_at_full_resolution(self):
        path=Path(self.temp.name)/'das.npz'
        data=np.arange(2000*1000,dtype='float32').reshape(2000,1000)
        np.savez(path,data=data)
        session=DetailSession(path,{})
        try:
            self.assertTrue(session.sample({})['sampled'])
            result=session.sample({'xrange':[10,30],'yrange':[40,60]})
            self.assertFalse(result['sampled'])
            np.testing.assert_array_equal(values(result),data[40:61,10:31])
        finally:session.close()

    def test_waveform_color_formula(self):
        data=np.array([-10,-3,-2,-1,1,2,3,100])
        low,high=np.percentile(data,[.5,99.5])
        expected=min(abs(low),abs(high))
        self.assertEqual(color_limits(data,{}),(-expected,expected))
        self.assertEqual(color_limits(data,{'vmin':-4,'vmax':8}),(-4,8))
        for data in [np.zeros(20),np.array([np.nan,np.inf])]:
            low,high=color_limits(data,{})
            self.assertTrue(np.isfinite(low) and low<high and low==-high)

    def test_non_waveform_limits_keep_original_display_bounds(self):
        for data in (np.linspace(0, 1, 100), np.linspace(-10, -1, 100),
                     np.linspace(-1, 9, 100), np.array([-1e6, 2, 3, 4, 5, 1e6])):
            expected = tuple(np.percentile(data, [.5, 99.5]))
            self.assertEqual(color_limits(data, {}), expected)

    def test_tiny_waveform_and_constant_fields(self):
        data = np.array([-10, -3, -2, -1, 1, 2, 3, 100]) * 1e-12
        low, high = np.percentile(data, [.5, 99.5])
        amplitude = min(abs(low), abs(high))
        self.assertEqual(color_limits(data, {}), (-amplitude, amplitude))
        self.assertNotEqual(amplitude, min(abs(data.min()), abs(data.max())))
        for value in (0, 5, -5):
            low, high = color_limits(np.full(20, value), {})
            self.assertLess(low, value)
            self.assertGreater(high, value)

    def test_cold_volume_roi_reads_only_selected_region(self):
        for axis in ('iline', 'xline', 'time'):
            self.session.cache.clear()
            original = self.session.read
            calls = []
            def read(key):
                calls.append(key)
                return original(key)
            self.session.read = read
            try:
                result = self.session.sample({'axis': axis, 'index': 3, 'xrange': [5, 10], 'yrange': [6, 12]})
            finally:
                self.session.read = original
            self.assertEqual(values(result).shape, (7, 6))
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(k.start is not None and k.stop is not None for k in calls[0] if isinstance(k, slice)))
            self.assertFalse(self.session.cache)
