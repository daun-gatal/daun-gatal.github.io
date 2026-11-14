# daun-gatal.github.io

Source for [daun-gatal.github.io](https://daun-gatal.github.io), a one-page portfolio, and the SVG cards shown on the [GitHub profile](https://github.com/daun-gatal).

| Path | What it is |
|---|---|
| `index.html`, `assets/` | The landing page. Static HTML; `assets/app.js` draws the charts from `data/stats.json`. |
| `scripts/build_stats.py` | Pulls numbers from the GitHub API and writes `data/stats.json` and `cards/*.svg`. Standard library only. |
| `.github/workflows/refresh.yml` | Runs the script every night and commits any changes. |

Run it locally:

```bash
GH_TOKEN=$(gh auth token) python3 scripts/build_stats.py
python3 -m http.server 8000   # then open http://localhost:8000
```

Optional: add a `STATS_TOKEN` repo secret (a personal token with `read:user`). Without it, the workflow uses `GITHUB_TOKEN` and the contribution count may leave out private contributions.
