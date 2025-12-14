# Copilot / Agent Instructions for DGLab-Sleepy

Short, actionable notes to help an AI get productive quickly in this repo.

- **Big picture:** This is a small Flask web service that exposes a status page and a simple JSON API. Server logic and routes live in [server.py](server.py). Persistent state lives in `data.json` and is managed by the `data` class in [data.py](data.py). Frontend templates are in `templates/` and static assets in `static/` and `background/`.

- **How it runs:**
  - Local dev: `python server.py` (or use `start.py` to auto-restart on exit).
  - Docker: built from [Dockerfile](Dockerfile); CMD runs `python server.py`.
  - Requirements: see [requirements.txt](requirements.txt) (Flask, pytz, json5, requests, python-dotenv).

- **Configuration:** Environment variables are read via [env.py](env.py) and `python-dotenv` (loads `.env`). Variables accept UPPERCASE or lowercase (e.g., `SLEEPY_SECRET` or `sleepy_secret`). Boolean parsing uses internal `tobool()` from `_utils.py`.

- **Authentication/conventions:**
  - Many write routes require the shared secret; see `require_secret` decorator in [server.py](server.py).
  - Secret may be provided in JSON body (`{"secret":"..."}`), query param `?secret=...`, header `Sleepy-Secret: ...`, or `Authorization: Bearer ...`.

- **Data & persistence:**
  - `data.template.jsonc` is the source template; `data.json` is created/updated by the `data` class in [data.py](data.py).
  - `data.start_timer_check()` is used to periodically persist changes; calling `/save_data` forces a save.

- **Metrics & telemetry:**
  - Optional (`env.util.metrics`) and gated by `setting/metrics_list.default.jsonc`.
  - Server records metrics via `d.record_metrics(path)` in `before_request` and exposes `/metrics` if enabled.

- **Client integration:**
  - Clients (in `/client`) push device info to `/device/set` (GET or POST) and use the project secret.
  - SSE live updates available on `/events` (server sends `update`/`heartbeat` events).
  - App usage events are recorded on each `/device/set` call. The server exposes `/device/history?id=<id>&hours=<n>` returning per-hour aggregates, per-app total seconds, most-used app, and current app runtime (useful for 24h charts and summaries).
  - Add `sleepy_status_track_device_id` in `.env` to auto-select a device on page load and show its 24-hour app history.
  - Clients may include `app_name_only` and `app_pkg` in the `/device/set` payload to improve parsing accuracy (Magisk and Win_Simple now include these fields).

- **Third-party integrations:**
  - DG-Lab: [dglab_api.py](dglab_api.py) loads `DGLab.json` at startup and provides `/dglab/lightning` and `/dglab/config` endpoints.
  - Steam iframe is toggled with `env.util.steam_enabled` and rendered in `/steam-iframe`.

- **Key patterns & pitfalls agents should follow:**
  - Use [env.py](env.py) to read/tune behaviour (page, status, util namespaces). Avoid hardcoding config values.
  - Use `utils.format_dict()` and `utils.reterr()` to build JSON responses that follow project style.
  - When modifying routes that change state, update `data` via `d.dset()`/`d.check_device_status()` and ensure `last_updated` is set.
  - Follow existing logging functions `utils.info/debug/warning/error` for consistent output.

- **Developer workflow notes:**
  - Changing config: edit `.env` or set env vars; no separate config server.
  - To test client integrations, use `/set`, `/device/set` and check `/query` or SSE `/events`.
  - Server restart: `start.py` can be used for quick restart loops during development.

- **Files to inspect first (quick tour):**
  - [server.py](server.py) — routing & auth
  - [data.py](data.py) — in-memory state and persistence
  - [env.py](env.py) — feature flags & env var sources
  - [client/README.md](client/README.md) — example clients & usage
  - [templates/](templates/) and [static/](static/) — front-end

If anything here is unclear or you want me to expand specific sections (e.g. example configs, quick run commands, typical PR checklist for this repo), tell me which part and I will iterate.
