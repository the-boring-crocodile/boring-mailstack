#!/usr/bin/env python3
"""Writes life-of-a-mail.dot next to this script: the positions are computed here.

Render (from docs/architecture):
    python3 life-of-a-mail.py && neato -n2 -Tsvg life-of-a-mail.dot -o life-of-a-mail.svg
Style and rules as the other diagrams: README.md in this folder.
"""
from pathlib import Path
F = 'fontname="Helvetica"'
BLUE, GREEN, GREY, INK = "#587b96", "#578478", "#b3b8b5", "#111111"
lanes = {"Inbox": 400, "News": 335, "Reading": 270, "Keep": 205}
cols = [230, 430, 630, 830]
L = ['digraph "The life of a mail" {',
     f'graph [{F}, bgcolor="#ffffff", pad=0.444, splines=line, outputorder=nodesfirst];',
     f'node [{F}, fontsize=10, fontcolor="{INK}"];',
     'edge [arrowsize=0.7, penwidth=1.4];']
def node(name, x, y, **a):
    attrs = ", ".join(f'{k}={v}' for k, v in a.items())
    L.append(f'{name} [pos="{x},{y}", {attrs}];')
# title
node("title", 205, 548, shape="plaintext", label='<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="0">'
     '<TR><TD ALIGN="LEFT" WIDTH="400"><FONT POINT-SIZE="18"><B>The life of a mail</B></FONT></TD></TR>'
     '<TR><TD HEIGHT="6"></TD></TR>'
     '<TR><TD ALIGN="LEFT">Dynamic diagram · boring-mailstack · what you file, the filter leaves alone</TD></TR></TABLE>>')
# folder lanes
for name, y in lanes.items():
    node(f"lane_{name}", 475, y, shape="box", style='"filled,rounded"', fillcolor='"#f4f5f3"', color='"#dfe2df"',
         width=12.64, height=0.694, fixedsize="true", label='""')
    node(f"lanelabel_{name}", 72, y, shape="plaintext", label=f'<<TABLE BORDER="0" CELLPADDING="0"><TR><TD ALIGN="LEFT" WIDTH="90"><B>{name}</B></TD></TR></TABLE>>')
# column headings: number in a circle, then text
heads = [("Mail arrives", "Your filter: newsletters &#8594; News.", "It files A and B."),
         ("You file B into Keep", "Recorded: placed by you.", ""),
         ("You change the filter", "newsletters &#8594; Reading. A minute", "later the filter re-sorts."),
         ("You move B to the Inbox", "Released: the filter", "files it again.")]
for i, (x, (h, l1, l2)) in enumerate(zip(cols, heads), 1):
    node(f"num{i}", x - 84, 488, shape="circle", width=0.21, height=0.21, fixedsize="true", style="filled",
         fillcolor='"#ffffff"', color=f'"{BLUE}"', penwidth=1.2, fontsize=10, fontcolor='"#33506a"', label=f'<<B>{i}</B>>')
    rows = f'<TR><TD ALIGN="LEFT" WIDTH="168"><B>{h}</B></TD></TR><TR><TD ALIGN="LEFT">{l1}</TD></TR>'
    rows += f'<TR><TD ALIGN="LEFT">{l2 or " "}</TD></TR>'
    node(f"head{i}", x + 10, 472, shape="plaintext",
         label=f'<<TABLE BORDER="0" CELLSPACING="1" CELLPADDING="0">{rows}</TABLE>>')
# mails
def mail(name, letter, x, lane, mine=False):
    if mine:
        node(name, x, lanes[lane], shape="box", style='"filled,rounded"', fillcolor='"#edf2fa"', color='"#33506a"',
             penwidth=2.6, width=0.5, height=0.32, fixedsize="true", fontsize=11, label=f'<<B>{letter}</B>>')
    else:
        node(name, x, lanes[lane], shape="box", style='"filled,rounded"', fillcolor='"#ffffff"', color='"#7a8a96"',
             penwidth=1.0, width=0.5, height=0.32, fixedsize="true", fontsize=11, label=f'<<B>{letter}</B>>')
node("new", 150, lanes["Inbox"], shape="point", width=0.08, color=f'"{GREEN}"')
mail("B1", "B", 205, "News"); mail("A1", "A", 255, "News")
mail("A2", "A", 430, "News"); mail("B2", "B", 430, "Keep", mine=True)
mail("A3", "A", 630, "Reading"); mail("B3", "B", 630, "Keep", mine=True)
mail("A4", "A", 790, "Reading"); mail("B4i", "B", 870, "Inbox"); mail("B4", "B", 870, "Reading")
def edge(a, b, kind):
    style = {"you": f'color="{BLUE}"', "filter": f'color="{GREEN}"',
             "stays": f'color="{GREY}", style=dotted, dir=none, penwidth=1.2'}[kind]
    L.append(f"{a} -> {b} [{style}];")
edge("new", "A1", "filter"); edge("new", "B1", "filter")
edge("A1", "A2", "stays"); edge("B1", "B2", "you")
edge("A2", "A3", "filter"); edge("B2", "B3", "stays")
edge("A3", "A4", "stays"); edge("B3", "B4i", "you"); edge("B4i", "B4", "filter")
# key
key = ('<<TABLE BORDER="0" CELLSPACING="24" CELLPADDING="0"><TR>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>Key</B></FONT><BR ALIGN="LEFT"/>'
       f'<FONT COLOR="{BLUE}"><B>Blue arrow</B></FONT> · you move the mail<BR ALIGN="LEFT"/>'
       f'<FONT COLOR="{GREEN}"><B>Green arrow</B></FONT> · your filter moves it<BR ALIGN="LEFT"/>'
       'Dotted line · it stays where it is<BR ALIGN="LEFT"/>'
       '<B>Bold frame</B> · placed by you: the filter leaves it alone<BR ALIGN="LEFT"/>'
       'Grey band · a folder<BR ALIGN="LEFT"/></TD>'
       '<TD ALIGN="LEFT" VALIGN="TOP" BALIGN="LEFT"><FONT POINT-SIZE="12"><B>The rule</B></FONT><BR ALIGN="LEFT"/>'
       'Where you put a mail, it stays: a move or copy in the webmail<BR ALIGN="LEFT"/>'
       'or any IMAP client, and a folder you had filed it into at<BR ALIGN="LEFT"/>'
       'your provider. Everything else goes where your filter says,<BR ALIGN="LEFT"/>'
       'also when you change the filter. Moving a mail into the Inbox<BR ALIGN="LEFT"/>'
       'hands it back to the filter.<BR ALIGN="LEFT"/></TD></TR></TABLE>>')
node("key", 500, 92, shape="plaintext", label=key)
L.append("}")
open(Path(__file__).with_suffix(".dot"), "w").write("\n".join(L) + "\n")
