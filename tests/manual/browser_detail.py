"""Run after node tests/manual/detail_fixture.cjs; requires Playwright Chromium."""
import asyncio
from pathlib import Path
import sys
import re

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from datapeek.detail import DetailSession
from playwright.async_api import async_playwright

async def main():
    fixture=Path(sys.argv[1])
    session=DetailSession(Path('/home/jtli/data/seismic/seismic_data/baiyun/sx_cut.npy'),{})
    actions=[]
    errors=[]
    sample_gate=asyncio.Event();sample_gate.set()
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--allow-file-access-from-files','--enable-unsafe-swiftshader'])
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        async def host(message):
            actions.append(message)
            if message['action']=='sample':
                await sample_gate.wait()
                result=await asyncio.to_thread(session.sample,message['options'])
                result['region']=message['options'].get('region',False)
                result['clientRequest']=message['options'].get('clientRequest')
                if result['region']:result['view']={k:message['options'][k] for k in ('xrange','yrange') if k in message['options']}
                await page.evaluate('(result)=>window.dispatchEvent(new MessageEvent("message",{data:{type:"sample",result}}))',result)
        await page.expose_function('postToHost',host)
        await page.add_init_script('window.acquireVsCodeApi=()=>({postMessage:message=>window.postToHost(message)});')
        try:
            await page.goto((fixture/'index.html').as_uri())
            await page.wait_for_function('() => document.getElementById("plot").data?.length===1')
            await page.wait_for_function('() => document.getElementById("status").textContent === ""')
            original_limits=await page.evaluate('document.getElementById("plot").data.map(t=>[t.zmin,t.zmax])')
            # Hold a real slice request open and inspect every frame, not just its endpoints.
            await page.wait_for_timeout(150)
            await page.evaluate("""()=>{
                window.layoutSamples=[];window.recordLayout=true;
                const sample=()=>{const p=document.getElementById('plot'),r=p.getBoundingClientRect();
                    window.layoutSamples.push([r.x,r.y,r.width,r.height,p._fullLayout._size.w,p._fullLayout._size.h]);
                    if(window.recordLayout)requestAnimationFrame(sample);};sample();
            }""")
            sample_gate.clear()
            previous_index=int(await page.locator('#index').input_value())
            await page.fill('#index',str(previous_index+1));await page.locator('#index').press('Tab')
            await page.wait_for_function('() => document.getElementById("status").textContent === "Reading slice…"')
            await page.wait_for_timeout(200)
            sample_gate.set()
            await page.wait_for_function('() => document.getElementById("status").textContent === "" && !document.getElementById("apply").disabled')
            await page.wait_for_timeout(150)
            # Long errors must also stay within the reserved status area.
            await page.evaluate("""()=>window.dispatchEvent(new MessageEvent('message',{data:{type:'error',message:'A long reader error. '.repeat(80)}}))""")
            await page.wait_for_timeout(150)
            samples=await page.evaluate('() => {window.recordLayout=false;return window.layoutSamples;}')
            assert len(samples)>5
            assert all(abs(a-b)<.1 for row in samples for a,b in zip(row,samples[0])),samples
            assert await page.locator('#status').get_attribute('title'), 'Full error should remain accessible'
            await page.evaluate("""()=>window.dispatchEvent(new MessageEvent('message',{data:{type:'viserStopped'}}))""")

            before_resize=await page.evaluate('JSON.stringify(document.getElementById("plot").data)')
            read_count=sum(m['action']=='sample' for m in actions)
            for width,height in [(800,700),(1200,500),(1200,280),(480,900),(1440,1000)]:
                await page.set_viewport_size(dict(width=width,height=height))
                await page.wait_for_timeout(150)
                ratio=await page.evaluate('(()=>{const s=document.getElementById("plot")._fullLayout._size;return s.w/s.h;})()')
                assert abs(ratio-session.shape[1]/session.shape[2])<.01,ratio
                bounds=await page.evaluate('''()=>{const p=document.getElementById('plot').getBoundingClientRect(),f=document.getElementById('plotFrame').getBoundingClientRect();return {fits:p.left>=f.left-1&&p.right<=f.right+1&&p.top>=f.top-1&&p.bottom<=f.bottom+1,visible:p.bottom<=innerHeight};}''')
                assert bounds['fits'] and bounds['visible'],bounds
                assert await page.evaluate('JSON.stringify(document.getElementById("plot").data)')==before_resize
            assert sum(m['action']=='sample' for m in actions)==read_count,'Resize reread data'

            await page.uncheck('#preserveAspect')
            await page.fill('#aspectRatio','1.5');await page.locator('#aspectRatio').press('Tab')
            await page.wait_for_timeout(150)
            ratio=await page.evaluate('(()=>{const s=document.getElementById("plot")._fullLayout._size;return s.w/s.h;})()')
            assert abs(ratio-1.5)<.01,ratio
            assert sum(m['action']=='sample' for m in actions)==read_count
            assert await page.evaluate('JSON.stringify(document.getElementById("plot").data)')==before_resize
            assert any(m['action']=='save' and m['options'].get('aspect_ratio')==1.5 for m in actions)
            await page.check('#preserveAspect')

            await page.select_option('#axis','xline')
            await page.wait_for_function('() => document.getElementById("plot").layout.xaxis.title.text==="iline"')
            assert await page.evaluate('document.getElementById("plot").data.map(t=>[t.zmin,t.zmax])')==original_limits,'Slice change reset color limits'
            count=sum(m['action']=='sample' for m in actions)
            await page.fill('#vmin','-0.25');await page.fill('#vmax','0.5');await page.click('#apply')
            await page.wait_for_function('() => document.getElementById("plot").data[0].zmin===-0.25 && document.getElementById("plot").data[0].zmax===0.5')
            assert sum(m['action']=='sample' for m in actions)==count,'Color change unexpectedly reread source'
            before=await page.evaluate('JSON.stringify(document.getElementById("plot").data)')
            old_status=await page.locator('#status').inner_text()
            for i in range(5):
                await page.evaluate('(i)=>Plotly.relayout(document.getElementById("plot"),{"xaxis.range":[10+i,20+i],"yaxis.range":[40,30]})',i)
            await page.wait_for_timeout(700)
            assert sum(m['action']=='sample' for m in actions)==count,'Zoom reread data'
            assert await page.evaluate('JSON.stringify(document.getElementById("plot").data)')==before,'Zoom changed image or limits'
            assert await page.locator('#status').inner_text()==old_status,'Zoom changed status'
            await page.click('#region')
            await page.wait_for_function('() => document.getElementById("plot").data[0].z.length===11 && document.getElementById("plot").data[0].z[0].length===11')
            assert sum(m['action']=='sample' for m in actions)==count+1
            count+=1
            assert await page.evaluate('document.getElementById("plot").layout.xaxis.range')==[14,24]
            assert await page.evaluate('document.getElementById("plot").data[0].zmin')==-.25
            await page.fill('#vmin','0');await page.fill('#vmax','1');await page.click('#apply')
            await page.select_option('#cmap','Petrel')
            await page.click('#apply')
            await page.wait_for_function('() => document.getElementById("plot").data[0].colorscale.length===256')
            assert await page.evaluate('document.getElementById("plot").data[0].colorscale')==session.info()['colorscales']['Petrel']
            assert sum(m['action']=='sample' for m in actions)==count,'Petrel reread data'
            await page.click('#reset')
            await page.wait_for_timeout(300)
            assert sum(m['action']=='sample' for m in actions)==count,'Reset reread data'
            await page.screenshot(path=str(fixture/'detail.png'))
            await page.fill('#index','999999');await page.locator('#index').press('Tab')
            await page.wait_for_timeout(100)
            assert await page.locator('#index').input_value()==str(session.shape[1]//2),'Invalid index did not restore shown slice'
            await page.click('#defaults')
            await page.wait_for_function('() => document.getElementById("plot").layout.xaxis.title.text==="xline" && !document.getElementById("apply").disabled')
            assert await page.evaluate('document.getElementById("plot").data[0].colorscale.length')==2,'Defaults did not restore gray'
            await page.click('#quick')
            await page.wait_for_timeout(100)
            assert actions[-1]['action']=='quick'
            assert not errors,errors
            print('Browser checks passed: fixed limits across slice changes; zoom/reset preserve image without reads; manual color; quick button.')
            result=await asyncio.to_thread(session.start_viser,{'axis':'iline','index':256,'slices':['iline','xline','time'],'cmap':'Petrel','vmin':0,'vmax':1})
            viewer=await browser.new_page()
            embedded=re.sub(r'http://127\.0\.0\.1:\d+', 'http://127.0.0.1:'+str(result['port']), (fixture/'3d.html').read_text())
            (fixture/'3d-live.html').write_text(embedded)
            await viewer.add_init_script('window.acquireVsCodeApi=()=>({postMessage:()=>{}});')
            await viewer.goto((fixture/'3d-live.html').as_uri())
            await viewer.frame_locator('iframe').locator('canvas').first.wait_for(timeout=30000)
            await viewer.wait_for_timeout(2000)
            assert session.server.get_clients(),'Viser WebSocket not connected'
            await viewer.screenshot(path=str(fixture/'viser.png'))
            print('Viser browser canvas loaded:',result['port'])
        finally:
            await browser.close()
            session.close()

asyncio.run(main())
