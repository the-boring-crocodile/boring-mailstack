#!/usr/bin/env python3
"""Writes who-is-trusted.dot next to this script: the positions are computed here.

Render (from docs/architecture):
    python3 who-is-trusted.py && neato -n2 -Tsvg who-is-trusted.dot -o who-is-trusted.svg
Style and rules as the other diagrams: README.md in this folder.
"""
from pathlib import Path
F = 'fontname="Helvetica"'
INK, GREYLINE = "#111111", "#8c8d87"
H = 640
def Y(v): return H - v
L = ['digraph "Who is trusted" {',
     f'graph [{F}, bgcolor="#ffffff", pad=0.444, splines=line, outputorder=nodesfirst];',
     f'node [{F}, fontsize=10, fontcolor="{INK}"];', 'edge [arrowsize=0.9, penwidth=1.4];']
def node(name, x, y, **a):
    L.append(f'{name} [pos="{x},{Y(y)}", ' + ", ".join(f"{k}={v}" for k, v in a.items()) + "];")
def box(name, x0, y0, x1, y1, fill, line, rounded=True, pen=1.2):
    node(name, (x0 + x1) / 2, (y0 + y1) / 2, shape="box", style='"filled,rounded"' if rounded else "filled",
         fillcolor=f'"{fill}"', color=f'"{line}"', penwidth=pen, width=(x1 - x0) / 72, height=(y1 - y0) / 72,
         fixedsize="true", label='""')
def text(name, x0, y0, lines, w, title=None):
    rows = ""
    if title:
        rows += f'<TR><TD ALIGN="LEFT" WIDTH="{w}"><FONT POINT-SIZE="12"><B>{title}</B></FONT></TD></TR><TR><TD HEIGHT="3"></TD></TR>'
    rows += "".join(f'<TR><TD ALIGN="LEFT" WIDTH="{w}">{l}</TD></TR>' for l in lines)
    h = 13 * len(lines) + (26 if title else 0)
    node(name, x0 + w / 2, y0 + h / 2, shape="plaintext", width=w / 72, height=h / 72, fixedsize="true",
         label=f'<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="0">{rows}</TABLE>>')
def pt(name, x, y): node(name, x, y, shape="point", width=0.01, style="invis")

text("title", 8, 8, ["Trust boundaries · boring-mailstack · a small office: one machine, a handful of people"], 560,
     title='<FONT POINT-SIZE="18">Who is trusted</FONT>')
# the three circles, outermost first (drawn first)
box("lan", 20, 80, 700, 520, "#f7f9fb", "#9aaabb")
box("users", 50, 170, 670, 490, "#eef3f8", "#8fa1b4")
box("root", 80, 290, 430, 460, "#e2eaf4", "#7489a5", pen=1.6)
text("t_lan", 36, 94, ["Webmail and the admin page are plain HTTP on the machine's LAN address,",
                       "so every computer in the house or office can open them."], 600,
     title="The LAN · trusted by default")
text("t_users", 66, 184, ["Each one's logins (mail, Nextcloud) are theirs alone.",
                          "The webmail connects to the contact and Nextcloud addresses they type in."], 580,
     title="Everyone with an account · trusted not to attack the office")
text("t_root", 96, 304, ["You hold every provider password (accounts.yaml)",
                         "and can read every mailbox, as the administrator",
                         "of any mail server can. Tell your users so.",
                         " ",
                         "Inside the stack, TLS to the mail server is not",
                         "verified: whoever gets in here can read the",
                         "secrets anyway."], 320,
     title="You (root) and the stack · fully trusted")
# guard between the users and the stack's insides
text("t_guard", 448, 318, ["Roundcube shares a network with the mail",
                           "server only: addresses users type in reach",
                           "the LAN and the Internet, never the",
                           "stack's own services."], 214, title=None)
pt("g_a", 650, 392); pt("g_b", 430, 392)
L.append(f'g_a -> g_b [arrowhead=tee, color="{GREYLINE}"];')
# outside: not trusted
outside = [("host", 150, "Other users of this machine",
            ["Not trusted: tools/deploy refuses to run", "while etc/ or accounts.yaml is open to them."]),
           ("internet", 300, "The Internet",
            ["Not trusted by default. From outside, only", "through a TLS reverse proxy, with the stack", "bound to 127.0.0.1."]),
           ("path", 420, "The way to your providers",
            ["Not trusted. Certificates are verified", "for fetching and for sending."])]
# stacked with equal gaps, from just inside the LAN frame's top to its bottom
heights = [18 + 13 * len(o[3]) + 20 for o in outside]
gap = (490 - 110 - sum(heights)) / (len(outside) - 1)
top = 110
for (key, _, title, lines), h in zip(outside, heights):
    y = top + h / 2
    top += h + gap
    box(f"o_{key}", 790, y - h / 2, 1030, y + h / 2, "#f5f5f3", GREYLINE, rounded=False)
    text(f"t_{key}", 802, y - h / 2 + 10, lines, 220, title=title)
    pt(f"o_{key}_a", 790, y); pt(f"o_{key}_b", 700, y)
    L.append(f'o_{key}_a -> o_{key}_b [arrowhead=tee, color="{GREYLINE}"];')
key = ('<<TABLE BORDER="0" CELLSPACING="24" CELLPADDING="0"><TR>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>Key</B></FONT><BR ALIGN="LEFT"/>'
       'Blue frame · a circle of trust; the deeper, the more it is trusted<BR ALIGN="LEFT"/>'
       'Grey box · not trusted<BR ALIGN="LEFT"/>'
       'Line ending in a bar · kept out, and how<BR ALIGN="LEFT"/></TD>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>Why</B></FONT><BR ALIGN="LEFT"/>'
       'For a family or a small office, a trusted administrator is how things are.<BR ALIGN="LEFT"/>'
       'Designing against them (end-to-end encryption, split secrets) would add<BR ALIGN="LEFT"/>'
       'complexity this setting does not need, and would still not stop root.<BR ALIGN="LEFT"/></TD></TR></TABLE>>')
node("key", 525, 585, shape="plaintext", label=key)
L.append("}")
open(Path(__file__).with_suffix(".dot"), "w").write("\n".join(L) + "\n")
