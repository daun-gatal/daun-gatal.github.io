#!/usr/bin/env python3
"""Fetch GitHub stats and write data/stats.json plus the SVG cards in cards/.

Runs nightly from .github/workflows/refresh.yml. Standard library only.
Needs a token in GH_TOKEN (or GITHUB_TOKEN).
"""
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

USER = "daun-gatal"
CHOUSE = "chouse-ui"
BEZI = "bezisync"
ACCENT = "#f5d90a"
BLUE = "#4493f8"
ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


# ---------------------------------------------------------------- GitHub API

def _req(url, data=None, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "profile-stats-builder"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r), r.headers.get("Link", "")


def rest(path, accept="application/vnd.github+json"):
    return _req(f"https://api.github.com/{path}", accept=accept)[0]


def rest_all(path, accept="application/vnd.github+json"):
    out, url = [], f"https://api.github.com/{path}"
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}per_page=100"
    while url:
        page, link = _req(url, accept=accept)
        out.extend(page)
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1: part.find(">")]
    return out


def graphql(query):
    res, _ = _req("https://api.github.com/graphql", data={"query": query})
    if "errors" in res:
        raise RuntimeError(res["errors"])
    return res["data"]


# ---------------------------------------------------------------- collect

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def star_history(repo_info, today):
    """Monthly cumulative stars.

    Listing stargazers with dates is refused (403) for the Actions GITHUB_TOKEN,
    so when that happens keep the history saved last run and set the current
    month to today's live star count.
    """
    months = []
    cur = dt.date.fromisoformat(repo_info["created"]).replace(day=1)
    while cur <= today:
        months.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    try:
        stars = rest_all(f"repos/{USER}/{CHOUSE}/stargazers",
                         accept="application/vnd.github.star+json")
        starred = sorted(s["starred_at"][:7] for s in stars)
        return [{"month": m, "stars": sum(1 for s in starred if s <= m)} for m in months]
    except urllib.error.HTTPError as err:
        print(f"stargazers unavailable ({err.code}); reusing saved history")
    saved = {}
    path = ROOT / "data" / "stats.json"
    if path.exists():
        saved = {p["month"]: p["stars"]
                 for p in json.loads(path.read_text())["chouse"].get("star_history", [])}
    out, last = [], 0
    for m in months:
        last = saved.get(m, last)
        out.append({"month": m, "stars": last})
    out[-1]["stars"] = repo_info["stars"]
    return out


def collect():
    today = dt.date.today()
    cc = graphql("""{ user(login: "%s") { contributionsCollection {
        totalCommitContributions totalPullRequestContributions
        contributionCalendar { totalContributions weeks { contributionDays {
          date contributionCount contributionLevel } } } } } }""" % USER
                 )["user"]["contributionsCollection"]
    weeks = cc["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]

    streak = best = 0
    for d in days:
        streak = streak + 1 if d["contributionCount"] else 0
        best = max(best, streak)

    months = {}
    for d in days:
        months[d["date"][:7]] = months.get(d["date"][:7], 0) + d["contributionCount"]

    merged = rest(f"search/issues?q=author:{USER}+type:pr+is:merged")["total_count"]

    def repo(name):
        info = rest(f"repos/{USER}/{name}")
        rels = [r for r in rest_all(f"repos/{USER}/{name}/releases") if not r["draft"]]
        rels.sort(key=lambda r: r["published_at"])
        contributors = rest_all(f"repos/{USER}/{name}/contributors")
        return {
            "stars": info["stargazers_count"],
            "forks": info["forks_count"],
            "created": info["created_at"][:10],
            "releases": len(rels),
            "latest": rels[-1]["tag_name"] if rels else None,
            "release_dates": [r["published_at"][:10] for r in rels],
            "release_tags": [r["tag_name"] for r in rels],
            "contributors": len(contributors),
        }

    chouse = repo(CHOUSE)
    chouse["star_history"] = star_history(chouse, today)

    return {
        "updated": today.isoformat(),
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "prs_opened": cc["totalPullRequestContributions"],
        "prs_merged": merged,
        "longest_streak": best,
        "active_days": sum(1 for d in days if d["contributionCount"]),
        "calendar": ["".join(str(LEVELS[d["contributionLevel"]]) for d in w["contributionDays"])
                     for w in weeks],
        "months": [{"month": k, "count": v} for k, v in months.items()],
        "chouse": chouse,
        "bezisync": repo(BEZI),
    }


# ---------------------------------------------------------------- release buckets

def release_buckets(dates, today=None):
    """Per day if the first release is at most 31 days old, else per week (last 16)."""
    today = today or dt.date.today()
    if not dates:
        return "day", []
    parsed = [dt.date.fromisoformat(d) for d in dates]
    start = min(parsed)
    if (today - start).days <= 31:
        n = (today - start).days + 1
        return "day", [{"label": (start + dt.timedelta(i)).strftime("%-d %b"),
                        "count": sum(1 for d in parsed if d == start + dt.timedelta(i))}
                       for i in range(n)]
    monday = today - dt.timedelta(days=today.weekday())
    out = []
    for i in range(15, -1, -1):
        ws = monday - dt.timedelta(weeks=i)
        out.append({"label": ws.strftime("%d %b"),
                    "count": sum(1 for d in parsed if ws <= d < ws + dt.timedelta(7))})
    return "week", out


# ---------------------------------------------------------------- SVG cards

def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">'
            f'<title>{escape(label)}</title>'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" '
            f'fill="#0d1117" stroke="#30363d"/>{body}</svg>\n')


