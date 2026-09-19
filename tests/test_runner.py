import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

import numpy as np

RUNNER = Path(__file__).resolve().parents[1] / "python" / "runner.py"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="datapeek test \u7a7a\u683c ")
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / ".datapeek").mkdir()
        self.target = self.project / "signal.npy"
        np.save(self.target, np.arange(100, dtype=float))

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation="render", **kwargs):
        directory = self.root / str(uuid.uuid4())
        directory.mkdir()
        request = {"protocolVersion": 1, "requestId": str(uuid.uuid4()), "operation": operation,
                   "workspaceRoot": str(self.project), "targetPath": str(self.target),
                   "rendererId": "builtin:npy", "options": {}, "readerPaths": []}
        request.update(kwargs)
        source = directory / "request.json"
        source.write_text(json.dumps(request))
        completed = subprocess.run([sys.executable, str(RUNNER), "--request", str(source)],
                                   cwd=self.project, capture_output=True, text=True, timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads((directory / "response.json").read_text())
        self.assertEqual(response["requestId"], request["requestId"])
        return response, directory, completed

    def test_line_and_image_png(self):
        for data in (np.arange(100), np.arange(120).reshape(10, 12), np.array([True, False])):
            np.save(self.target, data)
            response, directory, _ = self.call(options={"backend":"matplotlib"})
            self.assertEqual(response["status"], "ok", response)
            self.assertEqual((directory / response["artifact"]["entry"]).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    @unittest.skipUnless(importlib.util.find_spec("plotly"), "Optional Plotly dependency is not installed")
    def test_plotly_offline_external_scripts(self):
        response, directory, _ = self.call(options={"backend": "plotly", "title": 'unsafe </script><script>alert(1)</script> \u6807\u7b7e'})
        self.assertEqual(response["status"], "ok", response)
        artifact = response["artifact"]
        html = (directory / artifact["entry"]).read_text()
        self.assertIn('__DATA_CSP__', html)
        self.assertIn('__DATA_ASSET_plotly.min.js__', html)
        self.assertNotIn('<script>alert(1)', html)
        self.assertNotIn('cdn.plot.ly', html)
        for name in artifact["files"]:
            self.assertTrue((directory / name).is_file())
        scripts = '\n'.join((directory / name).read_text() for name in artifact["files"] if 'script-' in name)
        self.assertIn('Plotly.newPlot', scripts)

    @unittest.skipUnless(importlib.util.find_spec("plotly"), "Optional Plotly dependency is not installed")
    def test_plotly_heatmap(self):
        np.save(self.target, np.arange(100).reshape(10, 10))
        response, _, _ = self.call(options={"backend": "plotly"})
        self.assertEqual(response["status"], "ok", response)

    def test_bad_arrays(self):
        for data in (np.zeros((2, 2, 2, 2)), np.array([]), np.array([1j]), np.array(["text"]), np.array([{}], dtype=object)):
            np.save(self.target, data)
            response, _, _ = self.call()
            self.assertEqual(response["status"], "error", response)
            self.assertEqual(response["error"]["code"], "UNSUPPORTED_DATA")

    def test_discovery_rollback_and_print(self):
        (self.project / ".datapeek" / "good.py").write_text('''from datapeek import viewer
print("a user debug message")
@viewer.register(name="Custom", extensions=[".CUSTOM"])
def render(path, options):
    from matplotlib.figure import Figure
    fig = Figure()
    fig.subplots().plot([1, 3, 2])
    return fig
''')
        (self.project / ".datapeek" / "bad.py").write_text('''from datapeek import viewer
@viewer.register(name="Bad", extensions=[".bad"])
def render(path, options): pass
raise RuntimeError("broken import")
''')
        response, _, completed = self.call("discover")
        self.assertEqual({r['id'] for r in response['renderers']}, {"builtin:npy", "builtin:scientific", "workspace:good.py:render"})
        self.assertEqual(len(response["diagnostics"]), 1)
        self.assertIn('a user debug message', completed.stdout)
        response, _, _ = self.call(rendererId="workspace:good.py:render")
        self.assertEqual(response["status"], "ok", response)

    def test_missing_dependency(self):
        (self.project / ".datapeek" / "missing.py").write_text('''from datapeek import viewer
@viewer.register(name="Missing", extensions=[".npy"])
def render(path, options):
    import datapeek_nonexistent_dependency
''')
        response, _, _ = self.call(rendererId="workspace:missing.py:render")
        self.assertEqual(response["error"]["code"], "DEPENDENCY_MISSING")

    def test_wrong_result_and_output_limit(self):
        (self.project / ".datapeek" / "wrong.py").write_text('''from datapeek import viewer
@viewer.register(name="Wrong", extensions=[])
def render(path, options): return "raw html"
''')
        response, _, _ = self.call(rendererId="workspace:wrong.py:render")
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_RESULT")
        response, _, _ = self.call(limits={"maxArtifactBytes": 1})
        self.assertEqual(response["error"]["code"], "OUTPUT_TOO_LARGE")

    def test_protocol_version(self):
        response, _, _ = self.call(protocolVersion=99)
        self.assertEqual(response["error"]["code"], "PROTOCOL_ERROR")

    def test_sampling_bounds(self):
        sys.path.insert(0, str(RUNNER.parent))
        from datapeek.builtin import render_npy
        np.save(self.target, np.arange(50001))
        fig = render_npy(self.target, {})
        xs = fig.axes[0].lines[0].get_xdata()
        self.assertEqual(len(xs), 20000)
        self.assertEqual((xs[0], xs[-1]), (0, 50000))
        self.assertIn('sampled preview', fig.axes[0].get_title())
        np.save(self.target, np.zeros((1200, 1300)))
        fig = render_npy(self.target, {})
        self.assertEqual(fig.axes[0].images[0].get_array().shape, (1024, 1024))

    def test_custom_array_reader_quick_preview_and_discovery(self):
        (self.project / '.datapeek' / 'reader.py').write_text("from datapeek import viewer\n@viewer.reader(name='Custom array',extensions=['.npy'])\ndef read(path,options):\n import numpy as np\n return np.load(path,mmap_mode='r')\n")
        response,_,_=self.call('discover')
        renderer=next(r for r in response['renderers'] if r['id']=='workspace:reader.py:read')
        self.assertEqual(renderer['kind'],'array')
        self.assertTrue(renderer['matches'])
        response,_,_=self.call(rendererId='workspace:reader.py:read')
        self.assertEqual(response['status'],'ok',response)


if __name__ == '__main__':
    unittest.main()
