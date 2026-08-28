from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "use-cases.json"
PRODUCT = ROOT / "docs" / "product.html"
DEFAULT_OUTPUT = ROOT / "build" / "docs-site"

CSS = """
:root{color-scheme:light;--ink:#102126;--muted:#5e6e72;--line:#dce4e3;--soft:#f5f8f7;--accent:#0d655f;--max:1120px}
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:#fff;line-height:1.62}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px}.wrap{width:min(var(--max),calc(100% - 40px));margin:auto}.top{border-bottom:1px solid var(--line);background:#fff;position:sticky;top:0;z-index:5}.top .wrap{display:flex;gap:24px;align-items:center;min-height:64px}.brand{font-weight:800;color:var(--ink);text-decoration:none}.nav{margin-left:auto;display:flex;gap:18px;font-size:14px}.hero{padding:72px 0 48px;background:linear-gradient(180deg,#f7faf9 0,#fff 100%)}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:800}.hero h1{font-size:clamp(38px,6vw,70px);line-height:1.02;letter-spacing:-.045em;max-width:900px;margin:12px 0 20px}.hero p{font-size:20px;max-width:780px;color:var(--muted)}main{padding:44px 0 80px}h2{font-size:30px;letter-spacing:-.025em;margin:48px 0 16px}h3{font-size:20px;margin:0 0 8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}.card{border:1px solid var(--line);border-radius:16px;padding:22px;background:#fff}.card p{color:var(--muted);margin-bottom:0}.meta{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.pill{font-size:12px;border:1px solid var(--line);background:var(--soft);border-radius:999px;padding:5px 9px}.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:24px 0}.flow span{text-align:center;border:1px solid var(--line);border-radius:12px;padding:12px 8px;background:var(--soft);font-size:13px;font-weight:700}.code{background:#102126;color:#eaf5f1;border-radius:14px;padding:18px;overflow:auto;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}.note{border-left:4px solid #c58a24;background:#fff9ed;padding:14px 18px;margin:20px 0}.ok{border-left-color:var(--accent);background:#f2faf7}.cols{display:grid;grid-template-columns:1fr 1fr;gap:28px}.list{padding-left:20px}.breadcrumb{font-size:13px;color:var(--muted);margin-bottom:24px}.faq details{border-top:1px solid var(--line);padding:16px 0}.faq summary{font-weight:750;cursor:pointer}.faq p{color:var(--muted);max-width:850px}.footer{border-top:1px solid var(--line);padding:28px 0 48px;color:var(--muted);font-size:13px}@media(max-width:760px){.nav{display:none}.flow{grid-template-columns:1fr}.cols{grid-template-columns:1fr}.hero{padding-top:48px}.wrap{width:min(var(--max),calc(100% - 28px))}}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def load_data() -> dict:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    use_cases = data.get("use_cases")
    if not isinstance(use_cases, list) or not 8 <= len(use_cases) <= 10:
        raise ValueError("docs/use-cases.json must contain 8-10 use cases")
    slugs: set[str] = set()
    titles: set[str] = set()
    for item in use_cases:
        for field in ("slug", "title", "description", "problem", "spec", "command", "limitations", "repo_guide"):
            if not item.get(field):
                raise ValueError(f"use case missing {field}: {item}")
        if item["slug"] in slugs or item["title"] in titles:
            raise ValueError(f"duplicate use case identity: {item['slug']}")
        slugs.add(item["slug"]); titles.add(item["title"])
        for path_field in ("spec", "repo_guide"):
            if not (ROOT / item[path_field]).exists():
                raise ValueError(f"use case {item['slug']} references missing {path_field}: {item[path_field]}")
        if not str(item["command"]).startswith("rac run "):
            raise ValueError(f"use case {item['slug']} must expose a runnable rac command")
    faq = data.get("faq")
    if not isinstance(faq, list) or len(faq) < 5:
        raise ValueError("FAQ requires at least five questions")
    return data


def head(title: str, description: str, canonical: str, *, structured: dict | None = None) -> str:
    ld = ""
    if structured is not None:
        ld = f'<script type="application/ld+json">{json.dumps(structured, ensure_ascii=False)}</script>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:type" content="article"><style>{CSS}</style>{ld}</head><body>"""


def nav(base: str) -> str:
    return f'<header class="top"><div class="wrap"><a class="brand" href="{esc(base)}">Reconciliation as Code</a><nav class="nav"><a href="{esc(urljoin(base,"use-cases/"))}">Use cases</a><a href="{esc(urljoin(base,"faq/"))}">FAQ</a><a href="https://github.com/dkharlanau/reconciliation-as-code">GitHub</a></nav></div></header>'


def footer() -> str:
    return '<footer class="footer"><div class="wrap">Synthetic public examples. Reconciliation evidence proves only the scope and rules declared by the contract.</div></footer></body></html>'


