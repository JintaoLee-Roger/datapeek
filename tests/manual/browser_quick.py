"""Real Chromium Canvas/CSP test for generated quick-preview fixture pages."""
import asyncio
import json
import re
import base64
import zlib
import hashlib
import numpy as np
from pathlib import Path
import sys
from playwright.async_api import async_playwright

async def main():
    root=Path(sys.argv[1]);results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--allow-file-access-from-files'])
        for path in sorted(root.glob('*.html')):
            page=await browser.new_page(viewport=dict(width=1440,height=1000))
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.add_init_script('window.actions=[];window.acquireVsCodeApi=()=>({postMessage:m=>window.actions.push(m)});')
            await page.goto(path.as_uri())
            await page.wait_for_function('() => window.datapeekQuickReady')
            result=await page.evaluate('''()=>({name:document.getElementById('title').textContent,...window.datapeekQuickReady,canvases:[...document.querySelectorAll('.image')].map(c=>({width:c.width,height:c.height,visible:c.getContext('2d').getImageData(0,0,c.width,c.height).data.some(v=>v!==0)}))})''')
            assert all(c['visible'] for c in result['canvases']),result
            payload=json.loads(re.search(r'const data=(.*);',path.read_text()).group(1))
            if payload['panels']:
                lut=np.frombuffer(base64.b64decode(payload['lut']),dtype='uint8').reshape(256,4)
                expected=[]
                for panel in payload['panels']:
                    raw=base64.b64decode(panel['pixels'])
                    if panel.get('compressed'):raw=zlib.decompress(raw)
                    rgba=lut[np.frombuffer(raw,dtype='uint8')].copy()
                    if panel['mask']:rgba[np.frombuffer(base64.b64decode(panel['mask']),dtype='uint8')==0,3]=0
                    # Canvas premultiplies transparent pixels, so their RGB reads back as zero.
                    rgba[rgba[:,3]==0,:]=0
                    expected.append(hashlib.sha256(rgba.tobytes()).hexdigest())
                hashes=await page.evaluate('''async()=>Promise.all([...document.querySelectorAll('.image')].map(async c=>{const b=c.getContext('2d').getImageData(0,0,c.width,c.height).data;const h=await crypto.subtle.digest('SHA-256',b);return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('');}))''')
                assert hashes==expected,'Canvas pixels differ from Python output'

            assert len(result['canvases'])==(3 if path.stem in ['baiyun','channels','volume_zarr'] else 1)
            await page.click('#detail');await page.click('#choose')
            assert await page.evaluate('window.actions')==[dict(action='detail'),dict(action='chooseReader')]
            await page.mouse.wheel(0,-500);await page.set_viewport_size(dict(width=800,height=700))
            assert await page.evaluate('window.actions.length')==2
            assert not errors,errors
            if path.stem in ('ridgecrest','baiyun'):await page.screenshot(path=str(root/(path.stem+'.png')))
            results.append(result);await page.close()
        await browser.close()
    (root/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
asyncio.run(main())
