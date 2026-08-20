#!/usr/bin/env python3
"""Sync merged-PR content into the portfolio (index.html) and/or profile README.md.

Run by .github/workflows/sync-prs.yml on a schedule. Fetches every merged PR
authored by USER in repos they don't own, then regenerates the marked regions:

  index.html   AUTO:STATS   AUTO:CARDS
  README.md    AUTO:SUMMARY AUTO:TABLES

Everything outside those markers is hand-written and never touched.
Exits 0 with "no changes" when nothing moved, so the workflow skips the commit.
"""
import json
import os
import re
import sys
import urllib.request

USER = "YousufFFFF"
API = "https://api.github.com"

# ---------------------------------------------------------------- projects --
# Display order. `repos` match "owner/name". A repo not listed here still gets
# counted and rendered, using generic defaults, so new orgs appear on their own.
PROJECTS = [
    dict(
        key="mifos", name="Mifos X Web App",
        repos=["openMF/web-app", "openMF/selfservice-plugin"],
        url="https://github.com/openMF/web-app",
        badge_class="mifos", badge="MSOC 2026 · Intern", star_repo=None,
        meta="Feb 2026 – present · UI Product Templates · fintech in 40+ countries · {n} merged PRs",
        desc=("Building the loan product creation experience — a 7-step Angular Material stepper with "
              "hidden-defaults payload logic and human-readable review UX. Shipped a library of "
              "<b>{templates} loan product templates</b> — BNPL, gold, auto, JLG, home, mortgage and more — "
              "plus white-label theming down to the Fineract backend."),
        more="https://github.com/search?q=author%3AYousufFFFF+org%3AopenMF+is%3Amerged&type=pullrequests",
        more_text="all {n} Mifos PRs →", show=4,
        md_title="🏦 Mifos X — Merged PRs", md_top=7, md_icon="🏦",
    ),
    dict(
        key="superset", name="Apache Superset", repos=["apache/superset"],
        url="https://github.com/apache/superset",
        badge_class="superset", badge="{stars} · {n} merged PRs", star_repo="apache/superset",
        meta="Nov 2025 – present · ECharts &amp; deck.gl plugin internals",
        desc=("Fixes merged into the visualization engine — tagged "
              '<code style="font-family:var(--mono);font-size:12.5px;color:var(--accent2)">v6.0</code> and '
              '<code style="font-family:var(--mono);font-size:12.5px;color:var(--accent2)">viz:charts:echarts</code>.'),
        more="https://github.com/apache/superset/pulls?q=is%3Apr+author%3AYousufFFFF",
        more_text="all Superset PRs →", show=4,
        md_title="📊 Apache Superset — Merged PRs", md_top=99, md_icon="📊",
        md_summary="**Apache Superset** ({stars}) — fixes in ECharts & deck.gl rendering internals, shipped in `v6.0`",
    ),
    dict(
        key="headlamp", name="Headlamp", repos=["kubernetes-sigs/headlamp"],
        url="https://github.com/kubernetes-sigs/headlamp",
        badge_class="k8s", badge="{stars} · Kubernetes SIGs", star_repo="kubernetes-sigs/headlamp",
        meta="Aug 2026 · CNCF · extensible Kubernetes web UI",
        desc=("Contributing to the official Kubernetes SIGs dashboard — a fully-featured web UI for "
              "managing Kubernetes clusters."),
        more="https://github.com/kubernetes-sigs/headlamp/pulls?q=is%3Apr+author%3AYousufFFFF",
        more_text="all Headlamp PRs →", show=4,
        md_title="☸️ Headlamp (Kubernetes SIGs) — Merged PRs", md_top=99, md_icon="☸️",
        md_summary="**Kubernetes SIGs** — merged into Headlamp ({stars}), the CNCF Kubernetes web UI",
        md_blurb=("[Headlamp](https://github.com/kubernetes-sigs/headlamp) is the CNCF / Kubernetes SIGs web UI "
                  "for managing clusters — fully-featured, user-friendly and extensible."),
    ),
    dict(
        key="riscv", name="RISC-V Unified Database", repos=["riscv/riscv-unified-db"],
        url="https://github.com/riscv/riscv-unified-db",
        badge_class="riscv", badge="RISC-V International · Contributor", star_repo=None,
        meta="Jul 2026 – present · machine-readable database of the RISC-V ISA specification",
        desc=("Contributing to the official RISC-V spec database — the source of truth that generates the "
              "ISA manuals, compliance tests and tooling used across the RISC-V ecosystem."),
        more="https://github.com/riscv/riscv-unified-db/pulls?q=is%3Apr+author%3AYousufFFFF",
        more_text="all RISC-V PRs →", show=4,
        md_title="⚙️ RISC-V Unified Database — Merged PRs", md_top=99, md_icon="⚙️",
        md_summary="**RISC-V International** — merged into the official machine-readable ISA specification database",
        md_blurb=("The official machine-readable database of the RISC-V ISA specification, maintained by "
                  "RISC-V International — it generates the ISA manuals, compliance tests and tooling used "
                  "across the ecosystem."),
    ),
]

