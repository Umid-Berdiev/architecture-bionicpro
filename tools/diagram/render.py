"""Render every page of a draw.io file to PNG with headless Google Chrome.

There is no draw.io CLI on this machine, so each page is embedded into a small HTML
document that loads the public diagrams.net viewer script, and Chrome takes a screenshot
of it. The window size is derived from the page's geometry so nothing is clipped.

Usage: python3 tools/diagram/render.py <file.drawio> <out-prefix>
       -> <out-prefix>.png for a single page, <out-prefix>-<page-name>.png otherwise
"""
import html
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCALE = 1.5          # device scale factor: crisp text without a huge file
MARGIN = 40          # white border around the diagram, in diagram units


def page_bounds(diagram):
    """Bounding box of all absolutely positioned vertices on a page."""
    xs, ys, xe, ye = [], [], [], []
    for cell in diagram.iter("mxCell"):
        if cell.get("vertex") != "1":
            continue
        geo = cell.find("mxGeometry")
        if geo is None or geo.get("relative") == "1":
            continue
        x, y = float(geo.get("x", 0)), float(geo.get("y", 0))
        w, h = float(geo.get("width", 0)), float(geo.get("height", 0))
        xs.append(x); ys.append(y); xe.append(x + w); ye.append(y + h)
    return min(xs), min(ys), max(xe), max(ye)


def render_page(mxfile_root, diagram, out_png):
    # The viewer accepts a whole mxfile; keep only the page we want so page indexes stay simple.
    single = ET.Element("mxfile", attrib=dict(mxfile_root.attrib))
    single.append(diagram)
    xml = ET.tostring(single, encoding="unicode")
    x0, y0, x1, y1 = page_bounds(diagram)
    width = int(x1 - x0 + 2 * MARGIN)
    height = int(y1 - y0 + 2 * MARGIN)
    config = {"highlight": "#0000ff", "nav": False, "resize": False, "toolbar": None,
              "border": MARGIN, "xml": xml}
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:#fff}}.mxgraph{{width:{width}px;height:{height}px}}</style>
</head><body>
<div class="mxgraph" data-mxgraph='{html.escape(json.dumps(config), quote=True)}'></div>
<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
</body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
        fh.write(page)
        html_path = fh.name
    try:
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--disable-gpu",
                        f"--window-size={width},{height}", f"--force-device-scale-factor={SCALE}",
                        "--virtual-time-budget=15000", f"--screenshot={out_png}",
                        f"file://{html_path}"], check=True, capture_output=True)
    finally:
        os.unlink(html_path)
    print("written", out_png, f"({width}x{height} @ {SCALE})")


def main():
    src, prefix = sys.argv[1], sys.argv[2]
    tree = ET.parse(src)
    root = tree.getroot()
    diagrams = root.findall("diagram")
    for d in diagrams:
        name = d.get("name", "page")
        out = f"{prefix}.png" if len(diagrams) == 1 else f"{prefix}-{name}.png"
        render_page(root, d, out)


if __name__ == "__main__":
    main()
