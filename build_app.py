#!/usr/bin/env python3
"""Assembla il deliverable finale: un singolo index.html autonomo con
CSS, JS e dati demo incorporati (funziona anche aprendo il file senza
server web, senza fetch). Copia anche data/nba_stats.json accanto, così
l'app può essere servita con un server e usare il JSON esterno (che il
workflow GitHub Actions aggiornerà)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = ROOT  # index.html, style.css, app.js alla radice del repo
DATA = os.path.join(ROOT, "data", "nba_stats.json")
OUTDIR = os.path.join(ROOT, "download", "nba-advanced-stats")
os.makedirs(OUTDIR, exist_ok=True)

html = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
css = open(os.path.join(APP, "style.css"), encoding="utf-8").read()
js = open(os.path.join(APP, "app.js"), encoding="utf-8").read()
demo = open(DATA, encoding="utf-8").read()

# valida il JSON prima di incorporarlo
json.loads(demo)

# inline CSS
html = html.replace(
    '<link rel="stylesheet" href="style.css">',
    "<style>\n" + css + "\n</style>")

# inline JS: i dati demo diventano window.__DEMO_DATA__ (fallback senza server)
demo_block = "<script>window.__DEMO_DATA__ = " + demo + ";</script>\n"
html = html.replace(
    '<script src="app.js"></script>',
    demo_block + "<script>\n" + js + "\n</script>")

# il fetch punta al JSON nella stessa cartella (repo root / GitHub Pages)
html = html.replace('fetch("../data/nba_stats.json"', 'fetch("nba_stats.json"')

out = os.path.join(OUTDIR, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

# copia anche il JSON (per l'uso con un server locale / GitHub Pages)
with open(os.path.join(OUTDIR, "nba_stats.json"), "w", encoding="utf-8") as f:
    f.write(demo)

kb = os.path.getsize(out) / 1024
print(f"OK -> {out} ({kb:.0f} KB)")
print(f"OK -> {os.path.join(OUTDIR, 'nba_stats.json')}")
# controlli rapidi
assert "style.css" not in html and 'src="app.js"' not in html
assert "__DEMO_DATA__" in html
print("Controlli inline: superati")