# Curated one-liners keyed by PR number. A PR without one falls back to its
# cleaned-up title, so newly merged work shows up without any edit here.
HIGHLIGHTS = {
    3874: "<b>Consumer Durable template</b> — latest addition to the loan product library",
    3866: "<b>JLG template</b> — Joint Liability Group lending, core to group microfinance",
    3863: "<b>Auto loan template</b> — vehicle financing product",
    3856: "<b>Gold loan template</b> — collateral-backed lending product",
    3840: "<b>Home &amp; mortgage products</b> — long-tenure secured lending templates",
    3838: "<b>Theme translation &amp; brand colours</b> — localized theme page with custom hex support",
    3830: "<b>BNPL product template</b> — implemented the Buy Now Pay Later loan product",
    3784: "<b>Theme management</b> — tenant-level theming page for white-labelled deployments",
    3764: "<b>New loan products</b> — Two Wheeler, Education and Agricultural templates",
    3701: "<b>Product Templates launch</b> — landing page with personal &amp; advance loan flows",
    188: "<b>Backend — tenant theming API</b> — Fineract plugin endpoints for branding &amp; custom colours",
    184: "<b>Backend — tenant branding API</b> — Fineract plugin endpoint serving branding to client apps",
    38126: "<b>Time shift handling</b> — corrected time-shift logic in Timeseries transformProps",
    37244: ('<b>WebGL freeze fix</b> — clamped &amp; auto-scaled '
            '<code style="font-family:var(--mono);font-size:12px">cellSize</code> in deck.gl contour '
            'to prevent GPU hangs'),
    37217: "<b>Legend dedup</b> — killed duplicate legend entries in mixed timeseries charts",
    36306: "<b>Scroll legend</b> — stopped label collisions in horizontal ECharts layouts",
    36264: "<b>Docs</b> — clarified duplicate report delivery for Alerts &amp; Reports",
    6844: ("<b>Node shell error surfacing</b> — made pod creation failures visible in NodeShellTerminal "
           "instead of failing silently"),
    2264: ('<b>Floating-point CSR pseudoinstructions</b> — added '
           '<code style="font-family:var(--mono);font-size:12px">fscsr</code>, '
           '<code style="font-family:var(--mono);font-size:12px">fsrm</code> and '
           '<code style="font-family:var(--mono);font-size:12px">fsflags</code> to the '
           '<code style="font-family:var(--mono);font-size:12px">csrrw</code> instruction definition'),
}

# Loan product templates. Titles like "Implement the gold loan product template"
# are detected automatically, so newly shipped templates count themselves; this
# map only overrides PRs that shipped several at once (or whose title is vaguer).
TEMPLATE_PRS = {3701: 2, 3764: 3, 3840: 2}
TEMPLATE_RE = re.compile(r"\b(implement|add)\b.*\bloan product", re.I)
NOT_TEMPLATE_RE = re.compile(r"creation|wizard|localization", re.I)


def templates_in(pr):
    """Number of loan product templates a PR shipped (0 if it isn't one)."""
    if pr["number"] in TEMPLATE_PRS:
        return TEMPLATE_PRS[pr["number"]]
    title = pr["title"]
    if TEMPLATE_RE.search(title) and not NOT_TEMPLATE_RE.search(title):
        return 1
    return 0

