import base64
import json
import zlib
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from datapeek.quick import payload, render
from datapeek.colors import color_limits
from datapeek.cache import PreviewCache

class QuickTests(unittest.TestCase):
    def test_orientation_limits_and_invalid(self):
        values=np.array([[-3.,-1.,np.nan],[0.,1.,4.]])
        p=payload(values,{'cmap':'gray','kind':'das'},'event 7',time_axis=0,dt=.02)
        self.assertEqual(p['limits'],list(color_limits(values,{})))
        a=p['panels'][0]
        self.assertEqual((a['rows'],a['cols']),(3,2))
        self.assertEqual(a['width'],.02)
        self.assertEqual(a['aspect'],2/3)
        self.assertEqual(list(base64.b64decode(a['mask'])),[1,1,1,1,0,1])
        self.assertEqual(p['title'],'event 7')

    def test_volume_reads_full_slices_and_respects_selection(self):
        class Volume:
            shape=(17,21,25);dtype=np.dtype('float32')
            def __getitem__(self,key):
                keys.append(key)
                return np.arange(17*21*25,dtype='float32').reshape(self.shape)[key]
        keys=[]
        p=payload(Volume(),{'slices':['xline','time'],'xline':3,'time':7,'max_pixels':16},'volume')
        self.assertEqual(keys,[(slice(None),3,slice(None)),(slice(None),slice(None),7)])
        self.assertEqual([(x['rows'],x['cols']) for x in p['panels']],[(13,9),(9,11)])
        self.assertEqual(p['panels'][0]['xlabel'],'iline')
        self.assertEqual(p['panels'][0]['ylabel'],'time')
        self.assertEqual([x['aspect'] for x in p['panels']],[17/25,21/17])

    def test_custom_aspect_preserves_pixels(self):
        values=np.arange(2000,dtype='float32').reshape(200,10)
        original=payload(values,{},'tall')
        custom=payload(values,{'preserve_aspect':False,'aspect_ratio':2},'tall')
        self.assertFalse(custom['preserveAspect'])
        self.assertEqual(custom['aspectRatio'],2)
        self.assertEqual(original['panels'],custom['panels'])
        self.assertEqual(original['limits'],custom['limits'])

    def test_common_lut_matches_matplotlib(self):
        import matplotlib
        values=np.linspace(-1,1,513).reshape(1,-1)
        for cmap in ['gray','seismic','viridis','RdBu_r']:
            p=payload(values,dict(cmap=cmap,vmin=-1,vmax=1,max_pixels=1024),'x')
            panel=p['panels'][0];raw=base64.b64decode(panel['pixels'])
            indices=np.frombuffer(zlib.decompress(raw) if panel['compressed'] else raw,dtype='uint8')
            lut=np.frombuffer(base64.b64decode(p['lut']),dtype='uint8').reshape(256,4)
            np.testing.assert_array_equal(lut[indices],matplotlib.colormaps[cmap]((values.ravel()+1)/2,bytes=True))

    def test_html_escapes_title_and_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);art=root/'artifacts';art.mkdir();target=root/'data.npy';np.save(target,np.zeros((2,2)))
            artifact=render(np.zeros((2,2)),{},'</script><script>alert(1)</script>',art)
            content=(art/artifact['entry']).read_bytes()
            self.assertNotIn(b'<script>alert',content)
            result={'artifact':{**artifact,'entry':'artifacts/'+artifact['entry'],'files':['artifacts/'+s for s in artifact['files']]}}
            request=dict(targetPath=str(target),rendererId='builtin:npy',cache=dict(directory=str(root/'cache')))
            cache=PreviewCache(request);cache.save(result,root,str(target));dest=root/'hit';dest.mkdir()
            hit=cache.restore(dest)
            self.assertEqual(hit,result)
            self.assertEqual((dest/hit['artifact']['entry']).read_bytes(),content)
            (cache.entry/'quick.html').write_text('corrupt')
            self.assertIsNone(cache.restore(dest))

    def test_line_preserves_nan_gaps(self):
        p=payload(np.array([1,np.nan,2.]),{},'line')
        np.testing.assert_equal(np.frombuffer(base64.b64decode(p['line']),dtype='<f8'),[1,np.nan,2])
        self.assertEqual(p['limits'],[1,2])

    def test_compression_preserves_indices(self):
        p=payload(np.zeros((256,256)),{'cmap':'gray'},'zeros')
        a=p['panels'][0]
        self.assertTrue(a['compressed'])
        self.assertEqual(zlib.decompress(base64.b64decode(a['pixels'])),bytes([128])*(256*256))

    def test_default_canvas_does_not_import_plotting_libraries(self):
        import subprocess
        result=subprocess.run([sys.executable,'-c',
            "import sys,tempfile;from pathlib import Path;import numpy as np;from datapeek.quick import render; "
            "t=tempfile.TemporaryDirectory();render(np.zeros((64,64)),{'cmap':'seismic'},'x',Path(t.name)); "
            "assert not any(n in sys.modules for n in ('matplotlib','plotly','PIL')), list(sys.modules)"],
            env={**__import__('os').environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'python')},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
