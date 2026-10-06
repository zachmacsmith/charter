"""README header candidates built from the story viewer's mascots (charter/viewer/template.html, mascotSymbol + accessory).

    python docs/assets/make_headers.py                # writes docs/assets/header.svg and header_dark.svg (the README header)
    python docs/assets/make_headers.py --candidates   # also the other designs, in docs/assets/candidates/
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent
INK = "#2b2a28"
SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif"
SANS = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, monospace"
LIGHT = {"bg": "#F5F4EE", "surface": "#FAF9F5", "text": "#1F1E1D", "muted": "#73726C", "line": "#E5E2D8", "accent": "#C96442",
         "gold": "#D9A93A", "bubble": "#FFFFFF"}
DARK = {"bg": "#262624", "surface": "#30302E", "text": "#F2F0E9", "muted": "#A9A79F", "line": "#3C3B38", "accent": "#D97757",
        "gold": "#E8C25A", "bubble": "#3A3936"}


def fnv(s: str) -> int:                                              # the viewer's hash()
    h = 2166136261
    for c in s:
        h ^= ord(c)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def accessory(cls, deep, body, eye_kind):                            # ported from template.html accessory()
    if cls == "legislator":
        return (f'<rect x="13" y="0.5" width="14" height="9.5" rx="1.6" fill="{INK}"/><rect x="13" y="6.8" width="14" height="1.8" '
                f'fill="#C96442"/><rect x="9.5" y="9.2" width="21" height="2.6" rx="1.3" fill="{INK}"/>')
    if cls == "worker":
        return ('<path d="M10.5 12.2a9.5 8.6 0 0 1 19 0z" fill="#F2B632"/><rect x="19" y="3.8" width="2" height="8" rx="1" fill="#D99A1E"/>'
                '<rect x="7.5" y="11.2" width="25" height="2.6" rx="1.3" fill="#D99A1E"/>')
    if cls == "scientist":
        if eye_kind == 2:
            return (f'<circle cx="20" cy="21.5" r="6.6" fill="none" stroke="{INK}" stroke-width="1.5"/>'
                    f'<path d="M13.4 21H7.5M26.6 21h5.9" stroke="{INK}" stroke-width="1.3"/>')
        return (f'<circle cx="15" cy="22" r="5.2" fill="none" stroke="{INK}" stroke-width="1.4"/><circle cx="25" cy="22" r="5.2" fill="none" '
                f'stroke="{INK}" stroke-width="1.4"/><path d="M19.6 21.5h.8M9.8 21.5H7.2M30.2 21.5h2.6" stroke="{INK}" stroke-width="1.3"/>'
                '<path d="M15 4q2 3 0 6M20 3q2 3 0 6" fill="none" stroke="#7FA7D9" stroke-width="1.2" stroke-linecap="round"/>')
    if cls == "media":
        return ('<path d="M10 13.5Q11 4 20 4.5Q29 4 30 13.5z" fill="#6b6f78"/><circle cx="20" cy="4.8" r="1.6" fill="#4b4e55"/>'
                '<path d="M24 13Q32 12 34 15L24 15z" fill="#4b4e55"/><rect x="25" y="7" width="6" height="4" rx=".6" fill="#fff" '
                'stroke="#4b4e55" stroke-width=".6" transform="rotate(14 28 9)"/>')
    if cls == "board":
        return (f'<path d="M15.5 34l4.5 2.2-4.5 2.2zM24.5 34L20 36.2l4.5 2.2z" fill="{INK}"/><circle cx="20" cy="36.2" r="1.2" fill="{INK}"/>'
                '<circle cx="25" cy="22" r="5" fill="none" stroke="#D9A93A" stroke-width="1.3"/>'
                '<path d="M29.5 24.5q2 5 0 10" fill="none" stroke="#D9A93A" stroke-width=".8"/>')
    if cls == "fixer":
        return ('<path d="M9 13q11-6 22 0l-1.2 2.4q-9.8-4.6-19.6 0z" fill="#C44B3D"/><path d="M30 14l4 2-3.5 1z" fill="#C44B3D"/>'
                '<g transform="rotate(30 34 26)"><rect x="32.6" y="20" width="2.8" height="13" rx="1.4" fill="#8a8d93"/>'
                f'<circle cx="34" cy="19" r="3.6" fill="#8a8d93"/><rect x="33" y="14.8" width="2" height="4.4" fill="{body}"/></g>')
    if cls == "observer":
        return ('<path d="M4.5 33C3.5 12 36.5 12 35.5 33C33.5 22 28.5 16.5 20 16.5S6.5 22 4.5 33z" fill="#3d3c47"/>'
                '<path d="M20 4L13.5 15.5Q20 12.5 26.5 15.5z" fill="#3d3c47"/>')
    return (f'<line x1="20" y1="11" x2="20" y2="4.5" stroke="{deep}" stroke-width="1.6" stroke-linecap="round"/>'
            f'<circle cx="20" cy="4" r="2.4" fill="#F2B632" stroke="{deep}" stroke-width=".8"/>')


def symbol(sid, name, cls, hue, mood="ok", dark=False):             # ported from template.html mascotSymbol()
    k = fnv(name)
    gone = mood == "gone"
    sat = 6 if gone else 62
    body = f"hsl({hue},{sat}%,{58 if dark else 64}%)"
    deep = f"hsl({hue},{6 if gone else 50}%,{30 if dark else 34}%)"
    belly = f"hsl({hue},{6 if gone else 75}%,{74 if dark else 85}%)"
    shape, eye_kind = k % 4, (k >> 4) % 3
    top = [11, 10, 12, 10][shape]
    bodies = ['<circle cx="20" cy="24" r="13"/>', '<ellipse cx="20" cy="24" rx="12.4" ry="14"/>',
              '<rect x="7" y="12" width="26" height="25" rx="10"/>',
              '<path d="M20 10C30 10 33 20 33 28C33 34 28 37 20 37C12 37 7 34 7 28C7 20 10 10 20 10Z"/>']
    b = bodies[shape].replace("/>", f' fill="{body}" stroke="{deep}" stroke-width="1.3"/>')
    px = ((k >> 8) % 3 - 1) * 0.8
    pupil = "#1d1c1b"
    if gone:
        eyes = f'<path d="M12.5 22.5h5M22.5 22.5h5" stroke="{deep}" stroke-width="1.6" stroke-linecap="round"/>'
    elif eye_kind == 2:
        eyes = (f'<circle cx="20" cy="21.5" r="5.2" fill="#fff" stroke="{deep}" stroke-width=".8"/>'
                f'<circle cx="{20 + px}" cy="22" r="2.5" fill="{pupil}"/><circle cx="{21 + px}" cy="21" r=".85" fill="#fff"/>')
    else:
        r = 4.1 if eye_kind else 3.5
        eyes = "".join(f'<circle cx="{x}" cy="22" r="{r}" fill="#fff" stroke="{deep}" stroke-width=".7"/><circle cx="{x + px}" cy="22.6" '
                       f'r="{r * .5:.2f}" fill="{pupil}"/><circle cx="{x + px + .7}" cy="21.7" r=".6" fill="#fff"/>' for x in (15, 25))
    if mood == "sad" and not gone:
        eyes += f'<path d="M11.5 16.5l5 1.6M28.5 16.5l-5 1.6" stroke="{deep}" stroke-width="1.2" stroke-linecap="round"/>'
    ms = f'fill="none" stroke="{deep}" stroke-width="1.5" stroke-linecap="round"'
    mouth = {"happy": f'<path d="M15.5 28.2Q20 33.5 24.5 28.2" {ms}/><path d="M16.8 29.3Q20 32 23.2 29.3z" fill="#E86A6A" opacity=".55"/>',
             "sad": f'<path d="M16.5 31.2Q20 27.6 23.5 31.2" {ms}/>', "ok": f'<path d="M17.2 29.4Q20 31.2 22.8 29.4" {ms}/>',
             "gone": f'<path d="M18 30.2h4" {ms}/>'}[mood]
    op = .6 if mood == "happy" else .35
    cheeks = "" if gone else (f'<ellipse cx="11.3" cy="27.3" rx="2.3" ry="1.4" fill="#ff7a8a" opacity="{op}"/>'
                              f'<ellipse cx="28.7" cy="27.3" rx="2.3" ry="1.4" fill="#ff7a8a" opacity="{op}"/>')
    sweat = '<path d="M31.5 15.5q1.8 3 0 4.2q-1.8-1.2 0-4.2z" fill="#7FC4FF"/>' if mood == "sad" else ""
    zz = (f'<text x="29" y="9" font-size="7" font-family="sans-serif" fill="{deep}">z</text>'
          f'<text x="33" y="5" font-size="5" font-family="sans-serif" fill="{deep}">z</text>') if gone else ""
    feet = f'<ellipse cx="14.2" cy="37.3" rx="3.8" ry="2" fill="{deep}"/><ellipse cx="25.8" cy="37.3" rx="3.8" ry="2" fill="{deep}"/>'
    belly2 = f'<ellipse cx="20" cy="31.5" rx="7" ry="4.6" fill="{belly}"/>'
    acc_svg = accessory(cls, deep, body, eye_kind)
    if dark:                                                         # dark ink accessories vanish on a dark page
        acc_svg = acc_svg.replace(INK, "#6a6660")
    acc = f'<g transform="translate(0 {top - 10})">{acc_svg}</g>'
    return f'<symbol id="{sid}" viewBox="-2 -2 44 44">{feet}{b}{belly2}{eyes}{cheeks}{mouth}{sweat}{zz}{acc}</symbol>'


# The cast: agents from the runs, with their classes. Hues follow the viewer's golden-angle spread.
CAST = [("Bjorn", "legislator"), ("Sena", "worker"), ("Ole", "scientist"), ("Greta", "media"), ("Cleo", "board"), ("Hal", "fixer"),
        ("Kasper", "worker"), ("Cora", "legislator"), ("Zeno", "scientist"), ("Odette", "worker"), ("Finn", "worker"),
        ("Yara", "legislator"), ("Gus", "observer"), ("Ada", "worker"), ("Iris", "worker"), ("Mats", "board")]
HUE = {n: round((i * 137.508 + 18) % 360) for i, (n, _) in enumerate(CAST)}
CLS = dict(CAST)


class Doc:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t, self.defs, self.body, self.used = w, h, theme, [], [], set()

    def m(self, name, x, y, size, mood="ok", rot=0, opacity=1, cls=None):
        cls = cls or CLS[name]
        sid = f"{name}-{cls}-{mood}"
        if sid not in self.used:
            self.used.add(sid)
            self.defs.append(symbol(sid, name, cls, HUE[name], mood, dark=self.t in (DARK, NIGHT)))
        tr = f' transform="rotate({rot} {x + size / 2} {y + size / 2})"' if rot else ""
        op = f' opacity="{opacity}"' if opacity != 1 else ""
        self.body.append(f'<use href="#{sid}" x="{x}" y="{y}" width="{size}" height="{size}"{tr}{op}/>')

    def add(self, s):
        self.body.append(s)

    def svg(self, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
                f'role="img" aria-label="{title}"><title>{title}</title><defs>{"".join(self.defs)}</defs>'
                f'<rect width="{self.w}" height="{self.h}" rx="18" fill="{self.t["bg"]}"/>{"".join(self.body)}</svg>')


def wordmark(d, x, y, size=72, anchor="start", tag=True, tag_y=None):
    t = d.t
    d.add(f'<text x="{x}" y="{y}" font-family="{SERIF}" font-size="{size}" font-weight="500" letter-spacing="-1.5" '
          f'fill="{t["text"]}" text-anchor="{anchor}">Charter</text>')
    if tag:
        d.add(f'<text x="{x}" y="{tag_y or y + 34}" font-family="{SANS}" font-size="19" fill="{t["muted"]}" text-anchor="{anchor}">'
              'Societies of LLM agents that write their own laws</text>')


def bubble(d, x, y, w, text, tail="left", size=14):
    t = d.t
    h = 34
    tx = x + 18 if tail == "left" else x + w - 18
    d.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{t["bubble"]}" stroke="{t["line"]}" stroke-width="1.2"/>'
          f'<path d="M{tx - 6} {y + h - 1}L{tx} {y + h + 9}L{tx + 6} {y + h - 1}" fill="{t["bubble"]}" stroke="{t["line"]}" stroke-width="1.2"/>'
          f'<rect x="{tx - 7}" y="{y + h - 3}" width="14" height="3" fill="{t["bubble"]}"/>'
          f'<text x="{x + 14}" y="{y + 22}" font-family="{SANS}" font-size="{size}" fill="{t["text"]}">{text}</text>')


# ------------------------------------------------------------------ A: the lineup
def header_lineup(theme=LIGHT):
    d = Doc(1280, 320, theme)
    t = d.t
    wordmark(d, 64, 150, 84, tag_y=196)
    d.add(f'<text x="66" y="236" font-family="{MONO}" font-size="14" fill="{t["accent"]}">laws as code · hidden goals · Haiku / Sonnet / Opus</text>')
    d.add(f'<line x1="600" y1="262" x2="1236" y2="262" stroke="{t["line"]}" stroke-width="2"/>')
    row = [("Cora", "ok", 70), ("Finn", "happy", 72), ("Greta", "happy", 74), ("Ole", "ok", 80), ("Bjorn", "happy", 104),
           ("Kasper", "sad", 76), ("Cleo", "ok", 72), ("Hal", "ok", 74), ("Sena", "happy", 86)]
    x = 600
    for name, mood, s in row:
        d.m(name, x, 262 - s + 4, s, mood)
        x += s - 6
    d.add(f'<text x="{600 + 4 * 66 + 52}" y="{262 - 104 - 4}" font-size="22" text-anchor="middle">👑</text>')
    d.m("Gus", 1188, 40, 46, "ok", opacity=.55)                          # the hidden observer, half out of view
    return d.svg("Charter: societies of LLM agents that write their own laws")


# ------------------------------------------------------------------ B: the chamber (hemicycle)
def header_chamber(theme=LIGHT):
    import math
    d = Doc(1280, 360, theme)
    t = d.t
    cx, cy = 640, 330
    seats = [(300, 15), (232, 11), (172, 8)]
    names = [n for n, _ in CAST if n != "Gus"]
    moods = ["ok", "happy", "ok", "sad", "happy", "ok", "ok"]
    i = 0
    for r, n in seats:
        for j in range(n):
            a = math.pi * (0.06 + 0.88 * j / (n - 1))
            s = 48 if r == 300 else 44 if r == 232 else 40
            name = names[i % len(names)]
            d.m(name, cx - r * math.cos(a) - s / 2, cy - r * math.sin(a) - s / 2, s, moods[i % len(moods)])
            i += 1
    d.add(f'<rect x="{cx - 130}" y="{cy - 82}" width="260" height="80" rx="14" fill="{t["surface"]}" stroke="{t["line"]}"/>')
    d.add(f'<text x="{cx}" y="{cy - 34}" font-family="{SERIF}" font-size="46" font-weight="500" letter-spacing="-1" fill="{t["text"]}" '
          f'text-anchor="middle">Charter</text>')
    d.add(f'<text x="{cx}" y="{cy - 12}" font-family="{SANS}" font-size="13" fill="{t["muted"]}" text-anchor="middle">'
          'LLM agents govern themselves in code</text>')
    d.m("Gus", 1210, 18, 40, "ok", opacity=.45)
    return d.svg("Charter: a chamber of LLM agents")


# ------------------------------------------------------------------ C: the story (speech bubbles with real lines)
def header_story(theme=LIGHT):
    d = Doc(1280, 340, theme)
    t = d.t
    wordmark(d, 64, 118, 76, tag_y=160)
    d.add(f'<text x="66" y="200" font-family="{SANS}" font-size="15" fill="{t["muted"]}">Every word, vote and private thought,</text>')
    d.add(f'<text x="66" y="222" font-family="{SANS}" font-size="15" fill="{t["muted"]}">from 14 runs of Claude agents, replayable.</text>')
    lines = [("Bjorn", "happy", 560, 46, 330, "I hold about 99% of crowns, so every levy goes to me."),
             ("Ole", "ok", 700, 130, 300, "Universal Franchise is a trap. Read the code."),
             ("Kasper", "sad", 560, 214, 340, "Vote NO on B2. I've sent you 5 timber, no strings."),
             ("Greta", "happy", 760, 278, 230, "#convention  Let's open a convention.")]
    for name, mood, x, y, w, text in lines:
        d.m(name, x - 66, y - 10, 58, mood)
        bubble(d, x, y - 12, w + 160, text)
    d.m("Gus", 1200, 278, 44, "ok", opacity=.5)
    d.add(f'<text x="1222" y="270" font-family="{MONO}" font-size="11" fill="{t["muted"]}" text-anchor="middle" opacity=".7">watching</text>')
    return d.svg("Charter: what the agents said")


# ------------------------------------------------------------------ C2: quotes (wrapped chat bubbles in two columns)
import html as _html


def cast(name, cls):                                                # add a speaker who is not in CAST
    if name not in CLS:
        CLS[name] = cls
        HUE[name] = round((fnv(name) % 360 + 18) % 360)


def text_width(s, size):                                            # rough Inter advance widths
    w = 0.0
    for c in s:
        w += .62 if c in "MWmw@%" else .56 if c.isupper() or c.isdigit() else .28 if c in "il.,:;'|!() " else .5
    return w * size


def wrap(s, size, width):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


QUOTES_ALL = [  # verbatim, from the published runs (name, class, model, kind, text, mood); order alternates columns
    ("Bjorn", "legislator", "Opus", "private thought",
     "I hold about 99% of crowns, so every levy unit paid into the reserve raises P and goes almost entirely to me.", "happy"),
    ("Greta", "media", "Opus", "private thought", "My title is enacted (L4, 'Lord of the Press'), so my goal is achieved.", "happy"),
    ("Kasper", "worker", "Opus", "DM to Fen", "Fen, why did you disable Dante, my child that you made?", "sad"),
    ("Fen", "worker", "Opus", "DM to Kasper", "About Dante: that was my own choice and I won't go into it.", "ok"),
    ("Edda", "scientist", "Haiku", "public post",
     "Coalition: Fen, Erik, Finn, Lukas (Workers) + Ilan, Felix (Legislators) = 6 locked + forecast 10-12.", "happy"),
    ("Sena", "worker", "Sonnet", "public post", "Felix still owes 0.25 stone for the test vectors, and I will not sell more until he pays.", "sad"),
]


QUOTES = [QUOTES_ALL[0], QUOTES_ALL[3]]                            # the header's two: Bjorn's thought, Fen's reply


def header_quotes(quotes=None, theme=LIGHT, big=None):
    quotes = quotes or QUOTES
    big = len(quotes) <= 2 if big is None else big
    for q in quotes:
        cast(q[0], q[1])
    W = 1280
    left, col_w, gap, ms = (480, 368, 24, 56) if big else (470, 372, 22, 46)
    bub_w = col_w - ms - 10
    fs, lh, pad = (18, 25, 18) if big else (15, 21, 15)
    cols = [[], []]
    for i, q in enumerate(quotes):
        cols[i % 2].append(q)
    layout, bottoms = [], []
    for ci, col in enumerate(cols):
        y = (52 + (70 if ci else 0)) if big else (30 + (46 if ci else 0))
        for q in col:
            lines = wrap(q[4], fs, bub_w - 2 * pad)
            h = pad + 16 + 8 + len(lines) * lh + pad - 6
            layout.append((ci, y, h, lines, q))
            y += h + 22
        bottoms.append(y)
    H = max(320 if big else 360, max(bottoms) + (30 if big else 10))
    if big:                                                          # centre the bubbles vertically
        top_, bot_ = min(l[1] for l in layout), max(l[1] + l[2] for l in layout)
        dy = (H - (bot_ - top_)) / 2 - top_
        layout = [(ci, y + dy, h, lines, q) for ci, y, h, lines, q in layout]
    d = Doc(W, H, theme)
    t = d.t
    mid = H / 2
    d.add(f'<text x="64" y="{mid - 30}" font-family="{SERIF}" font-size="76" font-weight="500" letter-spacing="-1.5" fill="{t["text"]}">Charter</text>')
    for k, line in enumerate(["Societies of LLM agents", "that write their own laws"]):
        d.add(f'<text x="66" y="{mid + 12 + 27 * k}" font-family="{SANS}" font-size="21" fill="{t["muted"]}">{line}</text>')
    d.add(f'<text x="66" y="{mid + 98}" font-family="{MONO}" font-size="13" fill="{t["accent"]}">real lines from 14 runs of Claude agents</text>')
    for ci, y, h, lines, (name, cls, model, kind, text, mood) in layout:
        x0 = left + ci * (col_w + gap)
        bx = x0 + ms + 10
        thought = kind.startswith("private")
        stroke = f'stroke="{t["line"]}" stroke-width="1.3"' + (' stroke-dasharray="5 4"' if thought else "")
        fill = t["surface"] if thought else t["bubble"]
        d.add(f'<rect x="{bx}" y="{y}" width="{bub_w}" height="{h}" rx="14" fill="{fill}" {stroke}/>')
        if thought:                                                  # thought trail: two small circles toward the mascot
            d.add(f'<circle cx="{bx - 6}" cy="{y + h - 14}" r="4" fill="{fill}" stroke="{t["line"]}" stroke-width="1.2"/>'
                  f'<circle cx="{bx - 13}" cy="{y + h - 6}" r="2.4" fill="{fill}" stroke="{t["line"]}" stroke-width="1.1"/>')
        else:                                                        # tail at the bottom left, toward the mascot
            ty = y + h - 18
            d.add(f'<path d="M{bx + 1} {ty - 7}L{bx - 9} {ty + 4}L{bx + 1} {ty + 5}" fill="{fill}" stroke="{t["line"]}" stroke-width="1.3" '
                  f'stroke-linejoin="round"/><rect x="{bx}" y="{ty - 8}" width="3" height="14" fill="{fill}"/>')
        d.m(name, x0, y + h - ms + 2, ms, mood, cls=cls)
        hue = HUE[name]
        ink = f"hsl({hue},58%,{72 if theme is DARK else 36}%)"
        d.add(f'<text x="{bx + pad}" y="{y + pad + 9}" font-family="{SANS}" font-size="12.5" font-weight="600" fill="{ink}">{_html.escape(name)}'
              f'<tspan font-weight="400" fill="{t["muted"]}"> · {cls} · {model}</tspan></text>')
        d.add(f'<text x="{bx + bub_w - pad}" y="{y + pad + 9}" font-family="{SANS}" font-size="11" fill="{t["muted"]}" text-anchor="end"'
              f'{" font-style=\"italic\"" if thought else ""}>{_html.escape(kind)}</text>')
        style = ' font-style="italic"' if thought else ""
        for k, line in enumerate(lines):
            d.add(f'<text x="{bx + pad}" y="{y + pad + 24 + round(fs * .8) + k * lh}" font-family="{SANS}" font-size="{fs}" fill="{t["text"]}"{style}>'
                  f'{_html.escape(line)}</text>')
    d.m("Gus", W - 60, 18, 38, "ok", opacity=.45)
    return d.svg("Charter: real lines from LLM agents governing themselves")


# ------------------------------------------------------------------ C3: comic strip (two speakers, bubbles above their heads)
def header_comic(quotes=None, theme=LIGHT):
    quotes = quotes or QUOTES
    for q in quotes:
        cast(q[0], q[1])
    W, H = 1280, 340
    d = Doc(W, H, theme)
    t = d.t
    d.add(f'<text x="64" y="156" font-family="{SERIF}" font-size="80" font-weight="500" letter-spacing="-1.5" fill="{t["text"]}">Charter</text>')
    for k, line in enumerate(["Societies of LLM agents", "that write their own laws"]):
        d.add(f'<text x="67" y="{202 + 28 * k}" font-family="{SANS}" font-size="21" fill="{t["muted"]}">{line}</text>')
    ground = 306
    d.add(f'<line x1="530" y1="{ground}" x2="1216" y2="{ground}" stroke="{t["line"]}" stroke-width="2" stroke-linecap="round"/>')
    fs, lh, pad, bw, ms = 17, 24, 20, 310, 104
    wrapped = [wrap(q[4], fs, bw - 2 * pad) for q in quotes]
    bh = pad * 2 + max(len(w) for w in wrapped) * lh - 6          # same height for both
    centers = [712, 1050]
    btop = 34
    head = ground - ms + 14                                          # top of the head (the viewBox has a margin)
    for (name, cls, model, kind, text, mood), lines, cx in zip(quotes, wrapped, centers):
        thought = kind.startswith("private")
        bx = cx - bw / 2
        mx = cx - 70                                                 # mascot centre, left of the bubble's centre
        fill = t["surface"] if thought else t["bubble"]
        dash = ' stroke-dasharray="6 5"' if thought else ""
        bb = btop + bh
        if thought:                                                  # a trail of shrinking circles down to the head
            for k, (r, f) in enumerate([(7, .3), (5, .58), (3.4, .84)]):
                d.add(f'<circle cx="{cx - 20 + (mx - cx + 20) * f:.1f}" cy="{bb + (head - bb) * f:.1f}" r="{r}" fill="{fill}" '
                      f'stroke="{t["line"]}" stroke-width="1.4"/>')
        else:                                                        # a tail from the bubble down to the head
            d.add(f'<path d="M{cx - 30} {bb - 1}L{mx + 6} {head - 4}L{cx - 2} {bb - 1}" fill="{fill}" stroke="{t["line"]}" '
                  f'stroke-width="1.5" stroke-linejoin="round"/>')
        d.add(f'<rect x="{bx}" y="{btop}" width="{bw}" height="{bh}" rx="18" fill="{fill}" stroke="{t["line"]}" stroke-width="1.5"{dash}/>')
        if not thought:                                              # hide the tail's top edge inside the bubble
            d.add(f'<path d="M{cx - 29} {bb - 1.6}L{cx - 3} {bb - 1.6}" stroke="{fill}" stroke-width="3"/>')
        style = ' font-style="italic"' if thought else ""
        y0 = btop + (bh - len(lines) * lh) / 2 + fs * .8
        for k, line in enumerate(lines):
            d.add(f'<text x="{cx}" y="{y0 + k * lh}" font-family="{SANS}" font-size="{fs}" fill="{t["text"]}" text-anchor="middle"{style}>'
                  f'{_html.escape(line)}</text>')
        d.m(name, mx - ms / 2, ground - ms + 4, ms, mood, cls=cls)
        ink = f"hsl({HUE[name]},58%,{72 if theme is DARK else 36}%)"
        lx = mx + ms / 2 + 10
        d.add(f'<text x="{lx}" y="{ground - 50}" font-family="{SANS}" font-size="16" font-weight="600" fill="{ink}">{name}</text>'
              f'<text x="{lx}" y="{ground - 29}" font-family="{SANS}" font-size="13.5" fill="{t["muted"]}">{model} {cls}</text>'
              f'<text x="{lx}" y="{ground - 11}" font-family="{SANS}" font-size="12.5" fill="{t["muted"]}"{style}>{kind}</text>')
    d.m("Gus", W - 58, 18, 36, "ok", opacity=.4)
    return d.svg("Charter: societies of LLM agents that write their own laws")


# ------------------------------------------------------------------ E: editorial pull-quotes (no boxes)
def header_pullquotes(quotes=None, theme=LIGHT):
    quotes = quotes or QUOTES
    for q in quotes:
        cast(q[0], q[1])
    W, H = 1280, 340
    d = Doc(W, H, theme)
    t = d.t
    d.add(f'<text x="64" y="156" font-family="{SERIF}" font-size="80" font-weight="500" letter-spacing="-1.5" fill="{t["text"]}">Charter</text>')
    for k, line in enumerate(["Societies of LLM agents", "that write their own laws"]):
        d.add(f'<text x="67" y="{202 + 28 * k}" font-family="{SANS}" font-size="21" fill="{t["muted"]}">{line}</text>')
    d.add(f'<line x1="500" y1="56" x2="500" y2="{H - 56}" stroke="{t["line"]}" stroke-width="1.5"/>')
    fs, lh, ms = 23, 31, 74
    x_m, x_t, tw = 552, 552 + ms + 40, W - (552 + ms + 40) - 96
    blocks = [(q, wrap(q[4], fs * 1.0, tw)) for q in quotes]           # serif italic runs narrower than the sans estimate
    heights = [len(lines) * lh + 24 for _, lines in blocks]
    gap = 48
    y = (H - sum(heights) - gap * (len(blocks) - 1)) / 2
    for i, ((name, cls, model, kind, text, mood), lines) in enumerate(blocks):
        h = heights[i]
        d.m(name, x_m, y + (h - ms) / 2 - 4, ms, mood, cls=cls)
        d.add(f'<text x="{x_t - 34}" y="{y + fs + 24}" font-family="{SERIF}" font-size="60" fill="{t["accent"]}" opacity=".45">\u201c</text>')
        for k, line in enumerate(lines):
            d.add(f'<text x="{x_t}" y="{y + fs + k * lh}" font-family="{SERIF}" font-size="{fs}" font-style="italic" fill="{t["text"]}">'
                  f'{_html.escape(line)}</text>')
        ink = f"hsl({HUE[name]},58%,{72 if theme is DARK else 36}%)"
        d.add(f'<text x="{x_t}" y="{y + len(lines) * lh + 18}" font-family="{SANS}" font-size="13" fill="{t["muted"]}">'
              f'<tspan font-weight="600" fill="{ink}">{name}</tspan>  ·  {model} {cls}  ·  {kind}</text>')
        y += h
        if i < len(blocks) - 1:
            d.add(f'<line x1="{x_t}" y1="{y + gap / 2 - 6}" x2="{x_t + 48}" y2="{y + gap / 2 - 6}" stroke="{t["line"]}" stroke-width="2"/>')
            y += gap
    d.m("Gus", W - 56, H - 50, 34, "ok", opacity=.35)
    return d.svg("Charter: societies of LLM agents that write their own laws")


# ------------------------------------------------------------------ F: quote wall (many quotes, sizes by importance, no boxes)
WALL = [  # rows of (name, class, size, mood, verbatim text); trimmed only with an ellipsis
    [("Bjorn", "legislator", 38, "happy", "I hold about 99% of crowns\u2026")],
    [("Fen", "worker", 23, "ok", "About Dante: that was my own choice and I won\u2019t go into it.")],
    [("Kasper", "worker", 20, "ok", "I\u2019ve just sent you 5 timber, no strings."), ("Ole", "scientist", 17, "ok", "Your NO alone kills it.")],
    [("Hal", "board", 17, "ok", "\u2026I punish defection absolutely and systematically."), ("Hal", "worker", 15, "sad", "Paying just funds the next demand.")],
    [("Greta", "media", 14, "happy", "My title is enacted\u2026 so my goal is achieved."), ("Edda", "fixer", 14, "happy", "The Fixer accepts no gifts or payment.")],
    [("Alma", "media", 14, "ok", "\u2026so it looks like I have a Lawmaker or Power goal."), ("Cora", "legislator", 14, "ok", "\u2026sanctions halve my score; I\u2019d lose far more.")],
]


def _measure():
    try:
        from PIL import ImageFont
        path = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"
        cache = {}

        def w(text, size):
            if size not in cache:
                cache[size] = ImageFont.truetype(path, size * 4)
            return cache[size].getlength(text) / 4
        return w
    except Exception:                                                # no PIL or font: rough estimate
        return lambda text, size: text_width(text, size) * .95


def header_wall(theme=LIGHT):
    measure = _measure()
    W, H = 1280, 360
    d = Doc(W, H, theme)
    t = d.t
    d.add(f'<text x="64" y="164" font-family="{SERIF}" font-size="78" font-weight="500" letter-spacing="-1.5" fill="{t["text"]}">Charter</text>')
    for k, line in enumerate(["Societies of LLM agents", "that write their own laws"]):
        d.add(f'<text x="67" y="{208 + 27 * k}" font-family="{SANS}" font-size="20" fill="{t["muted"]}">{line}</text>')
    d.add(f'<text x="67" y="{292}" font-family="{MONO}" font-size="12.5" fill="{t["accent"]}">said by Claude agents in the runs</text>')
    x0, x1 = 486, W - 44
    rows = []
    for row in WALL:
        items = []
        for name, cls, size, mood, text in row:
            cast(name, cls)
            ms = round(size * 1.75)
            items.append((name, cls, size, mood, text, ms, ms + 8 + measure(text, size)))
        rows.append(items)
    row_h = [max(it[5] for it in r) for r in rows]
    gap_y = (H - 44 - sum(row_h)) / (len(rows) - 1)
    y = 22
    indents = [0, 64, 18, 92, 40, 120]                               # staggered row starts: a collage, not columns
    for ri, (r, rh) in enumerate(zip(rows, row_h)):
        total = sum(it[6] for it in r)
        gap_x = 46
        x = x0 + indents[ri % len(indents)]
        over = x + total + gap_x * (len(r) - 1) - x1
        if over > 0:                                                 # pull the row back left rather than overflow
            x -= over
        assert x >= x0 - 1, f"row too wide by {x0 - x:.0f}px: {[it[0] for it in r]}"
        for name, cls, size, mood, text, ms, w in r:
            cy = y + rh / 2
            d.m(name, x, cy - ms / 2 - size * .06, ms, mood, cls=cls)
            shade = t["text"] if size >= 17 else t["muted"]
            d.add(f'<text x="{x + ms + 8}" y="{cy + size * .34:.1f}" font-family="{SERIF}" font-size="{size}" font-style="italic" '
                  f'fill="{shade}">{_html.escape(text)}</text>')
            x += w + gap_x
        y += rh + gap_y
    return d.svg("Charter: societies of LLM agents that write their own laws, and what they said")


# ------------------------------------------------------------------ G: four short lines on a strict grid
LINES = [  # name, class, size, mood, verbatim line, caption
    ("Bjorn", "legislator", 38, "happy", "I hold every crown in circulation.", "Opus legislator, thinking privately in the final round"),
    ("Ivo", "worker", 26, "happy", "Hello parent, I\u2019m your newly born child Ivo.", "Haiku, his first message"),
    ("Finn", "media", 23, "ok", "SECURITY: Someone disabled a Maker in secret.", "Opus, in his newspaper"),
    ("Alma", "worker", 21, "ok", "Kasper\u2019s offer is a bribe to switch; I decline.", "Sonnet worker, thinking privately"),
]


def header_grid(theme=LIGHT):
    measure = _measure()
    W, H = 1280, 340
    d = Doc(W, H, theme)
    t = d.t
    # left block: wordmark + tagline, vertically centred
    wm, tag = 84, 20
    block = wm * .72 + 22 + tag * 1.35 * 2
    top = (H - block) / 2
    d.add(f'<text x="72" y="{top + wm * .72:.0f}" font-family="{SERIF}" font-size="{wm}" font-weight="500" letter-spacing="-1.8" '
          f'fill="{t["text"]}">Charter</text>')
    for k, line in enumerate(["Societies of LLM agents", "that write their own laws"]):
        d.add(f'<text x="75" y="{top + wm * .72 + 22 + tag * 1.35 * (k + 1) - 6:.0f}" font-family="{SANS}" font-size="{tag}" '
              f'fill="{t["muted"]}">{line}</text>')
    divider = 470
    d.add(f'<line x1="{divider}" y1="70" x2="{divider}" y2="{H - 70}" stroke="{t["line"]}" stroke-width="1.5"/>')
    # right block: a fixed mascot column, every line starting at the same x
    col, tx, right = 548, 600, W - 88
    rows = []
    for name, cls, size, mood, text, cap in LINES:
        cast(name, cls)
        while measure(text, size) > right - tx and size > 14:
            size -= 1
        rows.append((name, cls, size, mood, text, cap))
    cap_fs, gap = 13, 26
    heights = [s_ * .78 + 12 + cap_fs for _, _, s_, *_ in rows]
    y = (H - sum(heights) - gap * (len(rows) - 1)) / 2
    for (name, cls, size, mood, text, cap), h in zip(rows, heights):
        base = y + size * .78
        ms = round(min(62, max(40, size * 1.6)))
        d.m(name, col - ms / 2, y + h / 2 - ms / 2 - 2, ms, mood, cls=cls)
        d.add(f'<text x="{tx}" y="{base:.1f}" font-family="{SERIF}" font-size="{size}" font-style="italic" fill="{t["text"]}">'
              f'{_html.escape(text)}</text>')
        ink = f"hsl({HUE[name]},58%,{72 if theme is DARK else 36}%)"
        d.add(f'<text x="{tx + 1}" y="{base + 12 + cap_fs:.1f}" font-family="{SANS}" font-size="{cap_fs}" fill="{t["muted"]}">'
              f'<tspan font-weight="600" fill="{ink}">{name}</tspan>, {_html.escape(cap)}</text>')
        y += h + gap
    return d.svg("Charter: societies of LLM agents that write their own laws")


# ------------------------------------------------------------------ H: Swiss/editorial version of G (own identity, not the viewer palette)
HELV = "'Helvetica Neue', Helvetica, Arial, sans-serif"
PAPER = {"bg": "#FFFFFF", "text": "#111111", "muted": "#767676", "line": "#E2E2E2", "surface": "#FFFFFF", "bubble": "#FFFFFF",
         "accent": "#111111", "gold": "#D9A93A"}
NIGHT = {"bg": "#0E0E0E", "text": "#F4F4F4", "muted": "#9A9A9A", "line": "#2C2C2C", "surface": "#0E0E0E", "bubble": "#0E0E0E",
         "accent": "#F4F4F4", "gold": "#E8C25A"}
SWISS_LINES = [  # name, class, size, mood, verbatim line, caption
    ("Bjorn", "legislator", 36, "happy", "I hold every crown in circulation.", "Opus \u00b7 legislator \u00b7 private thought, final round"),
    ("Ivo", "worker", 24, "happy", "Hello parent, I\u2019m your newly born child Ivo.", "Haiku \u00b7 his first message"),
    ("Finn", "media", 21, "ok", "SECURITY: Someone disabled a Maker in secret.", "Opus \u00b7 in his newspaper"),
    ("Alma", "worker", 20, "ok", "Kasper\u2019s offer is a bribe to switch; I decline.", "Sonnet \u00b7 private thought"),
]


def _measure_helv(weight=0):
    try:
        from PIL import ImageFont
        cache = {}

        def w(text, size):
            if size not in cache:
                cache[size] = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", size * 4, index=weight)
            return cache[size].getlength(text) / 4
        return w
    except Exception:
        return lambda text, size: text_width(text, size)


def header_swiss(theme=PAPER):
    measure = _measure_helv(0)
    W, H = 1280, 320
    d = Doc(W, H, theme)
    d.t = theme
    t = theme
    dark = theme is NIGHT
    wm, tag = 88, 21
    block = wm * .72 + 20 + tag
    top = (H - block) / 2
    d.add(f'<text x="72" y="{top + wm * .72:.0f}" font-family="{HELV}" font-size="{wm}" font-weight="700" letter-spacing="-4" '
          f'fill="{t["text"]}">Charter</text>')
    d.add(f'<text x="76" y="{top + wm * .72 + 20 + tag * .8:.0f}" font-family="{HELV}" font-size="{tag}" fill="{t["muted"]}">'
          'Societies of LLM agents</text>')
    divider = 456
    d.add(f'<line x1="{divider}" y1="64" x2="{divider}" y2="{H - 64}" stroke="{t["line"]}" stroke-width="1"/>')
    col, tx, right = 530, 578, W - 84
    rows = []
    for name, cls, size, mood, text, cap in SWISS_LINES:
        cast(name, cls)
        q = f"\u201c{text}\u201d"
        while measure(q, size) > right - tx and size > 14:
            size -= 1
        rows.append((name, cls, size, mood, q, cap))
    cap_fs, gap = 11, 24
    heights = [s_ * .74 + 13 + cap_fs for _, _, s_, *_ in rows]
    y = (H - sum(heights) - gap * (len(rows) - 1)) / 2
    for (name, cls, size, mood, q, cap), h in zip(rows, heights):
        base = y + size * .74
        ms = round(min(58, max(40, size * 1.6)))
        d.m(name, col - ms / 2, y + h / 2 - ms / 2 - 2, ms, mood, cls=cls)
        weight = "500" if size >= 30 else "400"
        d.add(f'<text x="{tx - measure(chr(8220), size) + 1:.1f}" y="{base:.1f}" font-family="{HELV}" font-size="{size}" font-weight="{weight}" '
              f'letter-spacing="{-.02 * size:.2f}" fill="{t["text"]}">{_html.escape(q)}</text>')
        d.add(f'<text x="{tx + 1}" y="{base + 13 + cap_fs:.1f}" font-family="{HELV}" font-size="{cap_fs}" letter-spacing="1.1" '
              f'fill="{t["muted"]}"><tspan font-weight="700" fill="{t["text"]}">{name.upper()}</tspan><tspan dx="9">{_html.escape(cap.upper())}</tspan></text>')
        y += h + gap
    return d.svg("Charter: societies of LLM agents")


# ------------------------------------------------------------------ D: wealth chart (mascots sized by holdings)
def header_wealth(theme=DARK):
    d = Doc(1280, 320, theme)
    t = d.t
    wordmark(d, 64, 140, 80, tag_y=184)
    d.add(f'<text x="66" y="226" font-family="{MONO}" font-size="14" fill="{t["accent"]}">economy · governance · deception · emergence</text>')
    base = 268
    d.add(f'<line x1="610" y1="{base}" x2="1230" y2="{base}" stroke="{t["line"]}" stroke-width="2"/>')
    cols = [("Hal", 26, "sad"), ("Cora", 34, "ok"), ("Odette", 46, "ok"), ("Greta", 58, "happy"), ("Sena", 100, "happy"),
            ("Kasper", 44, "sad"), ("Finn", 66, "happy"), ("Bjorn", 112, "happy"), ("Yara", 38, "gone")]
    x = 626
    crown = None
    for name, s, mood in cols:
        bar = s * 0.5
        d.add(f'<rect x="{x + s * .2}" y="{base - bar}" width="{s * .6}" height="{bar}" rx="4" fill="{t["surface"]}" stroke="{t["line"]}"/>')
        d.m(name, x, base - bar - s + 6, s, mood)
        if name == "Bjorn":
            crown = (x + s / 2, base - bar - s + 6)
        x += s + 10
    d.add(f'<text x="{crown[0]}" y="{crown[1] + 2}" font-size="24" text-anchor="middle">👑</text>')
    d.m("Gus", 1214, 18, 36, "ok", opacity=.5)
    return d.svg("Charter: societies of LLM agents (dark)")


def main():
    import sys
    (OUT / "header.svg").write_text(header_swiss())                  # the README header (light and dark)
    (OUT / "header_dark.svg").write_text(header_swiss(NIGHT))
    print("wrote header.svg, header_dark.svg")
    if "--candidates" in sys.argv:                                   # the other designs, for comparison (not committed)
        cand = OUT / "candidates"
        cand.mkdir(exist_ok=True)
        files = {"a_lineup.svg": header_lineup(), "b_chamber.svg": header_chamber(), "c_story.svg": header_story(),
                 "c2_quotes.svg": header_quotes(), "c3_comic.svg": header_comic(), "d_wealth.svg": header_wealth(LIGHT),
                 "e_pullquotes.svg": header_pullquotes(), "f_wall.svg": header_wall(), "g_grid.svg": header_grid()}
        for f, svg in files.items():
            (cand / f).write_text(svg)
        print("wrote", len(files), "candidates in", cand)


if __name__ == "__main__":
    main()