# Optional emoji for README table rows, keyed by PR number.
MD_EMOJI = {
    3878: "💳", 3874: "🛋️", 3866: "🤝", 3863: "🚗", 3856: "🥇", 3840: "🏠", 3830: "💳",
    3838: "🎨", 3784: "🖌️", 3764: "🛵", 3701: "🚀", 188: "🔌", 184: "🔌",
    38126: "⏱️", 37244: "🧊", 37217: "👯", 36306: "📜", 36264: "📝", 6844: "🐚", 2264: "🧮",
}


def anchor(heading):
    """Reproduce GitHub's heading-anchor ids.

    Emoji are dropped (leaving the space that preceded them, hence a leading
    hyphen), but a trailing VARIATION SELECTOR-16 survives -- so "☸️ Headlamp"
    anchors to "️-headlamp", not "-headlamp". Verified against the rendered
    README via the GitHub API.
    """
    s = heading.lower()
    s = "".join(c for c in s if c == "️" or c.isalnum() or c in " -_")
    return s.replace(" ", "-")


# ------------------------------------------------------------------- github --
def _get(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "sync-prs",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_merged():
    """Every merged PR by USER in repos they don't own, newest first."""
    out, page = [], 1
    while page <= 10:
        data = _get("%s/search/issues?q=author:%s+type:pr+is:merged&per_page=100&page=%d" % (API, USER, page))
        items = data.get("items", [])
        for it in items:
            repo = "/".join(it["repository_url"].split("/")[-2:])
            if repo.lower().startswith(USER.lower() + "/"):
                continue  # own repos don't count as external contributions
            out.append(dict(repo=repo, number=it["number"], title=it["title"],
                            url=it["html_url"],
                            merged=(it.get("pull_request", {}).get("merged_at") or "")[:10]))
        if len(items) < 100:
            break
        page += 1
    out.sort(key=lambda p: (p["merged"], p["number"]), reverse=True)
    return out


def stars(repo):
    if not repo:
        return ""
    try:
        n = _get("%s/repos/%s" % (API, repo))["stargazers_count"]
    except Exception:
        return ""
    return "%.0fK ★" % (n / 1000.0) if n >= 1000 else "%d ★" % n


# ------------------------------------------------------------------ shaping --
def clean_title(title):
    """'WEB-1156: Implement X' -> '<b>WEB-1156</b> — Implement X'."""
    t = re.sub(r"^(?:feat|fix|docs|chore|refactor|perf|test)\((.+?)\):\s*", r"\1: ", title).strip()
    t = t.replace("&", "&amp;")
    m = re.match(r"^([A-Z]{2,}-\d+):\s*(.+)$", t)
    if m:
        body = m.group(2).strip()
        return "<b>%s</b> — %s" % (m.group(1), body[:1].upper() + body[1:])
    return t[:1].upper() + t[1:]


def describe(pr):
    return HIGHLIGHTS.get(pr["number"]) or clean_title(pr["title"])


def to_md(html):
    """Turn a highlight into GitHub-markdown-safe text."""
    s = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", html)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&amp;", "&").replace("|", "\\|")


def group(prs):
    """[(project, its PRs)], with unlisted repos appended as their own project."""
    groups, known = [], set()
    for proj in PROJECTS:
        known.update(proj["repos"])
        mine = [p for p in prs if p["repo"] in proj["repos"]]
        if mine:
            groups.append((proj, mine))
    extra = {}
    for p in prs:
        if p["repo"] not in known:
            extra.setdefault(p["repo"], []).append(p)
    for repo, mine in sorted(extra.items()):
        owner, name = repo.split("/")
        pretty = name.replace("-", " ").title()
        groups.append((dict(
            key=repo, name=pretty, repos=[repo], url="https://github.com/" + repo,
            badge_class="riscv", badge="%s · Contributor" % owner, star_repo=repo,
            meta="%s · %s" % (mine[-1]["merged"], repo),
            desc="Contributing to <a href=\"https://github.com/%s\" target=\"_blank\" rel=\"noopener\">%s</a>." % (repo, repo),
            more="https://github.com/%s/pulls?q=is%%3Apr+author%%3A%s" % (repo, USER),
            more_text="all %s PRs →" % pretty, show=4,
            md_title="🧩 %s — Merged PRs" % pretty, md_top=99, _new=True,
        ), mine))
    return groups