def page_use_case(item: dict, data: dict) -> str:
    base = data["base_url"]
    canonical = urljoin(base, f'use-cases/{item["slug"]}/')
    structured = {"@context":"https://schema.org","@type":"TechArticle","headline":item["title"],"description":item["description"],"url":canonical,"author":{"@type":"Person","name":"Dzmitryi Kharlanau"},"isPartOf":{"@type":"WebSite","name":"Reconciliation as Code","url":base}}
    controls = ''.join(f'<li>{esc(x)}</li>' for x in item["controls"])
    inputs = ''.join(f'<li>{esc(x)}</li>' for x in item["inputs"])
    outputs = ''.join(f'<li>{esc(x)}</li>' for x in item["outputs"])
    related = [x for x in data["use_cases"] if x["slug"] != item["slug"]][:3]
    related_html = ''.join(f'<article class="card"><h3><a href="../{esc(x["slug"])}/">{esc(x["title"])}</a></h3><p>{esc(x["description"])}</p></article>' for x in related)
    return head(item["title"] + " | Reconciliation as Code", item["description"], canonical, structured=structured) + nav(base) + f"""
<section class="hero"><div class="wrap"><div class="eyebrow">Executable use case</div><h1>{esc(item['title'])}</h1><p>{esc(item['description'])}</p><div class="meta"><span class="pill">Source-backed example</span><span class="pill">Deterministic evidence</span><span class="pill">Vendor-neutral runtime</span></div></div></section>
<main><div class="wrap"><div class="breadcrumb"><a href="../">Use cases</a> / {esc(item['title'])}</div>
<h2>The problem</h2><p>{esc(item['problem'])}</p>
<div class="flow"><span>Inputs</span><span>Versioned spec</span><span>Execute</span><span>Evidence</span><span>Decision</span></div>
<div class="cols"><section><h2>Inputs</h2><ul class="list">{inputs}</ul></section><section><h2>What the contract controls</h2><ul class="list">{controls}</ul></section></div>
<h2>Run the repository example</h2><p>The page points to a checked-in synthetic example; the same command is suitable for local review or CI.</p><pre class="code">{esc(item['command'])}</pre><p><a href="https://github.com/dkharlanau/reconciliation-as-code/blob/main/{esc(item['spec'])}">Open the specification</a> · <a href="https://github.com/dkharlanau/reconciliation-as-code/blob/main/{esc(item['repo_guide'])}">Open source guide/artifact</a></p>
<h2>Evidence you get</h2><ul class="list">{outputs}</ul>
<div class="note"><strong>Limitations.</strong> {esc(item['limitations'])}</div>
<h2>How to adapt it</h2><p>Replace the synthetic inputs, then explicitly define scope, authoritative business keys, identity changes, comparison rules, tolerances, critical fields, accepted-exception governance and the release decision that will consume the evidence. Keep missing proof visible rather than weakening the controls to force a green result.</p>
<h2>Related reconciliation patterns</h2><div class="grid">{related_html}</div>
</div></main>""" + footer()


def page_index(data: dict) -> str:
    base = data["base_url"]
    canonical = urljoin(base, "use-cases/")
    cards = ''.join(f'<article class="card"><h3><a href="{esc(x["slug"])}/">{esc(x["title"])}</a></h3><p>{esc(x["description"])}</p></article>' for x in data["use_cases"])
    return head("Reconciliation use cases | Reconciliation as Code", "Runnable source-to-target, SAP S/4HANA, cutover, CSV and control-total reconciliation patterns with explicit evidence boundaries.", canonical) + nav(base) + f'<section class="hero"><div class="wrap"><div class="eyebrow">Problem-first documentation</div><h1>Reconciliation patterns you can run</h1><p>Start from the business assurance problem, not the feature list. Every page maps to a checked-in synthetic contract and an executable command.</p></div></section><main><div class="wrap"><div class="grid">{cards}</div><div class="note ok"><strong>Evidence rule.</strong> These examples show reusable control patterns. They do not claim that a synthetic pass or failure represents your production landscape.</div></div></main>' + footer()


def page_faq(data: dict) -> str:
    base = data["base_url"]
    canonical = urljoin(base, "faq/")
    parts=[]; entities=[]
    for q,a in data["faq"]:
        parts.append(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>')
        entities.append({"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}})
    structured={"@context":"https://schema.org","@type":"FAQPage","mainEntity":entities}
    return head("Data reconciliation FAQ | Reconciliation as Code", "Practical answers about migration reconciliation, changed IDs, cutover sign-off, SQL inputs and large datasets.", canonical, structured=structured)+nav(base)+f'<section class="hero"><div class="wrap"><div class="eyebrow">FAQ</div><h1>Data reconciliation: practical questions</h1><p>Short answers grounded in the contracts and evidence model implemented by Reconciliation as Code.</p></div></section><main><div class="wrap faq">{"".join(parts)}</div></main>'+footer()


def build(output: Path) -> None:
    data=load_data(); base=data["base_url"]
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copy2(PRODUCT, output/"index.html")
    uc=output/"use-cases"; uc.mkdir()
    (uc/"index.html").write_text(page_index(data),encoding="utf-8")
    for item in data["use_cases"]:
        target=uc/item["slug"]; target.mkdir(); (target/"index.html").write_text(page_use_case(item,data),encoding="utf-8")
    faq=output/"faq"; faq.mkdir(); (faq/"index.html").write_text(page_faq(data),encoding="utf-8")
    urls=[base,urljoin(base,"use-cases/"),urljoin(base,"faq/")]+[urljoin(base,f'use-cases/{x["slug"]}/') for x in data["use_cases"]]
    (output/"robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {urljoin(base,'sitemap.xml')}\n",encoding="utf-8")
    sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'<url><loc>{esc(u)}</loc></url>\n' for u in urls)+'</urlset>\n'
    (output/"sitemap.xml").write_text(sitemap,encoding="utf-8")
    manifest={"pages":len(urls),"use_cases":len(data["use_cases"]),"urls":urls}
    (output/"site-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")


def main()->int:
    parser=argparse.ArgumentParser(description="Build static, source-backed Reconciliation as Code documentation pages.")
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args(); build(args.output.resolve()); print(json.dumps({"output":str(args.output),"status":"built"})); return 0

if __name__=="__main__": raise SystemExit(main())
