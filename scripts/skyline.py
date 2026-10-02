#!/usr/bin/env python3
"""Render the contribution skyline: a year of GitHub activity as an isometric SVG.

A static port of the ContributionSkyline React component for the profile
README, where scripts can't run. The maths (grid, levels, stats, bar heights,
camera) mirrors the component's pure region; the drawing is its 3D view, and
the bars rise in the same oldest-week-to-newest wave using SMIL, which GitHub
plays inside images.

    python scripts/skyline.py            # fetch real data, write assets/skyline-{light,dark}.svg
    python scripts/skyline.py --sample   # seeded demo year, for previewing offline
    python scripts/skyline.py --json contributions.json   # just the data, for the portfolio's live chart

Run by .github/workflows/sync-prs.yml. If the data can't be fetched, the
existing images are left alone and the script exits 0 so the PR sync still runs.
"""
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.request

USER = "YousufFFFF"
DAY = dt.timedelta(days=1)

# ------------------------------------------------------------------ data --
def _request(url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, headers=dict({"User-Agent": "skyline"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def fetch_graphql():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    query = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{"
             "weeks{contributionDays{date contributionCount}}}}}}")
    raw = _request("https://api.github.com/graphql",
                   json.dumps({"query": query, "variables": {"login": USER}}).encode(),
                   {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    weeks = json.loads(raw)["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [{"date": d["date"], "count": d["contributionCount"]} for w in weeks for d in w["contributionDays"]]


def fetch_profile_page():
    """The public calendar on the profile page: day cells carry a date, tooltips carry the count."""
    page = _request("https://github.com/users/%s/contributions" % USER)
    dates = dict(re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?id="([^"]+)"', page))
    dates.update({i: d for i, d in re.findall(r'id="([^"]+)"[^>]*?data-date="(\d{4}-\d{2}-\d{2})"', page)})
    out = []
    for target, text in re.findall(r'<tool-tip[^>]*?for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        date = dates.get(target)
        if not date:
            continue
        m = re.match(r"\s*([\d,]+) contribution", text)
        out.append({"date": date, "count": int(m.group(1).replace(",", "")) if m else 0})
    return out or None


def sample_year(end, seed=7, days=371):
    """A believable demo year (port of generateContributions), for offline previews."""
    state = [seed & 0xFFFFFFFF]

    def r():  # mulberry32
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    bursts = [(r(), 0.035 + r() * 0.07, 0.6 + r() * 1.1) for _ in range(4)]
    out, mood = [], 0.5
    for i in range(days):
        day = end - (days - 1 - i) * DAY
        x = i / max(1, days - 1)
        weekend = day.weekday() >= 5
        heat = 0.2 + sum(g * math.exp(-((x - a) ** 2) / (2 * w ** 2)) for a, w, g in bursts)
        mood = mood * 0.85 + r() * 0.15
        heat *= 0.55 + mood * 0.9
        count = 0
        if r() < min(0.94, (0.22 if weekend else 0.5) + heat * 0.4):
            count = 1 + int(-math.log(1 - r()) * (1.2 + heat * 7) * (0.5 if weekend else 1))
        if r() < 0.01:
            count += 18 + int(r() * 24)
        out.append({"date": day.isoformat(), "count": count})
    return out


# ------------------------------------------------- maths (mirrors the component) --
def level_of(count, busy):
    return 0 if count <= 0 else 4 if busy <= 0 else 1 + min(3, int(count / busy * 4))


def build_grid(data, end, week_start=0):
    counts = {}
    for d in data:
        if d["count"] > 0:
            counts[d["date"]] = counts.get(d["date"], 0) + d["count"]
    start = end - 364 * DAY
    start -= ((start.isoweekday() % 7 - week_start + 7) % 7) * DAY   # isoweekday%7: Sunday = 0
    cells, day, i = [], start, 0
    while day <= end:
        key = day.isoformat()
        cells.append({"date": key, "count": counts.get(key, 0), "week": i // 7, "day": i % 7})
        day += DAY
        i += 1
    nz = sorted(c["count"] for c in cells if c["count"] > 0)
    busy = nz[int(0.95 * (len(nz) - 1))] if nz else 0
    for c in cells:
        c["level"] = level_of(c["count"], busy)
    return cells, (cells[-1]["week"] + 1 if cells else 0), (nz[-1] if nz else 0)


def compute_stats(cells):
    total = best = run = 0
    best_date = run_start = None
    longest = (0, None, None)
    for c in cells:
        total += c["count"]
        if c["count"] > best:
            best, best_date = c["count"], c["date"]
        if c["count"] > 0:
            if run == 0:
                run_start = c["date"]
            run += 1
            if run > longest[0]:
                longest = (run, run_start, c["date"])
        else:
            run = 0
    j = len(cells) - 1
    if j >= 0 and cells[j]["count"] == 0:
        j -= 1          # today isn't over yet; a streak may still end yesterday
    end_at = j
    while j >= 0 and cells[j]["count"] > 0:
        j -= 1
    days = end_at - j
    current = (days, cells[j + 1]["date"], cells[end_at]["date"]) if days > 0 else (0, None, None)
    return dict(total=total, first=cells[0]["date"], last=cells[-1]["date"],
                busiest=(best, best_date), longest=longest, current=current)


def month_labels(cells, weeks):
    out, prev = [], -1
    for w in range(weeks):
        if w * 7 >= len(cells):
            break
        date = cells[w * 7]["date"]
        m = int(date[5:7])
        if m != prev:
            out.append((w, dt.date.fromisoformat(date).strftime("%b")))
        prev = m
    if len(out) > 1 and out[1][0] - out[0][0] < 3:
        out.pop(0)
    return out


def bar_height(count, peak, scale=1.0):
    return 0.4 + (count / peak) ** 0.85 * 7.2 * scale if count > 0 and peak > 0 else 0.2


WAVE = 0.42


def rise_delay(week, weeks, day):
    """Share of the animation a bar waits before rising (riseAt's offset)."""
    return (week / (weeks - 1) if weeks > 1 else 0) * 0.36 + (day / 6) * 0.06


YAW, ELEV = math.pi / 4, math.radians(34)
CS, SN, SE, CE = math.cos(YAW), math.sin(YAW), math.sin(ELEV), math.cos(ELEV)


def project(x, y, z):
    return x * CS - y * SN, (x * SN + y * CS) * SE - z * CE


# ----------------------------------------------------------------- render --
PALETTES = {
    "light": ["#c6e48b", "#7bc96f", "#239a3b", "#196127"],
    "dark": ["#0e4429", "#006d32", "#26a641", "#39d353"],
}
THEMES = {
    # background, foreground, border, muted text; tuned to sit on GitHub's own page colours
    "light": dict(bg=(255, 255, 255), fg=(23, 23, 23), border="#d0d7de", muted="#656d76", empty_mix=0.075),
    "dark": dict(bg=(13, 17, 23), fg=(230, 237, 243), border="#30363d", muted="#8b949e", empty_mix=0.11),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rgb(c, k=1.0):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * k))) for v in c)


def fmt_range(a, b, year=False):
    if not a or not b:
        return "—"
    f = (lambda d: "%s %d, %d" % (d.strftime("%b"), d.day, d.year)) if year else (lambda d: "%s %d" % (d.strftime("%b"), d.day))
    return "%s — %s" % (f(dt.date.fromisoformat(a)), f(dt.date.fromisoformat(b)))


def render(data, end, theme, animate=True):
    th = THEMES[theme]
    cells, weeks, peak = build_grid(data, end)
    stats = compute_stats(cells)
    months = month_labels(cells, weeks)
    n = len(cells)
    heights = [bar_height(c["count"], peak) for c in cells]

    # ---- layout: card > header, inner box > stage + footer ----
    WIDTH, PAD, INNER = 980, 20, 16
    W = WIDTH - 2 * PAD - 2 * INNER                     # stage width
    w, off = 0.9, 0.05

    def extent():
        xs, ys = [], []
        for i, c in enumerate(cells):
            x0, y0, z = c["week"] + off, c["day"] + off, heights[i]
            for px, py, pz in ((x0, y0, z), (x0 + w, y0, z), (x0, y0 + w, z),
                               (x0 + w, y0 + w, 0), (x0, y0 + w, 0), (x0 + w, y0, 0)):
                sx, sy = project(px, py, pz)
                xs.append(sx); ys.append(sy)
        for x in (0, weeks):                            # room for the front-edge month labels
            sx, sy = project(x, 8.5, 0)
            xs.append(sx); ys.append(sy)
        return min(xs), max(xs), min(ys), max(ys)

    minx, maxx, miny, maxy = extent()
    bw, bh = maxx - minx, maxy - miny
    natural = bh / bw * (W - 40) + 40
    H = max(min(natural, W * 0.72, 620), min(natural, 240))
    pad = 20
    s = min((W - 2 * pad) / bw, (H - 2 * pad) / bh)
    stage_x = PAD + INNER
    stage_y = PAD + 30 + 14 + INNER
    ox = stage_x + pad + ((W - 2 * pad) - bw * s) / 2 - minx * s
    oy = stage_y + pad + ((H - 2 * pad) - bh * s) / 2 - miny * s
    footer_y = stage_y + H + 14
    box_h = INNER + H + 14 + 30
    total_h = round(stage_y - INNER + box_h + PAD)

    def pt(x, y, z):
        sx, sy = project(x, y, z)
        return "%.1f,%.1f" % (ox + sx * s, oy + sy * s)

    fg, bg = th["fg"], th["bg"]
    empty = tuple(b + (f - b) * th["empty_mix"] for b, f in zip(bg, fg))
    colours = [empty] + [hex_rgb(h) for h in PALETTES[theme]]
    accent = PALETTES[theme][3]

    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
           'role="img" aria-label="%s contributions in the last year, shown as a 3D skyline" '
           'font-family="%s">' % (WIDTH, total_h, WIDTH, total_h, "{:,}".format(stats["total"]), html.escape(FONT, quote=True))]
    out.append('<rect x=".5" y=".5" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
               % (WIDTH - 1, total_h - 1, rgb(bg), th["border"]))
    out.append('<text x="%d" y="%d" font-size="15" fill="%s"><tspan font-weight="600">%s</tspan> %s in the last year</text>'
               % (PAD, PAD + 20, rgb(fg), "{:,}".format(stats["total"]), "contribution" if stats["total"] == 1 else "contributions"))
    out.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" rx="8" fill="none" stroke="%s"/>'
               % (PAD + .5, stage_y - INNER + .5, WIDTH - 2 * PAD - 1, box_h - 1, th["border"]))

    # ---- bars, back to front ----
    DUR = 1.8
    order = sorted(range(n), key=lambda i: (cells[i]["week"] + .5) * SN + (cells[i]["day"] + .5) * CS)
    out.append('<g stroke-linejoin="round">')
    for i in order:
        c = cells[i]
        x0, y0 = c["week"] + off, c["day"] + off
        x1, y1 = x0 + w, y0 + w
        z = heights[i]
        faces = [  # (points at height z, shade) — +y face, +x face, top
            (lambda z: " ".join((pt(x0, y1, 0), pt(x1, y1, 0), pt(x1, y1, z), pt(x0, y1, z))), 0.84),
            (lambda z: " ".join((pt(x1, y0, 0), pt(x1, y1, 0), pt(x1, y1, z), pt(x1, y0, z))), 0.68),
            (lambda z: " ".join((pt(x0, y0, z), pt(x1, y0, z), pt(x1, y1, z), pt(x0, y1, z))), 1.0),
        ]
        col = colours[c["level"]]
        rises = animate and c["count"] > 0
        d = rise_delay(c["week"], weeks, c["day"])
        for shape, shade in faces:
            full = shape(z)
            if rises:
                flat = shape(0)
                k2 = min(1.0, d + (1 - WAVE))
                if k2 >= 0.999:
                    anim = ('values="%s;%s;%s" keyTimes="0;%.3f;1" keySplines="0 0 1 1;.33 1 .68 1"'
                            % (flat, flat, full, d))
                else:
                    anim = ('values="%s;%s;%s;%s" keyTimes="0;%.3f;%.3f;1" keySplines="0 0 1 1;.33 1 .68 1;0 0 1 1"'
                            % (flat, flat, full, full, d, k2))
                out.append('<polygon points="%s" fill="%s"><animate attributeName="points" dur="%ss" fill="freeze" '
                           'calcMode="spline" %s/></polygon>' % (full, rgb(col, shade), DUR, anim))
            else:
                out.append('<polygon points="%s" fill="%s"/>' % (full, rgb(col, shade)))
    out.append("</g>")

    # ---- month labels along the front edge ----
    muted = th["muted"]
    edge = -1e9
    for week, label in months:
        sx, sy = project(week + 0.5, 7.3, 0)
        x, y = ox + sx * s, oy + sy * s
        tw = len(label) * 6.2
        if x < edge or x + tw > stage_x + W:
            continue
        out.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s">%s</text>' % (x, y + 11, muted, label))
        edge = x + tw + 10

    # ---- corner stats (top-right and bottom-left, where the skyline leaves room) ----
    big = round(max(30, min(56, W * 0.058)))
    n_unit = lambda v, one, many: one if v == 1 else many
    blocks = [
        ("1 year total", stats["total"], n_unit(stats["total"], "contribution", "contributions"), fmt_range(stats["first"], stats["last"], True)),
        ("Busiest day", stats["busiest"][0], n_unit(stats["busiest"][0], "contribution", "contributions"),
         dt.date.fromisoformat(stats["busiest"][1]).strftime("%b %-d") if stats["busiest"][1] else "—"),
        ("Longest streak", stats["longest"][0], n_unit(stats["longest"][0], "day", "days"), fmt_range(stats["longest"][1], stats["longest"][2])),
        ("Current streak", stats["current"][0], n_unit(stats["current"][0], "day", "days"), fmt_range(stats["current"][1], stats["current"][2])),
    ]
    block_h = 13 + 6 + big + 18

    def stat(x, y, anchor, label, value, unit, sub, delay):
        g = ['<g opacity="%d">' % (0 if animate else 1)]
        if animate:
            g.append('<animate attributeName="opacity" from="0" to="1" begin="%.2fs" dur=".6s" fill="freeze"/>' % delay)
        g.append('<text x="%.1f" y="%.1f" font-size="13" fill="%s" text-anchor="%s">%s</text>' % (x, y + 12, muted, anchor, label))
        g.append('<text x="%.1f" y="%.1f" text-anchor="%s"><tspan font-size="%d" font-weight="600" fill="%s" letter-spacing="-1">%s</tspan>'
                 '<tspan font-size="15" fill="%s" dx="6">%s</tspan></text>'
                 % (x, y + 19 + big * 0.82, anchor, big, accent, "{:,}".format(value), rgb(fg), unit))
        g.append('<text x="%.1f" y="%.1f" font-size="12" fill="%s" text-anchor="%s">%s</text>'
                 % (x, y + 19 + big + 13, muted, anchor, sub))
        g.append("</g>")
        return "".join(g)

    right, left = stage_x + W - 4, stage_x + 4
    out.append(stat(right, stage_y + 4, "end", *blocks[0], DUR * 0.55))
    out.append(stat(right, stage_y + 4 + block_h + 14, "end", *blocks[1], DUR * 0.6))
    bottom = stage_y + H - 4 - 2 * block_h - 14
    out.append(stat(left, bottom, "start", *blocks[2], DUR * 0.65))
    out.append(stat(left, bottom + block_h + 14, "start", *blocks[3], DUR * 0.7))

    # ---- footer: note + legend ----
    fy = footer_y + 16
    out.append('<text x="%d" y="%.1f" font-size="12" fill="%s">Updated daily from github.com/%s</text>' % (stage_x, fy + 4, muted, USER))
    lx = stage_x + W - 30
    out.append('<text x="%d" y="%.1f" font-size="12" fill="%s" text-anchor="start">More</text>' % (lx, fy + 4, muted))
    for k in range(4, -1, -1):
        lx -= 15
        out.append('<rect x="%d" y="%.1f" width="11" height="11" rx="2" fill="%s"/>' % (lx, fy - 6, rgb(colours[k])))
    out.append('<text x="%d" y="%.1f" font-size="12" fill="%s" text-anchor="end">Less</text>' % (lx - 5, fy + 4, muted))
    out.append("</svg>")
    return "\n".join(out), stats


def main():
    sample = "--sample" in sys.argv
    data = None
    if sample:
        data = sample_year(dt.date.today())
    else:
        for fetch in (fetch_graphql, fetch_profile_page):
            try:
                data = fetch()
            except Exception as exc:  # network, auth or markup changes: try the next source
                print("note: %s failed: %s" % (fetch.__name__, exc))
                data = None
            if data:
                print("data: %d days via %s" % (len(data), fetch.__name__))
                break
    if not data:
        print("warning: no contribution data; leaving the skyline images unchanged")
        return 0
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--json" in sys.argv:
        path = os.path.join(root, sys.argv[sys.argv.index("--json") + 1])
        days = sorted(({"date": d["date"], "count": d["count"]} for d in data), key=lambda d: d["date"])
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(days, fh, separators=(",", ":"))
            fh.write("\n")
        print("data: wrote %d days to %s" % (len(days), os.path.relpath(path, root)))
        return 0
    end = max(dt.date.fromisoformat(d["date"]) for d in data)
    out_dir = os.path.join(root, "assets")
    os.makedirs(out_dir, exist_ok=True)
    for theme in ("light", "dark"):
        svg, stats = render(data, end, theme)
        path = os.path.join(out_dir, "skyline-%s.svg" % theme)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(svg + "\n")
    print("skyline: %d contributions, busiest %d, longest streak %d, current %d"
          % (stats["total"], stats["busiest"][0], stats["longest"][0], stats["current"][0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
