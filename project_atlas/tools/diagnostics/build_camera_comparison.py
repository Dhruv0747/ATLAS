"""Render identical captured bytes under extracted V1 and V2 camera CSS.

This is a layout fixture, not a reconstruction of historical lighting/focus.
"""
import argparse
import base64
from pathlib import Path
import re

p=argparse.ArgumentParser();p.add_argument('--frame',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():p.error('new output required')
root=Path(__file__).resolve().parents[2]
v1=(root/'scripts/atlas_status_web.py').read_text(encoding='utf-8')
v2=(root/'web/v2/glass.css').read_text(encoding='utf-8')
s1=next(x for x in re.findall(r'\.camera\{([^}]+)\}',v1) if 'height:min(56vh,560px)' in x)
s2=re.search(r'\.camera\{([^}]+)\}',v2).group(1)
uri='data:image/jpeg;base64,'+base64.b64encode(a.frame.read_bytes()).decode()
html=f'''<!doctype html><meta charset="utf-8"><title>ATLAS same-frame comparison</title>
<style>body{{background:#071522;color:white;font:16px system-ui}}main{{display:flex;gap:20px}}section{{width:48%}}.v1{{{s1}}}.v2{{{s2}}}</style>
<h1>Same original JPEG · V1 vs V2 rendering</h1><p>Read-only CSS comparison fixture. Identical image bytes. Not historical lighting or focus.</p>
<main><section><h2>Original V1 camera CSS</h2><img class="v1" src="{uri}"></section><section><h2>Glass V2 camera CSS</h2><img class="v2" src="{uri}"></section></main>'''
a.out.write_text(html,encoding='utf-8')
