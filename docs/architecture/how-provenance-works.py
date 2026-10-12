#!/usr/bin/env python3
"""Writes how-provenance-works.dot next to this script: the positions are computed here.

Render (from docs/architecture):
    python3 how-provenance-works.py && neato -n2 -Tsvg how-provenance-works.dot -o how-provenance-works.svg
Style and rules as the other diagrams: README.md in this folder.
"""
from pathlib import Path
F = 'fontname="Helvetica"'
BLUE, GREEN, GREY, INK = "#587b96", "#578478", "#a9afab", "#111111"
X = {"you": 80, "roundcube": 255, "stalwart": 430, "provenance": 605, "resieve": 780, "bridge": 955}
HEADS = {"you": ("You", "Person", "blue", True), "roundcube": ("Roundcube", "Container · webmail", "blue", False),
         "stalwart": ("Stalwart", "Container · mail server", "green", False),
         "provenance": ("provenance", "Container · Python / SQLite", "green", False),
         "resieve": ("resieve", "Containers · watch, re-sort", "green", False),
         "bridge": ("bridge", "Container · Python", "green", False)}
COL = {"blue": ('"#edf2fa"', '"#7489a5"'), "green": ('"#edf5ef"', '"#7a9783"')}
ROWS = [
    ("phase", 1, "Mail arrives"),
    ("msg", "bridge", "stalwart", "stack", "delivers A and B"),
    ("note", "stalwart", "your filter files both into News; nothing is recorded"),
    ("phase", 2, "You file B into Keep"),
    ("msg", "you", "roundcube", "you", "move B to Keep"),
    ("msg", "roundcube", "stalwart", "you", "IMAP MOVE"),
    ("msg", "stalwart", "provenance", "stack", "webhook: B moved"),
    ("note", "provenance", "records: B placed by you"),
    ("phase", 3, "You change the filter"),
    ("msg", "you", "roundcube", "you", "newsletters → Reading"),
    ("msg", "roundcube", "stalwart", "you", "ManageSieve: save"),
    ("msg", "stalwart", "resieve", "stack", "webhook: a filter changed"),
    ("note", "resieve", "waits until 60 s without a change"),
    ("msg", "resieve", "provenance", "record", "reads the records"),
    ("msg", "resieve", "stalwart", "stack", "JMAP: A to Reading (B is yours: left alone)"),
    ("phase", 4, "You move B to the Inbox"),
    ("msg", "you", "roundcube", "you", "move B to the Inbox"),
    ("msg", "roundcube", "stalwart", "you", "IMAP MOVE"),
    ("msg", "stalwart", "provenance", "stack", "webhook: B moved to Inbox"),
    ("msg", "provenance", "resieve", "stack", "re-sort B"),
    ("note", "resieve", "waits until 60 s without a move"),
    ("msg", "resieve", "provenance", "record", "releases B's record"),
    ("msg", "resieve", "stalwart", "stack", "JMAP: B to Reading"),
]
# layout, top-down in y; converted to Graphviz's upward y at the end
y = 120          # first row below the heads
pos = []
for r in ROWS:
    y += 40 if r[0] == "phase" else (24 if r[0] == "note" else 30)
    pos.append(y)
BOTTOM = y + 30
KEY_Y = BOTTOM + 70
H = KEY_Y + 70
def Y(v): return H - v
L = ['digraph "How provenance works" {',
     f'graph [{F}, bgcolor="#ffffff", pad=0.444, splines=line, outputorder=nodesfirst];',
     f'node [{F}, fontsize=10, fontcolor="{INK}"];', 'edge [arrowsize=0.7, penwidth=1.4];']
def node(name, x, y, **a):
    L.append(f'{name} [pos="{x},{Y(y)}", ' + ", ".join(f"{k}={v}" for k, v in a.items()) + "];")
def pt(name, x, y): node(name, x, y, shape="point", width=0.01, style="invis")
def text(name, x_left, y, html, w=300, h=0.2):
    # plaintext node whose left edge is x_left; text baseline-ish at y
    node(name, x_left + w / 2, y, shape="plaintext", width=w / 72, fixedsize="true", height=h,
         label=f'<<TABLE BORDER="0" CELLPADDING="0" CELLSPACING="0"><TR><TD ALIGN="LEFT" WIDTH="{w}">{html}</TD></TR></TABLE>>')
