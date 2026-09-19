"""Array-reader contract, generic semantics and native cigvis delegation."""
import base64
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from datapeek import Array, viewer
from datapeek.sources import open_array
from datapeek.detail import DetailSession
from datapeek.scientific import draw_array


def unpack(result):
    return np.frombuffer(base64.b64decode(result['data']),dtype='<f4').reshape(result['shape'])


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'matrix.npy'
        self.data=np.arange(24,dtype='float32').reshape(4,6)
        np.save(self.path,self.data)

    def test_generic_quick_and_detail_keep_axes_orientation_and_values(self):
        with open_array(self.path,{}) as (data,options,title,axis,dt):
            fig=draw_array(data,options,title,axis,dt)
        session=DetailSession(self.path,{});self.addCleanup(session.close)
        result=session.sample({})
        self.assertEqual((result['xlabel'],result['ylabel']),('Column index','Row index'))
        self.assertEqual(fig.axes[0].images[0].origin,'upper')
        np.testing.assert_array_equal(fig.axes[0].images[0].get_array(),unpack(result))
        roi=session.sample({'xrange':[1,2],'yrange':[0,1]})
        np.testing.assert_array_equal(unpack(roi),unpack(result)[:2,1:3])

    def test_hdf5_generic_does_not_demean(self):
        import h5py
        path=self.path.with_suffix('.h5')
        with h5py.File(path,'w') as f:f['arbitrary/name']=self.data+100
        session=DetailSession(path,{});self.addCleanup(session.close)
        np.testing.assert_array_equal(unpack(session.sample({})),self.data+100)

    def test_no_guessed_npz_field(self):
        path=self.path.with_suffix('.npz');np.savez(path,data=self.data,clean_strain_rate=self.data+10)
        with self.assertRaisesRegex(ValueError,'Available arrays'):
            DetailSession(path,{})
        session=DetailSession(path,{'dataset':'data'});self.addCleanup(session.close)
        np.testing.assert_array_equal(unpack(session.sample({})),self.data)

    def test_custom_lazy_reader_reuses_all_views_and_closes(self):
        closed=[]
        @viewer.reader(name='lazy test',extensions=['.xyz'],id='test_lazy')
        @contextmanager
        def reader(path,options):
            try:yield Array(self.data,{'xlabel':'Distance','ylabel':'Depth'},'Custom matrix')
            finally:closed.append(True)
        self.addCleanup(lambda:viewer.renderers.pop('builtin:test_lazy',None))
        session=DetailSession(self.path,{},renderer_id='builtin:test_lazy')
        self.assertEqual(session.sample({})['xlabel'],'Distance')
        session.close();self.assertEqual(closed,[True])

    def test_reject_implicit_region_dependent_processing(self):
        with self.assertRaisesRegex(ValueError,'fixed reference'):
            DetailSession(self.path,{'demean':True})

    def test_cigvis_receives_user_positions_without_camera_overrides(self):
        np.save(self.path,np.arange(8*9*10,dtype='float32').reshape(8,9,10))
        session=DetailSession(self.path,{});self.addCleanup(session.close)
        from cigvis import viserplot
        from cigvis.visernodes import Server
        with patch.object(viserplot,'create_slices',return_value=[]) as create, patch.object(viserplot,'plot3D') as plot, patch('cigvis.visernodes.Server',spec=Server) as server:
            server.return_value.get_port.return_value=12345
            session.start_viser({'axis':'iline','index':2,'positions':{'iline':2,'xline':3,'time':4},'slices':['iline','xline','time'],'vmin':0,'vmax':100,'cmap':'Petrel'})
            self.assertEqual(create.call_args.kwargs['pos'],{'x':[2],'y':[3],'z':[4]})
            self.assertEqual(set(plot.call_args.kwargs),{'server','run_app'})
            self.assertEqual(create.call_args.kwargs['cmap'],'Petrel')
