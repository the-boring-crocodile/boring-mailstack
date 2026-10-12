#!/usr/bin/env python3
"""Put each edge's number on its arrow, in a small circle at the midpoint.

Graphviz places edge labels wherever there is room, so their sides and
distances vary. This moves every edge label of a rendered SVG onto the
middle of its (straight) edge instead: one rule for all.

Usage: dot -Tsvg way-of-a-mail.dot | python3 badges.py > way-of-a-mail.svg
"""
import re
import sys

R = 7.5  # badge radius, pt

def badge(m):
    g = m.group(0)
    path = re.search(r'<path[^>]* stroke="(#[0-9a-f]{6})"[^>]* d="M([-\d.]+),([-\d.]+)[^"]*?([-\d.]+),([-\d.]+)"', g)
    tip = re.search(r'<polygon[^>]* points="[^"]*?([-\d.]+),([-\d.]+) [-\d.]+,[-\d.]+ [-\d.]+,[-\d.]+"', g)
    text = re.search(r'<text [^>]*fill="(#[0-9a-f]{6})"[^>]*>([^<]*)</text>', g)
    if not (path and text):
        return g
    color = path.group(1)
    x0, y0 = float(path.group(2)), float(path.group(3))
    x1, y1 = float(path.group(4)), float(path.group(5))
    if tip:  # the arrowhead tip is the real end of the line
        x1, y1 = float(tip.group(1)), float(tip.group(2))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    label = text.group(2).replace("&#160;", "").strip()
    b = (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{R}" fill="#ffffff" stroke="{color}" stroke-width="1.2"/>'
         f'<text text-anchor="middle" x="{cx:.2f}" y="{cy + 3.6:.2f}" font-family="Helvetica,sans-Serif" '
         f'font-weight="bold" font-size="10.00" fill="{text.group(1)}">{label}</text>')
    return g.replace(text.group(0), b)

svg = sys.stdin.read()
sys.stdout.write(re.sub(r'<g id="edge\d+" class="edge">.*?</g>', badge, svg, flags=re.S))
