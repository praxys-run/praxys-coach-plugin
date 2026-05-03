# Praxys Coach — Claude Code Plugin

Claude Code plugin that surfaces [Praxys Coach](https://www.praxys.run) — a power-based scientific training dashboard for endurance athletes — through MCP tools and skills, so you can ask your training questions directly from your terminal.

> Praxys Coach itself syncs your data from Garmin, Stryd, and Oura, computes power-based training metrics, and serves them via a web dashboard at praxys.run. This plugin is a thin Claude Code client that lets an agent read and act on that data on your behalf.

## Skills

The plugin exposes 8 skills (auto-discovered when installed):

| Skill | What it does |
|-------|-------------|
| `setup` | Connect Garmin / Stryd / Oura, set training base, thresholds, race goal |
| `daily-brief` | Today's training signal (Go / Modify / Rest), recovery, upcoming workouts |
| `training-review` | Multi-week diagnosis: volume, consistency, zone distribution, suggestions |
| `training-plan` | Generate or update a personalized 4-week AI training plan |
| `race-forecast` | Predicted finish time, goal feasibility, required threshold improvement |
| `sync-data` | Trigger or check sync status across connected platforms |
| `science` | Browse and switch training science theories (load, recovery, prediction, zones) |
| `add-metric` | (Developer skill) Scaffold a new training metric end-to-end |

Backed by an MCP server with tools like `get_daily_brief`, `get_race_forecast`, `get_training_review`, `trigger_sync`, `update_settings`, etc.

## Install

You need an account at [praxys.run](https://www.praxys.run) (free, invitation-based) before the plugin is useful — the plugin is the agent client, not the data source.

In Claude Code:

```
/plugin marketplace add github:dddtc2005/praxys-coach-plugin
/plugin install praxys
```

Then authenticate with the `login` MCP tool using your praxys.run email and password. Your token is cached locally at `~/.praxys/token`.

## Configuration

The plugin defaults to the production backend at `https://api.praxys.run`. Override via environment variables:

| Variable | Purpose |
|----------|---------|
| `PRAXYS_URL` | Override backend API URL |
| `PRAXYS_FRONTEND_URL` | Override the browser-login URL |
| `PRAXYS_LOCAL=1` | Switch into local-development mode (see below) |

## Local development

Local mode (`PRAXYS_LOCAL=1`) imports directly from the Praxys Python codebase instead of going over HTTP. This is only useful if you have the (private) main `praxys` repo checked out — the plugin expects to live three directories deep inside that repo (`<praxys>/plugins/praxys/...`). The main repo wires it in as a git submodule at that path.

If you only want to use the plugin against praxys.run, ignore this section — remote mode is the default and needs no setup beyond `login`.

## License

MIT — see [LICENSE](LICENSE).