def replace_block(text, name, body):
    """Swap whatever sits between <!-- AUTO:name:START/END --> markers."""
    pat = re.compile(r"(<!-- AUTO:%s:START -->)(.*?)(<!-- AUTO:%s:END -->)" % (name, name), re.S)
    if not pat.search(text):
        sys.stderr.write("warning: marker AUTO:%s not found\n" % name)
        return text
    end = re.search(r"([ \t]*)<!-- AUTO:%s:END -->" % name, text)
    pad = end.group(1) if end else ""
    return pat.sub(lambda m: m.group(1) + "\n" + body.rstrip() + "\n" + pad + m.group(3), text)


# ------------------------------------------------------------------- render --
def render_html(groups, total, star_map):
    mifos = next((g for p, g in groups if p["key"] == "mifos"), [])
    templates = sum(templates_in(p) for p in mifos)

    stats = [(total, "Merged PRs"), (40, "Countries Impacted", "+"),
             (len(groups), "Major OSS Orgs")]
    rows = []
    for s in stats:
        suffix = ' data-suffix="%s"' % s[2] if len(s) > 2 else ""
        rows.append('    <div class="hstat"><div class="num" data-count="%d"%s>0</div>'
                    '<div class="lbl">%s</div></div>' % (s[0], suffix, s[1]))
    stats_html = "\n".join(rows)

    cards = []
    for proj, mine in groups:
        n = len(mine)
        fmt = dict(n=n, templates=templates, stars=star_map.get(proj["key"], ""))
        items = "\n".join(
            '        <li><a class="pr-id" href="%s" target="_blank" rel="noopener">#%d</a>'
            '<span class="pr-txt">%s</span></li>' % (p["url"], p["number"], describe(p))
            for p in mine[: proj["show"]])
        cards.append(
            '    <div class="os-card reveal">\n'
            '      <div class="os-head">\n'
            '        <div class="os-name"><a href="%s" target="_blank" rel="noopener">%s</a></div>\n'
            '        <div class="os-badge %s">%s</div>\n'
            '      </div>\n'
            '      <div class="os-meta">%s</div>\n'
            '      <p class="os-desc">%s</p>\n'
            '      <ul class="pr-list">\n%s\n      </ul>\n'
            '      <a class="pr-more" href="%s" target="_blank" rel="noopener">%s</a>\n'
            '    </div>' % (
                proj["url"], proj["name"], proj["badge_class"],
                proj["badge"].format(**fmt), proj["meta"].format(**fmt),
                proj["desc"].format(**fmt), items, proj["more"], proj["more_text"].format(**fmt)))
    return stats_html, "\n\n".join(cards)


