# Laneige Ranking Agent (MVP: Ranking Only)

## What it does
- Collects ranking snapshots (TopN) from Amazon US Best Sellers and @cosme JP ranking pages.
- Stores append-only history to Excel (rank_history_min, run_log).
- Generates ranking-only insights (streak, rank shock, new entry/exit).

## Compliance
- Always respects robots.txt and site policies.
- No bypass/evasion (no proxy rotation, no CAPTCHA bypass, no stealth tricks).
- Stops/backoffs on 429/403/503/CAPTCHA-like responses and logs the run.

## Quick start
1) Fill `config.yaml` and `selectors.yaml` (verify selectors via browser DevTools).
2) Run:
   - TODO: python entrypoint

## Output
- `data/rank_history.xlsx`
  - sheet: rank_history_min
  - sheet: run_log
