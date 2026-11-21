import os, sys, json, time
from playwright.sync_api import sync_playwright
"""Capture screenshots of all 11 pages at desktop/tablet/mobile and measure horizontal overflow + Streamlit exceptions.
Usage: python scripts/release_screenshots.py http://localhost:8501 <output_dir> sample_data/retail_sales_messy.csv   (env CHROMIUM_PATH optional; VP=mobile,tablet to limit viewports)
"""
URL = sys.argv[1]; OUT = sys.argv[2]; UPLOAD = sys.argv[3]
PAGES = ["Data Upload & Preview","Data Preparation","Automatic EDA","KPI Dashboard","Interactive Dashboard",
         "Visualizations","Correlation","Outlier Detection","Ask Your Data","Dataset Comparison","Export & Reporting"]
VPS = {"desktop":(1440,900,False),"tablet":(820,1100,True),"mobile":(390,844,True)}
if os.environ.get("VP"): VPS={k:v for k,v in VPS.items() if k in os.environ["VP"].split(",")}
OVERFLOW = """() => { const de=document.documentElement; const main=document.querySelector('[data-testid="stMain"]')||de;
 const bad=[]; const vw=window.innerWidth;
 document.querySelectorAll('[data-testid="stMain"] *').forEach(e=>{const r=e.getBoundingClientRect(); if(r.width>0 && r.right>vw+2){ let p=e.parentElement, scroll=false; while(p&&p!==document.body){const o=getComputedStyle(p).overflowX; if((o==='auto'||o==='scroll'||o==='hidden') && p.getBoundingClientRect().right<=vw+2){scroll=true;break} p=p.parentElement} if(!scroll) bad.push((e.tagName+'.'+(e.className||'').toString().slice(0,30)+' r='+Math.round(r.right)))}});
 return {scrollW:de.scrollWidth, vw, mainScrollW: main.scrollWidth, mainClient: main.clientWidth, bad: bad.slice(0,5), nbad: bad.length}; }"""
ERRS = """() => [...document.querySelectorAll('[data-testid="stException"], [data-testid="stAlertContainer"] .stException')].map(e=>e.innerText.slice(0,300))"""
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(**({"executable_path": os.environ["CHROMIUM_PATH"]} if os.environ.get("CHROMIUM_PATH") else {}), headless=True,
        args=["--no-sandbox","--disable-gpu","--no-zygote","--disable-dev-shm-usage"])
    for vp,(w,h,mob) in VPS.items():
        ctx = b.new_context(viewport={"width":w,"height":h}, is_mobile=mob, has_touch=mob)
        page = ctx.new_page(); console=[]
        page.on("console", lambda m: console.append(m.text[:200]) if m.type=="error" else None)
        page.on("pageerror", lambda e: console.append("PAGEERR "+str(e)[:200]))
        page.goto(URL); page.wait_for_selector("text=AnalyticsPro", timeout=30000); time.sleep(2)
        if mob or w<900:
            # open sidebar to upload
            btn = page.locator('[data-testid="stExpandSidebarButton"]')
            if btn.count() and btn.first.is_visible(): btn.first.click(); time.sleep(1)
        page.locator('input[type="file"]').first.set_input_files(UPLOAD)
        page.wait_for_selector("text=Active:", timeout=40000); time.sleep(2.5)
        for i,name in enumerate(PAGES,1):
            if mob or w<=768:
                if page.locator('[data-testid="stSidebar"]').first.get_attribute("data-collapsed")=="true":
                    page.locator('[data-testid="stExpandSidebarButton"]').first.click(); time.sleep(1.2)
            page.locator(f'[data-testid="stSidebar"] button:has-text("{name}")').first.click()
            time.sleep(4)
            if mob or w<=768:
                cb = page.locator('[data-testid="stSidebarCollapseButton"] button')
                if cb.count() and cb.first.is_visible(): cb.first.click(); time.sleep(1.2)
            ov = page.evaluate(OVERFLOW); ex = page.evaluate(ERRS)
            fn = f"{OUT}/{vp}_{i:02d}_{name.split()[0].lower()}.png"
            page.screenshot(path=fn, full_page=False)
            sh = page.evaluate("() => { const m=document.querySelector('[data-testid=\"stMain\"]'); return m? m.scrollHeight : document.documentElement.scrollHeight }")
            page.set_viewport_size({"width":w,"height":min(max(h,sh+10),7000)}); time.sleep(1.5)
            page.screenshot(path=fn.replace(".png","_full.png"))
            page.set_viewport_size({"width":w,"height":h}); time.sleep(0.5)
            res[f"{vp}|{name}"] = {"overflow": ov, "exceptions": ex}
        res[f"{vp}|console"] = console[:10]
        ctx.close()
    b.close()
json.dump(res, open(f"{OUT}/results.json","w"), indent=1)
for k,v in res.items():
    if k.endswith("console"): print(k, v); continue
    o=v["overflow"]; print(f'{k:42s} scrollW={o["scrollW"]}/{o["vw"]} main={o["mainScrollW"]}/{o["mainClient"]} nbad={o["nbad"]} exc={len(v["exceptions"])}', o["bad"][:2] if o["nbad"] else "")