def t(x, y, s, size=13, fill="#e6edf3", weight=400, font=SANS, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(str(s))}</text>')


def fmt(n):
    return f"{n:,}"


def hero_card():
    body = [t(32, 52, "RIZAL MAHIFA · SENIOR DATA ENGINEER", 12, ACCENT, 700, MONO),
            t(32, 96, "Sub-minute Flink pipelines behind", 27, weight=700),
            t(32, 130, "ride-hailing surge pricing.", 27, weight=700),
            t(32, 168, "6+ years in ride-hailing, fintech and e-commerce.", 14, "#b1bac4"),
            t(32, 190, "Creator of CHouse UI and BeziSync.", 14, "#b1bac4"),
            t(32, 232, "daun-gatal.github.io →", 13, "#79b8ff", 600, MONO)]
    x0, bw = 530, 278
    body.append(t(x0, 52, "RESULTS IN MY CURRENT ROLE", 11, "#8b949e", 700, MONO))
    rows = [("Pipeline fleet cost / year", "−30%", 0.70),
            ("Data processed (stream remodel)", "−90%", 0.10),
            ("CPU used (same POC)", "−60%", 0.40)]
    for i, (lab, delta, after) in enumerate(rows):
        y = 88 + i * 54
        body.append(t(x0, y, lab, 13, "#c9d1d9"))
        body.append(t(x0 + bw, y, delta, 18, ACCENT, 700, MONO, "end"))
        body.append(f'<rect x="{x0}" y="{y + 10}" width="{bw}" height="6" rx="3" fill="#30363d"/>')
        body.append(f'<rect x="{x0}" y="{y + 20}" width="{bw * after:.0f}" height="6" rx="3" fill="{ACCENT}"/>')
    return svg(840, 260, "".join(body),
               "Rizal Mahifa, Senior Data Engineer. Fleet cost down 30%, data processed down 90%, CPU down 60%.")


def project_card(name, version, accent, desc, chart, stats, foot):
    body = [t(24, 40, name, 20, weight=700)]
    if version:
        vw = 10 + 7.4 * len(version)
        body.append(f'<rect x="{386 - vw}" y="24" width="{vw}" height="22" rx="11" fill="none" stroke="{accent}"/>')
        body.append(t(386 - vw / 2, 39, version, 11, accent, 600, MONO, "middle"))
    body += [t(24, 66, desc[0], 13, "#b1bac4"), t(24, 84, desc[1], 13, "#b1bac4"), chart]
    sx = 24
    for value, lab in stats:
        body.append(t(sx, 236, value, 17, weight=700, font=MONO))
        body.append(t(sx, 252, lab, 11, "#8b949e"))
        sx += 92
    body.append(t(24, 276, foot, 11, accent, 600, MONO))
    return svg(410, 292, "".join(body), f"{name}: {desc[0]} {desc[1]}")


