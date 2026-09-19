"""Numerical and slicing checks for the standalone custom Figure example."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
spec = importlib.util.spec_from_file_location('seismic_fault_demo', ROOT/'examples/seismic_fault_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class SeismicDemoTests(unittest.TestCase):
    def test_step_impedance_reflection_and_centered_wavelet(self):
        imp = np.full((2, 129), 2000., dtype='float32')
        imp[:, 65:] = 4000.
        reflection, seismic = demo.synthetic(imp, .002, 25., .128, 'normalized')
        self.assertEqual(np.count_nonzero(reflection), 2)
        np.testing.assert_allclose(reflection[:, 64], 1/3)
        self.assertEqual(np.argmax(seismic[0]), 64)
        np.testing.assert_allclose(seismic[:, 64], 1/3)
        np.testing.assert_allclose(seismic[:, 63], seismic[:, 65])
        diff, _ = demo.synthetic(imp, .002, 25., .128, 'difference')
        np.testing.assert_allclose(diff[:,64], 2000)
        zeros, signal = demo.synthetic(np.zeros_like(imp), .002, 25., .128, 'normalized')
        self.assertFalse(zeros.any());self.assertFalse(signal.any())

    def test_npz_streamed_sections_match_array_slicing(self):
        imp=np.arange(3*4*129,dtype='float32').reshape(3,4,129)+2000
        fault=(imp % 7 == 0).astype('float16')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.npz'
            np.savez_compressed(path,imp=imp,fault=fault)
            for axis,key in [('iline',(1,slice(None),slice(None))),('xline',(slice(None),1,slice(None)))]:
                a,b,index=demo.read_sections(path,axis,1)
                np.testing.assert_array_equal(a,imp[key]);np.testing.assert_array_equal(b,fault[key]);self.assertEqual(index,1)
            with self.assertRaises(ValueError):demo.read_sections(path,'iline',3)
            with self.assertRaises(ValueError):demo.read_sections(path,'time',1)

    def test_overlay_orientation_and_background_transparency(self):
        imp=np.ones((3,4,129),dtype='float32')*2000;imp[:,:,65:]=4000
        fault=np.zeros_like(imp);fault[1,2,40:50]=3
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.npz';np.savez_compressed(path,imp=imp,fault=fault)
            figure=demo.render(path,dict(index=1))
            self.assertEqual(len(figure.axes),1)
            signal,overlay=figure.axes[0].images
            self.assertEqual(signal.get_array().shape,(129,4))
            np.testing.assert_array_equal(~np.ma.getmaskarray(overlay.get_array()),fault[1].T>0)
            self.assertEqual(signal.get_extent(),overlay.get_extent())
            self.assertEqual(len(demo.render(path,dict(index=1,show_steps=True)).axes),3)
