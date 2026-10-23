"""Accessible standalone HTML report; no network requests or external assets."""
import html
import json
from pathlib import Path

TITLES={'apac_procurement':('01 / APAC','Procurement exceptions'),
        'emea_payables':('02 / EMEA','Payables aging'),
        'americas_close':('03 / AMERICAS','Month-end journal controls')}


def write_report(report,path):
    sections=[]
    for name,results in report['scenarios'].items():
        region,title=TITLES[name]
        metrics={k:v for k,v in results.items() if k!='details'}
        selected=[r for r in results['details'] if r.get('exceptions') or r.get('balanced') is False
                  or r.get('bucket') in {'31_60','61_90','90_plus'}][:6]
        preview=html.escape(json.dumps(selected,indent=2))
        initial=report['runs'][name]['initial']
        sections.append(f'''<section><div class="eyebrow">{region}</div><h2>{title}</h2>
<p>{initial['rows_in']:,} incoming rows · {initial['quarantined']} quarantined · replay check passed</p>
<pre aria-label="Scenario metrics">{html.escape(json.dumps(metrics,indent=2))}</pre>
<details><summary>Inspect sample exceptions</summary><pre>{preview}</pre></details></section>''')
    owner=html.escape(report['owner'])
    document=f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{owner} | Oracle Fusion Portfolio</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f5f7;color:#16243a;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:56px 24px}}header{{background:#14253b;color:white;padding:40px;border-radius:20px}}h1{{font-size:clamp(30px,4.2vw,52px);line-height:1.12;max-width:850px}}header p{{color:#c8d6e8}}.eyebrow{{font-size:12px;letter-spacing:.14em;font-weight:750;color:#0e746e}}header .eyebrow{{color:#87ddd0}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:24px}}section{{background:white;border:1px solid #d6dfe8;border-radius:16px;padding:24px}}h2{{font-size:23px;line-height:1.25}}pre{{font:13px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#eff4f8;padding:16px;border-radius:10px}}summary{{cursor:pointer;font-weight:650}}.note{{padding:22px 0;color:#526176}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}header{{padding:28px}}}}</style></head><body><main><header>
<div class="eyebrow">{owner.upper()} / DATA ENGINEERING PORTFOLIO</div>
<h1>Oracle Fusion.<br>Three regions. Three data challenges.</h1>
<p>Procurement visibility, payable aging, and journal-close controls—built on a shared, replay-safe local pipeline.</p>
<p>Reference date: {html.escape(report['as_of'])} · Synthetic data · No live Oracle tenant connection</p></header>
<div class="grid">{''.join(sections)}</div><p class="note">Original portfolio implementation by {owner}, developed with AI-assisted tooling.
Regional cases are fictional business scenarios. Currency totals remain separate; no FX conversion, statutory compliance certification, or live production deployment is claimed.
Full row-level results are in summary.json; database lineage and rejects are stored in warehouse.sqlite.</p></main></body></html>'''
    Path(path).write_text(document+'\n')