def chouse_card(c):
    hist = c["star_history"]
    x0, y0, w, h = 24, 104, 362, 92
    top = max(10, max(p["stars"] for p in hist))
    pts = [(x0 + (w * i / max(1, len(hist) - 1)), y0 + h - h * p["stars"] / top)
           for i, p in enumerate(hist)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{x0},{y0 + h} {line} {x0 + w},{y0 + h}"
    chart = (f'<line x1="{x0}" y1="{y0 + h}" x2="{x0 + w}" y2="{y0 + h}" stroke="#30363d"/>'
             f'<polygon points="{area}" fill="{ACCENT}" fill-opacity="0.12"/>'
             f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-linejoin="round"/>'
             f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4" fill="{ACCENT}"/>'
             + t(x0, y0 + h + 14, dt.date.fromisoformat(hist[0]["month"] + "-01").strftime("%b %Y"), 10, "#8b949e", font=MONO)
             + t(x0 + w, y0 + h + 14, "stars over time", 10, "#8b949e", font=MONO, anchor="end"))
    return project_card("CHouse UI", c["latest"], ACCENT,
                        ("Web console for ClickHouse: RBAC, audit logs,",
                         "multi-cluster monitoring, AI root-cause assistant."),
                        chart,
                        [(fmt(c["stars"]), "stars"), (fmt(c["forks"]), "forks"),
                         (fmt(c["releases"]), "releases"), (fmt(c["contributors"]), "contributors")],
                        "✓ Listed in ClickHouse Community Tools")


def bezi_card(b):
    unit, buckets = release_buckets(b["release_dates"])
    x0, y0, w, h = 24, 104, 362, 92
    n = max(1, len(buckets))
    slot = w / n
    top = max(1, max((k["count"] for k in buckets), default=1))
    parts = [f'<line x1="{x0}" y1="{y0 + h}" x2="{x0 + w}" y2="{y0 + h}" stroke="#30363d"/>']
    for i, k in enumerate(buckets):
        bh = max(3, (h - 6) * k["count"] / top) if k["count"] else 3
        fill = BLUE if k["count"] else "#30363d"
        parts.append(f'<rect x="{x0 + i * slot + slot * 0.18:.1f}" y="{y0 + h - bh:.1f}" '
                     f'width="{slot * 0.64:.1f}" height="{bh:.1f}" rx="2" fill="{fill}"/>')
    if buckets:
        parts.append(t(x0, y0 + h + 14, buckets[0]["label"], 10, "#8b949e", font=MONO))
    parts.append(t(x0 + w, y0 + h + 14, f"releases per {unit}", 10, "#8b949e", font=MONO, anchor="end"))
    return project_card("BeziSync", b["latest"], BLUE,
                        ("Self-service CDC on Debezium Server: preflight",
                         "checks, RBAC, SSO, approvals, column masking."),
                        "".join(parts),
                        [("9", "source DBs"), (fmt(b["releases"]), "releases"),
                         ("Go", "+ React"), ("Apache", "2.0")],
                        "Kafka · Iceberg · and more")


def activity_card(s):
    alpha = [0, 0.25, 0.5, 0.75, 1]
    parts = [t(24, 36, "GITHUB ACTIVITY · LAST 12 MONTHS", 11, "#8b949e", 700, MONO)]
    for wi, week in enumerate(s["calendar"]):
        for di, lv in enumerate(week):
            lv = int(lv)
            fill = "#1c2128" if lv == 0 else ACCENT
            op = "" if lv == 0 else f' fill-opacity="{alpha[lv]}"'
            parts.append(f'<rect x="{24 + wi * 13}" y="{52 + di * 13}" width="10" height="10" rx="2" fill="{fill}"{op}/>')
    rx = 730
    for i, (v, lab) in enumerate([(fmt(s["contributions"]), "contributions"),
                                  (fmt(s["prs_merged"]), "PRs merged"),
                                  (f'{s["longest_streak"]}d', "longest streak")]):
        parts.append(t(rx, 64 + i * 38, v, 19, ACCENT if i == 0 else "#e6edf3", 700, MONO))
        parts.append(t(rx, 78 + i * 38, lab, 11, "#8b949e"))
    return svg(840, 160, "".join(parts),
               f'{s["contributions"]} contributions in the last 12 months, {s["prs_merged"]} pull requests merged')


# ---------------------------------------------------------------- main

def main():
    stats = collect()
    stats["bezisync"]["buckets_unit"], stats["bezisync"]["buckets"] = \
        release_buckets(stats["bezisync"]["release_dates"])
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "cards").mkdir(exist_ok=True)
    (ROOT / "data" / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
    cards = {"hero.svg": hero_card(), "chouse-ui.svg": chouse_card(stats["chouse"]),
             "bezisync.svg": bezi_card(stats["bezisync"]), "activity.svg": activity_card(stats)}
    for name, content in cards.items():
        (ROOT / "cards" / name).write_text(content)
    print(json.dumps({k: stats[k] for k in ("updated", "contributions", "prs_merged")}))


if __name__ == "__main__":
    main()
