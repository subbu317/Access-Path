# Screenshot guide — capture the actual running application

Before capturing: start both servers, reset the demo if you want the original obstacles, use a browser window at 1440×900 (desktop), and dismiss error/notice banners. Take genuine browser screenshots with Windows `Win + Shift + S` or the browser's screenshot command. Store them as files in `docs/screenshots/` if you plan to publish them; the folder is intentionally empty in the source ZIP because screenshots should reflect your own functioning installation.

1. **`01-route-planner.png`** — Route planner, Welcome Gate → Community Hub, Wheelchair profile, 70% aversion; include the map, three route cards, the explanation and amber uncertainty line.
2. **`02-segment-evidence.png`** — Open “Inspect segment evidence” on the preferred route; show per-edge verification warnings.
3. **`03-report-flow.png`** — Community reports section; click a map segment to prefill the form and display the report feed.
4. **`04-moderation.png`** — Moderation dashboard unlocked locally; show the verified report action and the audit entries. Avoid showing a custom secret in screenshots.
5. **`05-evaluation.png`** — Run the benchmark, showing computed K-shortest routing comparisons, uncertainty metrics, Brier/ECE calibration and sample sizes.
6. **`06-mobile.png`** — Chrome/Edge device toolbar around 390×844; demonstrate usable mobile profile controls, map and bottom navigation.

After capturing screenshots, embed selected files near the top of the root README:

```markdown
![AccessPath planner](docs/screenshots/01-route-planner.png)
![Synthetic evaluation dashboard](docs/screenshots/05-evaluation.png)
```

Caption every screenshot **“Synthetic example network; not certified navigation.”** Do not photoshop numerical benchmark claims. If referencing computed metrics in resume or documentation, include the number of evaluated cases and note that calibration outcomes were simulated.