def render_md(groups, total, star_map):
    mifos = next((g for p, g in groups if p["key"] == "mifos"), [])
    templates = sum(templates_in(p) for p in mifos)
    org_word = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(len(groups), str(len(groups)))

    summary = [
        "| 🏆 | What | Proof |",
        "|:--:|:--|:--|",
        "| 🎓 | **MSOC 2026 Intern** @ Mifos Initiative — building the **UI Product Templates** project for a "
        "fintech platform serving **40+ countries**, now a library of **%d loan product templates** | "
        "[Merged PRs ↓](#%s) |" % (templates, anchor(PROJECTS[0]["md_title"])),
        "| 🔥 | **%d merged PRs** across %s major open-source organizations | "
        "[All my PRs](https://github.com/search?q=author%%3A%s+type%%3Apr+is%%3Amerged&type=pullrequests) |"
        % (total, org_word, USER),
    ]
    for proj, mine in groups:
        if proj["key"] == "mifos":
            continue
        icon = proj.get("md_icon", "🧩")
        blurb = proj.get("md_summary", "**%s** — %d merged PR%s"
                         % (proj["name"], len(mine), "" if len(mine) == 1 else "s"))
        blurb = blurb.format(stars=star_map.get(proj["key"], ""), n=len(mine))
        summary.append("| %s | %s | [Merged PRs ↓](#%s) |" % (icon, blurb, anchor(proj["md_title"])))
    summary.append("| 💼 | **Past: Data Analyst @ Inspacco** — 6 months of production dashboards, now fueling "
                   "my software work | [Details ↓](#-industry-experience) |")

    def row(p):
        label = "#%d" % p["number"]
        if p["repo"] == "openMF/selfservice-plugin":
            label = "selfservice-plugin #%d" % p["number"]
        month = ""
        if p["merged"]:
            y, m, _ = p["merged"].split("-")
            month = "%s %s" % (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                               "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1], y)
        emoji = MD_EMOJI.get(p["number"])
        text = to_md(describe(p))
        if emoji:
            text = "%s %s" % (emoji, text)
        return "| [%s](%s) | %s | %s |" % (label, p["url"], text, month)

    tables = []
    for proj, mine in groups:
        block = ["## %s" % proj["md_title"], ""]
        if proj.get("md_blurb"):
            block += [proj["md_blurb"], ""]
        top = mine[: proj["md_top"]]
        rest = mine[proj["md_top"]:]
        block += ["| PR | What it did | Merged |", "|:--|:--|:--|"]
        block += [row(p) for p in top]
        if rest:
            block += ["", "<details>",
                      "<summary><b>➕ %d more merged %s PR%s…</b></summary>"
                      % (len(rest), proj["name"].split()[0], "" if len(rest) == 1 else "s"),
                      "<br/>", "", "| PR | What it did | Merged |", "|:--|:--|:--|"]
            block += [row(p) for p in rest]
            block += ["", "</details>"]
        tables.append("\n".join(block))
    return "\n".join(summary), "\n\n".join(tables)


# --------------------------------------------------------------------- main --
def main():
    prs = fetch_merged()
    if not prs:
        sys.stderr.write("error: GitHub returned no merged PRs; refusing to rewrite files\n")
        return 1
    groups = group(prs)
    total = len(prs)
    for proj, mine in groups:
        if proj.get("_new"):
            print("note: new project detected -> %s (%d PRs)" % (proj["repos"][0], len(mine)))
    print("%d merged PRs across %d projects" % (total, len(groups)))

    changed = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    html_path = os.path.join(root, "index.html")
    if os.path.exists(html_path):
        star_map = {p["key"]: stars(p["star_repo"]) for p, _ in groups}
        stats_html, cards_html = render_html(groups, total, star_map)
        with open(html_path, encoding="utf-8") as fh:
            before = fh.read()
        after = replace_block(before, "STATS", stats_html)
        after = replace_block(after, "CARDS", cards_html)
        after = re.sub(r"(\d+) merged PRs in production codebases",
                       "%d merged PRs in production codebases" % total, after)
        if after != before:
            with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(after)
            changed.append("index.html")

    md_path = os.path.join(root, "README.md")
    if os.path.exists(md_path):
        star_map = {p["key"]: stars(p["star_repo"]) for p, _ in groups}
        summary_md, tables_md = render_md(groups, total, star_map)
        with open(md_path, encoding="utf-8") as fh:
            before = fh.read()
        after = replace_block(before, "SUMMARY", summary_md)
        after = replace_block(after, "TABLES", tables_md)
        mifos = next((g for p, g in groups if p["key"] == "mifos"), [])
        after = re.sub(r"\d+\+merged\+PRs\+in\+production\+codebases",
                       "%d+merged+PRs+in+production+codebases" % total, after)
        after = re.sub(r"\*\*\d+ merged PRs\*\* and counting",
                       "**%d merged PRs** and counting" % len(mifos), after)
        # keep the hand-written "N loan product templates" bullet honest too
        after = re.sub(r"\*\*\d+ loan product templates\*\*",
                       "**%d loan product templates**" % sum(templates_in(p) for p in mifos), after)
        if after != before:
            with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(after)
            changed.append("README.md")

    print("updated: %s" % (", ".join(changed) if changed else "no changes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
