# Praxys Coach — Agent Plugin

Plugin for Codex and Claude Code that surfaces [Praxys Coach](https://www.praxys.run) — a power-based scientific training dashboard for endurance athletes — through MCP tools and skills, so you can ask your training questions directly from your terminal.

> Praxys Coach brings supported training and recovery data together, computes power-based training metrics, and serves them via a web dashboard at praxys.run. This plugin is a thin agent client that lets an agent read and act on that data on your behalf.

## Skills

The plugin exposes 8 skills (auto-discovered when installed):

| Skill | What it does |
|-------|-------------|
| `setup` | Connect account-available data sources, set training base, thresholds, race goal |
| `daily-brief` | Today's training signal (Go / Modify / Rest), recovery, upcoming workouts |
| `training-review` | Multi-week diagnosis: volume, consistency, zone distribution, suggestions |
| `training-plan` | Generate or update a personalized 4-week AI training plan |
| `race-forecast` | Predicted finish time, goal feasibility, required threshold improvement |
| `sync-data` | Trigger or check sync status across connected platforms |
| `science` | Browse and switch training science theories (load, recovery, prediction, zones) |
| `add-metric` | (Developer skill) Scaffold a new training metric end-to-end |

Backed by an MCP server with tools like `get_daily_brief`, `get_race_forecast`, `get_training_review`, `trigger_sync`, and `update_settings`.

### Plan authoring vs. managed delivery

The plugin keeps these operations explicit:

- `save_training_plan` authors canonical future workouts in Praxys. It does not
  directly select or mutate an execution platform.
- `push_training_plan` remains as a backward-compatible alias, but new callers
  should use `save_training_plan`.
- `get_managed_plan_status` reports ownership, delivery state, the 14-day plan,
  and opaque conflict IDs.
- `adopt_managed_plan`, `pause_managed_plan`, `resume_managed_plan`, and
  `leave_managed_plan` control the user's managed-delivery consent.
- `resolve_managed_plan_conflict` accepts only the server-provided
  `accept_target` and `restore_praxys` actions.

When managed delivery is already enabled, Praxys may independently deliver a
newly saved canonical plan under that existing consent. Manual workouts and
workouts from another coach remain untouched.

Adoption and resume require the exact `window.start` and `window.end` from a
fresh `get_managed_plan_status(days=14)` result, preventing approval from being
reused after the UTC review window changes.

## Install

You need an account at [praxys.run](https://www.praxys.run) (free, invitation-based) before the plugin is useful — the plugin is the agent client, not the data source.

### Python prerequisites

The MCP server runs locally with Python 3.10 or later. Install the dependencies
in the Python environment used to launch your agent (macOS/Linux shell example):

```sh
git clone https://github.com/praxys-run/praxys-coach-plugin.git praxys
cd praxys
python3 -m venv ../praxys-venv
source ../praxys-venv/bin/activate
python -m pip install -r mcp-server/requirements.txt
```

On Windows, activate the environment with `..\praxys-venv\Scripts\Activate.ps1` in
PowerShell. The plugin launches `python`, so keep this environment active when
starting Codex or Claude Code. Plugin installation does not install Python
packages for you.

### Codex CLI

With a current Codex CLI that supports `codex plugin` (commands checked with
0.153.4), register this checkout as a local marketplace and install the plugin:

```sh
codex plugin marketplace add .
codex plugin list --marketplace praxys-coach --available --json
codex plugin add praxys@praxys-coach
codex plugin list
codex
```

Run these commands from the checkout root after activating the Python
environment above. The existing marketplace exposes `praxys`; Codex loads
`.codex-plugin/plugin.json`, the same eight skills, and one `praxys` MCP server.
The Codex manifest resolves the server working directory relative to the
installed plugin, so launching Codex from another project also works. Start a
new Codex session after installation to load the tools and skills.

To track the Git marketplace instead of a local checkout, use
`codex plugin marketplace add https://github.com/praxys-run/praxys-coach-plugin.git`
for the marketplace-add step. The Python prerequisites still apply.

### Claude Code

In Claude Code:

```
/plugin marketplace add github:dddtc2005/praxys-coach-plugin
/plugin install praxys
```

### Authenticate (both hosts)

Then authenticate with the `login` MCP tool. It opens praxys.run in your
browser with opaque, expiring handoff state. After first-party approval, the
plugin exchanges a client-held verifier for a revocable MCP session and caches
it at `~/.praxys/token`; the Praxys account JWT never enters the URL or plugin
process. Use `whoami` to verify the account and `logout` to remove only that
active authentication scope.

### Purpose-bound plan context

Personal plan context is deny-by-default even after MCP login:

1. Call `request_personal_context_access` with one purpose, context kind, and
   `read`, `write`, or both.
2. Open the returned Praxys link and approve the exact short-lived request.
3. Call `complete_personal_context_access`.
4. Use `read_personal_context` for the minimum structured projection or
   `preview_personal_context` to validate one single-use structured draft.
5. Call `revoke_personal_context_access` when finished.

Read grants never return narrative, context IDs, provenance internals, consent
receipts, or encrypted data. Write grants create only a request-scoped preview:
the athlete must re-enter or confirm context in the first-party web or miniapp
plan-context surface before anything durable exists. The plugin cannot approve
its own access, grant AI processing, delete context, or persist conversation
text. Local direct-DB mode resolves the same server-authoritative grant tables
and does not bypass purpose, expiry, revocation, ownership, or single-use
checks.

### Troubleshooting

- **Plugin or skills missing:** check `codex plugin list` and confirm `praxys`
  is installed and enabled. Reopen Codex in a new session. If the marketplace
  is missing, run the marketplace-add command from the checkout root.
- **MCP server fails to start:** in the shell used to launch the agent, run
  `python -c "import mcp, requests"`. Activate the environment and reinstall
  `mcp-server/requirements.txt` if imports fail. Keep `mcp-server/server.py`
  and the manifests together in the plugin package; do not copy only the
  Codex manifest into another directory.
- **Login expired or not approved:** call `login` again and approve the fresh
  browser handoff, then call `whoami`.
- **Wrong account:** check `whoami` and `PRAXYS_PROFILE` in the shell used to
  launch the agent. Select the intended profile, restart the agent, and log in
  for that profile. See multiple authentication profiles below.
- **Backend unavailable:** check `PRAXYS_URL` and retry when the backend is
  reachable. Login and training tools require the backend in default remote
  mode; installing the plugin does not provide an offline data source.

## Configuration

The plugin defaults to the production backend at `https://api.praxys.run`. Override via environment variables:

| Variable | Purpose |
|----------|---------|
| `PRAXYS_URL` | Override backend API URL |
| `PRAXYS_FRONTEND_URL` | Override the browser-login URL |
| `PRAXYS_LOCAL=1` | Switch into local-development mode (see below) |
| `PRAXYS_PROFILE` | Use an isolated named authentication profile |
| `PRAXYS_TOKEN_PATH` | Explicit token-file override for automation or testing |

### Multiple authentication profiles

The default profile remains backward compatible: it writes
`~/.praxys/token` and reads the legacy `~/.trainsight/token` only when the
modern token is absent.

Set `PRAXYS_PROFILE` when a second MCP server must authenticate as a different
Praxys user. For example, `PRAXYS_PROFILE=dev-test` stores its token and config
under `~/.praxys/profiles/dev-test/` and never falls back to the default or
legacy token. Profile names may contain letters, numbers, underscores, and
hyphens. `PRAXYS_TOKEN_PATH` provides a fully isolated explicit path and also
disables legacy fallback.

```json
{
  "mcpServers": {
    "praxys": {
      "command": "python",
      "args": ["/path/to/praxys-coach-plugin/mcp-server/server.py"]
    },
    "praxys-dev-test": {
      "command": "python",
      "args": ["/path/to/praxys-coach-plugin/mcp-server/server.py"],
      "env": {
        "PRAXYS_PROFILE": "dev-test",
        "PRAXYS_URL": "https://api.praxys.run",
        "PRAXYS_FRONTEND_URL": "https://www.praxys.run"
      }
    }
  }
}
```

Run each server's `login` once, then confirm that `whoami` reports the expected
profile, user ID, and email. `logout` deletes only the selected profile's token
and config.

## Local development

Local mode (`PRAXYS_LOCAL=1`) imports directly from the Praxys Python codebase instead of going over HTTP. This is only useful if you have the (private) main `praxys` repo checked out — the plugin expects to live three directories deep inside that repo (`<praxys>/plugins/praxys/...`). The main repo wires it in as a git submodule at that path.

If you only want to use the plugin against praxys.run, ignore this section — remote mode is the default and needs only the Python prerequisites, plugin installation, and `login` above.

Most local tools read or write the development database directly and do not
need login. `trigger_sync` is the exception because it uses the authenticated
local API for background sync behavior; it reads only the active profile's
token and fails clearly when that scope has none.

## License

MIT — see [LICENSE](LICENSE).