text("title", 8, 22, '<FONT POINT-SIZE="18"><B>How provenance works</B></FONT>', 400, 0.32)
text("subtitle", 8, 44, "Sequence diagram · boring-mailstack · the same story as <I>The life of a mail</I>, inside the stack", 600)
# heads
for k, (name, kind, col, rounded) in HEADS.items():
    fill, line = COL[col]
    style = '"filled,rounded"' if rounded else "filled"
    node(f"head_{k}", X[k], 92, shape="box", style=style, fillcolor=fill, color=line, penwidth=1.2,
         width=2.08, height=0.64, fixedsize="true",
         label=f'<<TABLE BORDER="0" CELLSPACING="2" CELLPADDING="0"><TR><TD ALIGN="LEFT" WIDTH="128"><FONT POINT-SIZE="12"><B>{name}</B></FONT></TD></TR><TR><TD ALIGN="LEFT">[{kind}]</TD></TR></TABLE>>')
# phase bands; lifelines run in segments between them
bands = []
for i, r in enumerate(ROWS):
    if r[0] == "phase":
        yb = pos[i]
        bands.append(yb)
        node(f"band{r[1]}", 515, yb, shape="box", style='"filled,rounded"', fillcolor='"#f4f5f3"', color='"#dfe2df"',
             width=14.0, height=0.31, fixedsize="true", label='""')
        node(f"num{r[1]}", 24, yb, shape="circle", width=0.21, height=0.21, fixedsize="true", style="filled",
             fillcolor='"#ffffff"', color=f'"{BLUE}"', penwidth=1.2, fontcolor='"#33506a"', label=f"<<B>{r[1]}</B>>")
        text(f"phase{r[1]}", 36, yb, f"<B>{r[2]}</B>", 250)
segs = [(124, bands[0] - 11)] + [(b + 11, nb - 11) for b, nb in zip(bands, bands[1:])] + [(bands[-1] + 11, BOTTOM)]
for k, x in X.items():
    for j, (a, b) in enumerate(segs):
        pt(f"ll_{k}_{j}a", x, a); pt(f"ll_{k}_{j}b", x, b)
        L.append(f'll_{k}_{j}a -> ll_{k}_{j}b [dir=none, color="{GREY}", style=dashed, penwidth=1.0];')
# messages and notes
STYLE = {"you": f'color="{BLUE}"', "stack": f'color="{GREEN}"', "record": f'color="{GREEN}", style=dashed'}
for i, r in enumerate(ROWS):
    yy = pos[i]
    if r[0] == "msg":
        _, a, b, kind, label = r
        pt(f"m{i}a", X[a], yy); pt(f"m{i}b", X[b], yy)
        L.append(f"m{i}a -> m{i}b [{STYLE[kind]}];")
        left = min(X[a], X[b])
        text(f"ml{i}", left + 8, yy - 9, label, 160 if abs(X[a] - X[b]) < 200 else 330)
    elif r[0] == "note":
        _, at, label = r
        text(f"n{i}", X[at] + 8, yy - 2, f'<FONT COLOR="#555555"><I>{label}</I></FONT>', 300)
key = ('<<TABLE BORDER="0" CELLSPACING="24" CELLPADDING="0"><TR>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>Key</B></FONT><BR ALIGN="LEFT"/>'
       f'<FONT COLOR="{BLUE}"><B>Blue arrow</B></FONT> · started by you<BR ALIGN="LEFT"/>'
       f'<FONT COLOR="{GREEN}"><B>Green arrow</B></FONT> · the stack on its own<BR ALIGN="LEFT"/>'
       f'<FONT COLOR="{GREEN}"><B>Dashed green</B></FONT> · a record read or written<BR ALIGN="LEFT"/>'
       '<I>Grey italics</I> · what happens inside<BR ALIGN="LEFT"/></TD>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>Notes</B></FONT><BR ALIGN="LEFT"/>'
       'The records are one SQLite file: provenance writes it,<BR ALIGN="LEFT"/>'
       'resieve reads it and removes released records.<BR ALIGN="LEFT"/>'
       'A mail you had filed at your provider is recorded when<BR ALIGN="LEFT"/>'
       'the bridge imports it (not drawn).<BR ALIGN="LEFT"/></TD></TR></TABLE>>')
node("key", 515, KEY_Y, shape="plaintext", label=key)
L.append("}")
open(Path(__file__).with_suffix(".dot"), "w").write("\n".join(L) + "\n")
