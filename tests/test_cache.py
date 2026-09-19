import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from datapeek.cache import PreviewCache
import runner


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'data.npy'
        self.source.write_bytes(b'source')
        self.request = dict(protocolVersion=1, operation='render', targetPath=str(self.source), rendererId='builtin:npy', options={}, cache=dict(enabled=True, directory=str(self.root/'cache'), maxEntries=2))

    def populate(self, request=None):
        request = request or self.request
        cache = PreviewCache(request)
        folder = self.root / ('render-' + cache.key)
        (folder / 'artifacts').mkdir(parents=True, exist_ok=True)
        (folder / 'artifacts/figure.png').write_bytes(b'png result')
        result = {'artifact': {'kind':'image', 'entry':'artifacts/figure.png'}}
        cache.save(result, folder, request['targetPath'])
        return cache

    def test_hit_bypasses_renderer(self):
        self.populate()
        folder = self.root / 'hit'; folder.mkdir()
        with patch.object(runner, 'run', side_effect=AssertionError('must not render')):
            result = runner.cached_run(self.request, folder)
        self.assertEqual((folder / result['artifact']['entry']).read_bytes(), b'png result')

    def test_changes_invalidate(self):
        cache = self.populate()
        self.source.write_bytes(b'changed')
        self.assertNotEqual(cache.key, PreviewCache(self.request).key)
        request = {**self.request, 'options': {'iline': 4}}
        self.assertNotEqual(PreviewCache(self.request).key, PreviewCache(request).key)

    def test_directory_child_change_invalidates(self):
        folder = self.root / 'store.zarr'; folder.mkdir()
        child = folder / 'chunk'; child.write_bytes(b'old')
        request = {**self.request, 'targetPath': str(folder)}
        before = PreviewCache(request).key
        child.write_bytes(b'new')
        self.assertNotEqual(before, PreviewCache(request).key)

    def test_lru_count_and_age(self):
        first = self.populate()
        second = self.populate({**self.request, 'options': {'iline': 1}})
        os.utime(first.entry, (1, 1))
        third = self.populate({**self.request, 'options': {'iline': 2}})
        self.assertFalse(first.entry.exists())
        self.assertTrue(second.entry.exists())
        self.assertTrue(third.entry.exists())
        fourth = self.populate({**self.request, 'options': {'iline': 3}})
        self.assertEqual(len(list(fourth.root.iterdir())), 2)

    def test_corrupt_cache_is_miss(self):
        cache = self.populate()
        (cache.entry/'figure.png').write_bytes(b'corrupt')
        folder = self.root/'hit'; folder.mkdir()
        self.assertIsNone(cache.restore(folder))

    def test_byte_limit_prunes(self):
        cache = self.populate()
        cache.max_bytes = 1
        cache.prune()
        self.assertFalse(cache.entry.exists())

    def test_source_change_during_render_not_saved(self):
        cache = PreviewCache(self.request)
        self.source.write_bytes(b'changed')
        cache.save({'artifact': {'kind':'image'}}, self.root, str(self.source))
        self.assertFalse(cache.entry.exists())

    def test_events_in_same_store_do_not_share_cache(self):
        store = self.root / 'part_00.zarr'
        data = store / 'data'; data.mkdir(parents=True)
        for name in ('0.0.0', '7.0.0'):
            (data / name).write_bytes(name.encode())
        zero = {**self.request, 'targetPath': str(data / '0.0.0')}
        seven = {**self.request, 'targetPath': str(data / '7.0.0')}
        zero_cache = self.populate(zero)
        seven_cache = PreviewCache(seven)
        self.assertNotEqual(zero_cache.key, seven_cache.key)
        output = self.root / 'seven'; output.mkdir()
        self.assertIsNone(seven_cache.restore(output))
        metadata = store / '.zattrs'; metadata.write_text('{"fs":50}')
        self.assertNotEqual(seven_cache.key, PreviewCache(seven).key)

    def test_custom_reader_edit_invalidates_cache(self):
        script=self.root/'custom.py';script.write_text('x=1')
        request={**self.request,'readerCodeFiles':[str(script)]}
        before=PreviewCache(request).key
        script.write_text('x=2')
        self.assertNotEqual(before,PreviewCache(request).key)
