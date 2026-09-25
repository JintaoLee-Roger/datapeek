"""Persistent lazy reader for detailed views. No complete 3D volume conversion."""
import base64
from collections import OrderedDict
from contextlib import ExitStack
import math
from pathlib import Path
import threading
import time

import numpy as np

from .colors import color_limits, petrel_colorscale
from .sampling import budget_bytes, estimate
from .sources import open_array
from .scientific import integer

AXES = ('iline', 'xline', 'time')


class DetailSession:
    def __init__(self, path, options, cache_bytes=128 * 1024**2, renderer_id=None, workspace_root=None, reader_paths=None):
        self.stack = ExitStack()
        try:
            self.data, self.options, self.title, self.time_axis, self.dt = self.stack.enter_context(open_array(Path(path), options, renderer_id, workspace_root, reader_paths))
            self.shape = tuple(self.data.shape)
            if len(self.shape) not in (1, 2, 3) or min(self.shape) < 1 or np.dtype(self.data.dtype).kind not in 'biuf':
                raise ValueError('Detailed view supports nonempty real 1D, 2D or 3D data')
        except Exception:
            self.stack.close()
            raise
        self.cache_bytes = cache_bytes
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.server = None

    def close(self):
        if self.server:
            self.server.stop()
            self.server = None
        self.cache.clear()
        self.stack.close()

    def info(self):
        try:
            palettes = {'Petrel': petrel_colorscale()}
        except ImportError:
            palettes = {}  # cigvis remains optional for the ordinary 2D viewer.
        return dict(colorscales=palettes, shape=self.shape, dtype=str(self.data.dtype), nbytes=math.prod(self.shape)*np.dtype(self.data.dtype).itemsize, title=self.title, volume=len(self.shape)==3,
                    defaults={k: v for k, v in self.options.items() if k in (*AXES, 'slices', 'vmin', 'vmax', 'clip_percentile', 'cmap', 'large_volume_gb', 'preserve_aspect', 'aspect_ratio')})

    def read(self, key):
        read = self.data.read_region if hasattr(self.data, 'read_region') else self.data.__getitem__
        with self.lock:
            return np.array(read(tuple(key)), copy=True)

    def full_slice(self, axis, index):
        key = (axis, index)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            selection = [slice(None)] * 3
            selection[axis] = index
            values = self.read(selection)
            if values.nbytes <= self.cache_bytes:
                while self.cache and sum(a.nbytes for a in self.cache.values()) + values.nbytes > self.cache_bytes:
                    self.cache.popitem(last=False)
                self.cache[key] = values
            return values

    def sample(self, request):
        started = time.perf_counter()
        resolution = request.get('resolution', 768)
        if isinstance(resolution, bool) or not isinstance(resolution, int) or not 64 <= resolution <= 1536:
            raise ValueError('resolution must be 64–1536')
        ndim = len(self.shape)
        axis_name = request.get('axis', 'iline')
        if ndim == 3 and axis_name not in AXES:
            raise ValueError('Unknown slice direction')
        axis = AXES.index(axis_name) if ndim == 3 else None
        index = integer(request, 'index', self.shape[axis]//2, self.shape[axis]) if ndim == 3 else None
        if ndim == 3:
            xdim, ydim = ((1, 2), (0, 2), (1, 0))[axis]
            xlabel, ylabel = AXES[xdim], AXES[ydim]
            xscale = 1.0
        elif ndim == 2:
            xdim, ydim = self.time_axis, 1-self.time_axis
            xscale = float(self.dt or 1)
            xlabel, ylabel = (('Time (s)' if self.dt else 'Time index') if self.options.get('kind')=='das' else self.options.get('xlabel','Column index')), ('Channel index' if self.options.get('kind')=='das' else self.options.get('ylabel','Row index'))
        else:
            xdim, ydim, xscale, xlabel, ylabel = 0, None, 1.0, 'Sample index', 'Value'
        nx, ny = self.shape[xdim], self.shape[ydim] if ydim is not None else 1
        def interval(value, size, scale=1):
            if value is None:
                return 0, size
            if not isinstance(value, list) or len(value)!=2 or any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) for x in value):
                raise ValueError('View ranges must contain two finite numbers')
            a,b = sorted(x/scale for x in value)
            lo, hi = max(0, min(size-1, math.floor(a))), max(1, min(size, math.ceil(b)+1))
            return lo, max(lo+1,hi)
        xlo,xhi = interval(request.get('xrange'), nx, xscale)
        ylo,yhi = interval(request.get('yrange'), ny) if ndim>1 else (0,1)
        xs = max(1, math.ceil((xhi-xlo)/resolution))
        ys = max(1, math.ceil((yhi-ylo)/resolution))
        sx,sy = slice(xlo,xhi,xs),slice(ylo,yhi,ys)
        if ndim==3:
            region = request.get('xrange') is not None or request.get('yrange') is not None
            if region and (axis, index) not in self.cache:
                selection = [slice(None)] * 3
                selection[axis], selection[xdim], selection[ydim] = index, sx, sy
                values = self.read(selection)
                if axis < 2:
                    values = values.T
            else:
                full = self.full_slice(axis,index)
                oriented = full.T if axis<2 else full
                values = oriented[sy,sx].copy()
        else:
            selection = [slice(None)] * ndim
            selection[xdim] = sx
            if ydim is not None:
                selection[ydim] = sy
            # A large compressed DAS overview may touch far more data than its output.
            # Refine sampling before issuing the I/O; small zoomed regions stay full resolution.
            budget = budget_bytes(self.options)
            while estimate(self.data, selection) > budget:
                candidates = [i for i,k in enumerate(selection) if len(range(*k.indices(self.shape[i])))>1]
                if not candidates:
                    raise ValueError('One compressed chunk exceeds max_read_mib; increase the budget or use smaller chunks')
                dim=max(candidates,key=lambda i: len(range(*selection[i].indices(self.shape[i]))))
                k=selection[dim]; selection[dim]=slice(k.start,k.stop,(k.step or 1)*2)
            xs=selection[xdim].step
            if ydim is not None: ys=selection[ydim].step
            values = self.read(selection)
            if ndim==2 and self.time_axis==0:
                values = values.T
        clim_options = {**self.options, **{k: request[k] for k in ('vmin','vmax','clip_percentile') if k in request}}
        low, high = color_limits(values, clim_options)
        values = np.asarray(values,dtype='<f4',order='C')
        # Nonfinite values are converted to null in the webview.
        return dict(kind='line' if ndim==1 else 'heatmap', shape=values.shape,
                    data=base64.b64encode(values.tobytes()).decode('ascii'),
                    x0=xlo*xscale, dx=xs*xscale, y0=ylo, dy=ys,
                    xbounds=[0,(nx-1)*xscale], ybounds=[0,ny-1], displayAspect=nx/ny if ndim!=1 else 2,
                    xlabel=xlabel,ylabel=ylabel,vmin=low,vmax=high,
                    axis=axis_name,index=index, seconds=time.perf_counter()-started,
                    sampled=xs>1 or ys>1, title=self.title)

    def start_viser(self, request):
        if len(self.shape)!=3:
            raise ValueError('3D viewing requires a three-dimensional volume')
        if self.server:
            return {'port': self.server.get_port()}
        from cigvis import viserplot
        from cigvis.visernodes import Server
        import cigvis
        cigvis.set_order(True)
        axis_name = request.get('axis','iline')
        if axis_name not in AXES:
            raise ValueError('Unknown axis')
        axis = AXES.index(axis_name)
        index = integer(request,'index',self.shape[axis]//2,self.shape[axis])
        preview = [] if request.get('vmin') is not None and request.get('vmax') is not None else self.full_slice(axis,index)
        low,high = color_limits(preview,{**self.options,**{k:request[k] for k in ('vmin','vmax','clip_percentile') if k in request}})
        owner = self
        class LazyVolume:
            shape = owner.shape
            ndim = 3
            dtype = np.dtype(owner.data.dtype)
            def __getitem__(self,key):
                if not isinstance(key,tuple) or len(key)!=3 or sum(isinstance(k,(int,np.integer)) for k in key)!=1:
                    raise ValueError('3D viewer must request a single slice')
                fixed = next(i for i,k in enumerate(key) if isinstance(k,(int,np.integer)))
                plane = owner.full_slice(fixed,int(key[fixed]))
                return plane[tuple(k for i,k in enumerate(key) if i!=fixed)]
        pos = {name: [] for name in ('x','y','z')}
        # Respect the large-volume default on first opening; sliders handle the active direction.
        selected = request.get('slices') or self.options.get('slices') or (['iline'] if math.prod(self.shape)*self.data.dtype.itemsize>1.5e9 else list(AXES))
        for name in selected:
            if name not in AXES:
                raise ValueError('Invalid 3D slice direction')
            dim=AXES.index(name)
            position = request.get('positions',{}).get(name, index if dim==axis else self.shape[dim]//2)
            pos[('x','y','z')[dim]] = [integer({'position':position},'position',self.shape[dim]//2,self.shape[dim])]
        nodes = viserplot.create_slices(LazyVolume(),pos=pos,clim=[low,high],cmap=request.get('cmap','gray'))
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        server = Server(host='127.0.0.1',port=port,label='DataPeek · '+self.title,verbose=False)
        try:
            viserplot.plot3D(nodes,server=server,run_app=False)
        except Exception:
            server.stop()
            raise
        self.server=server
        return {'port':server.get_port()}
