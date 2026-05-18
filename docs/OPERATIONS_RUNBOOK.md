# KuCoin Lane — Operations Runbook

OUTPUT_PROVENANCE:
agent: library-kilo
lane: library
target: kucoin-lane-operations-docs
generated_at: 2026-05-18T15:15:00Z
session_id: kilo-doc-write

---

## Overview

This runbook covers day-to-day operations for the KuCoin Lane: starting, stopping, monitoring, and troubleshooting. For architecture and governance context, see [AGENTS.md](../AGENTS.md) and [governance/](../governance/).

---

## 1. Starting the Bot

### Dry-Run Mode (Default, No API Keys Required)

```bash
cd ~/agent/repos/kucoin-lane
EXECUTION_MODE=dry_run python -m src.deterministic_startup
```

The `DeterministicStartup` module runs three stages:
1. **CLEANUP** — Removes stale heartbeat files, temp state, leftover locks
2. **INIT** — Initializes config, data providers, exchange adapter
3. **VERIFY** — Confirms critical subsystems respond before entering the trading loop

If VERIFY fails, the bot exits with a non-zero code and logs which verification step failed.

### Live Mode (Requires API Keys)

```bash
# Ensure .env is configured (see config/.env.example)
cp config/.env.example .env
# Edit .env with real KuCoin API credentials

EXECUTION_MODE=live python -m src.deterministic_startup
```

**Prerequisite:** All HIGH-severity go-live blockers must be resolved first. See [memory/blocker-matrix.md](../memory/blocker-matrix.md).

### Systemd Service (Not Yet Available — Blocker B1)

There is no systemd service for the trading bot itself. Only monitoring timers are installed. See Blocker B1 in the blocker matrix.

---

## 2. Stopping the Bot

### Graceful Shutdown (SIGTERM / Ctrl+C)

The orchestrator catches SIGTERM and SIGINT. On receipt:

1. Sets `session_state.phase = "terminating"`
2. Writes current session state to `lanes/kucoin/inbox/SESSION_STATE.json`
3. Logs the shutdown event
4. Exits cleanly

```bash
# If running in foreground:
Ctrl+C

# If running in background:
kill -SIGTERM <PID>
```

### Forced Shutdown (SIGKILL)

Avoid if possible. SIGKILL cannot be caught, so the session state write in step 2 above will NOT happen. The next startup's CLEANUP stage handles leftover state, but the final cycle's state is lost.

```bash
kill -9 <PID>  # Last resort only
```

---

## 3. Monitoring

### Monitoring Timers (Systemd)

Four systemd timers run on the headless machine (`we4free@100.95.40.99`):

| Timer | Cadence | What It Does |
|-------|---------|-------------|
| `kucoin-monitoring-hourly.timer` | Hourly | Captures snapshot → `docs/automation/MONITORING_SNAPSHOT_*.md` + appends to `lanes/kucoin/state/monitoring/hourly_snapshots.jsonl` |
| `kucoin-monitoring-daily-analysis.timer` | Daily | Generates daily analysis → `docs/automation/MONITORING_ANALYSIS_daily_*.md` |
| `kucoin-monitoring-weekly-analysis.timer` | Weekly | Generates weekly analysis → `docs/automation/MONITORING_ANALYSIS_weekly_*.md` |
| `kucoin-monitoring-monthly-analysis.timer` | Monthly | Generates monthly analysis → `docs/automation/MONITORING_ANALYSIS_monthly_*.md` |

**Check timer status:**
```bash
# User-level timers:
systemctl --user list-timers --all | grep kucoin

# System-level timers:
systemctl list-timers --all | grep kucoin
```

**Install/reinstall timers:**
```bash
cd ~/agent/repos/kucoin-lane
bash scripts/install_monitoring_timers.sh           # user mode (default)
bash scripts/install_monitoring_timers.sh --system   # system mode
```

### Key Files to Check

| File | What It Tells You |
|------|-------------------|
| `bot_heartbeat_dry_run.json` (or `_live.json`) | Current bot status, cycle count, mode |
| `lanes/kucoin/inbox/SESSION_STATE.json` | Session phase, cycle number, final status |
| `docs/automation/latest-monitoring-snapshot.md` | Symlink to most recent hourly snapshot |
| `docs/automation/latest-monitoring-analysis-daily.md` | Symlink to most recent daily analysis |
| `lanes/kucoin/state/monitoring/hourly_snapshots.jsonl` | Full JSONL history of hourly snapshots |

### Manual Monitoring Commands

```bash
# Run a one-off snapshot:
python3 scripts/monitoring_automation.py snapshot

# Run daily analysis:
python3 scripts/monitoring_automation.py analyze --period daily

# Run weekly analysis:
python3 scripts/monitoring_automation.py analyze --period weekly

# Run monthly analysis:
python3 scripts/monitoring_automation.py analyze --period monthly
```

---

## 4. Health Checks

### Quick Health (3 commands)

```bash
# 1. Bot status from heartbeat:
cat bot_heartbeat_dry_run.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'status={d.get(\"status\",\"?\")} cycle={d.get(\"current_cycle\",\"?\")} mode={d.get(\"execution_mode\",\"?\")}')"

# 2. Session state:
cat lanes/kucoin/inbox/SESSION_STATE.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'phase={d.get(\"phase\",\"?\")} final={d.get(\"is_final\",\"?\")} cycle={d.get(\"current_cycle\",\"?\")}')"

# 3. Test suite:
pytest tests/ -q --tb=no 2>&1 | tail -5
```

### Expected Healthy State

| Signal | Healthy Value |
|--------|--------------|
| `heartbeat.status` | `running` (or `shutdown` if intentionally stopped) |
| `SESSION_STATE.phase` | `trading` (or `terminating` during shutdown) |
| `SESSION_STATE.is_final` | `false` (true = bot has stopped) |
| Test suite | 302 passing |
| Monitoring timers | All 4 active (hourly, daily, weekly, monthly) |

### Unhealthy Patterns

| Symptom | Meaning | Action |
|---------|---------|--------|
| `status: shutdown` + `is_final: true` | Bot stopped (intentional or crash) | Check logs; restart if expected to be running |
| `status: error` | Unhandled exception | Check stderr/stdout; investigate traceback |
| No heartbeat file | Bot never started or CLEANUP removed it | Check if bot process exists: `ps aux \| grep deterministic_startup` |
| Monitoring timers inactive | Timer installation failed or systemd not running | Reinstall: `bash scripts/install_monitoring_timers.sh` |
| Growing snapshot count in `docs/automation/` | Normal; see retention policy below | Run retention cleanup (section 6) |

---

## 5. Troubleshooting

### Bot Won't Start

1. Check `.env` exists (required even for dry-run): `ls -la .env`
2. Check Python dependencies: `pip install -r requirements.txt`
3. Run startup manually to see error: `EXECUTION_MODE=dry_run python -m src.deterministic_startup`
4. Check for stale locks in CLEANUP stage output

### Import Errors (BUG-006 Pattern)

If you see `ModuleNotFoundError` for `src.data` or `src`:
- Check `src/__init__.py` and `src/data/__init__.py` have correct imports
- Fixed in commit `561f4a3` — ensure you're past that commit

### API Key Errors (BUG-007 Pattern)

If config loads but API key attributes are `None`:
- Check `src/config.py` has module-level aliases for `KUCOIN_API_KEY` and `TRADING_MODE`
- Fixed in commit `e286209` — ensure you're past that commit

### Test Failures

```bash
pytest tests/ -q --tb=short
```

If failures relate to `CircuitBreaker` or `PortfolioCircuitBreaker`:
- These are known dead-code classes (see [memory/wire-map.md](../memory/wire-map.md))
- Test failures in these modules don't affect runtime
- Do NOT attempt to wire them in without addressing Blocker B2

---

## 6. Retention Policy for `docs/automation/`

### Problem

Monitoring automation generates timestamped snapshot and analysis files that grow unbounded:
- Hourly snapshots: ~24/day × ~30 lines each
- Daily/weekly/monthly analyses: smaller but accumulate

### Policy

| Artifact Type | Retain | Archive | Delete |
|--------------|--------|---------|--------|
| Hourly snapshots (`MONITORING_SNAPSHOT_*.md`) | Latest 48 | Older than 48 → gzip into `docs/automation/archive/` | Older than 90 days |
| Daily analyses (`MONITORING_ANALYSIS_daily_*.md`) | Latest 30 | Older than 30 → gzip into `docs/automation/archive/` | Older than 365 days |
| Weekly analyses (`MONITORING_ANALYSIS_weekly_*.md`) | All | Never | Never |
| Monthly analyses (`MONITORING_ANALYSIS_monthly_*.md`) | All | Never | Never |
| JSONL history (`hourly_snapshots.jsonl`) | All | Never | Never (append-only) |
| `latest-*` symlinks | Always current | N/A | N/A |

### Cleanup Script

```bash
# Run manually or via cron:
cd ~/agent/repos/kucoin-lane

# Archive old hourly snapshots (>48h):
find docs/automation/ -name 'MONITORING_SNAPSHOT_*.md' -mtime +2 ! -name 'latest-*' -exec gzip {} \;
mkdir -p docs/automation/archive
find docs/automation/ -name 'MONITORING_SNAPSHOT_*.md.gz' -exec mv {} docs/automation/archive/ \;

# Delete archived snapshots older than 90 days:
find docs/automation/archive/ -name 'MONITORING_SNAPSHOT_*.md.gz' -mtime +90 -delete

# Archive old daily analyses (>30 days):
find docs/automation/ -name 'MONITORING_ANALYSIS_daily_*.md' -mtime +30 -exec gzip {} \;
find docs/automation/ -name 'MONITORING_ANALYSIS_daily_*.md.gz' -exec mv {} docs/automation/archive/ \;

# Delete archived daily analyses older than 365 days:
find docs/automation/archive/ -name 'MONITORING_ANALYSIS_daily_*.md.gz' -mtime +365 -delete
```

**Recommendation:** Add a `retention` subcommand to `scripts/monitoring_automation.py` and wire it into a weekly systemd timer.

---

## 7. Git Operations

### Syncing Headless ↔ Local

```bash
# On headless (after local push):
cd ~/agent/repos/kucoin-lane && git pull

# On local (after headless push):
cd S:\kucoin-lane && git pull
```

Both copies should always be at the same commit. The remote is `https://github.com/vortsghost2025/kucoin-lane.git` (branch `main`).

### Commit Conventions

Follow the project's commit prefix style:
- `feat(scope):` — new feature
- `fix(scope):` — bug fix
- `docs:` — documentation changes
- `chore:` — maintenance, deps, cleanup

---

## 8. Emergency Procedures

### Bot Is Trading Unintended (Live Mode Only)

1. **Immediate:** Send SIGTERM to the bot process: `kill -SIGTERM <PID>`
2. **Verify:** Check `bot_heartbeat_live.json` shows `status: shutdown`
3. **Manual override:** If KuCoin API is accessible, cancel open orders via KuCoin web interface
4. **Post-mortem:** Check `lanes/kucoin/inbox/SESSION_STATE.json` for the last cycle state

### Monitoring Timers Failed

1. Check systemd journal: `journalctl --user -u kucoin-monitoring-hourly -n 50`
2. Reinstall timers: `bash scripts/install_monitoring_timers.sh`
3. Run manual snapshot: `python3 scripts/monitoring_automation.py snapshot`

### Disk Full from Snapshots

1. Run retention cleanup (section 6)
2. If urgent: `rm docs/automation/MONITORING_SNAPSHOT_2026-05-1*.md` (adjust date pattern)
3. The JSONL history is more compact — keep it

---

## 9. Go-Live Checklist

Before switching from `dry_run` to `live` mode, verify ALL of:

- [ ] `.env` configured with valid KuCoin API credentials
- [ ] Blocker B1 resolved: systemd service for the trading bot
- [ ] Blocker B2 resolved: CircuitBreaker classes wired into runtime
- [ ] Blocker B3 resolved: Auditor failures trigger circuit breaker (not just log)
- [ ] Blocker B4 resolved: API keys tested with a small read-only call
- [ ] Blocker B7 resolved: `circuit_breaker_active` persisted across restarts
- [ ] Test suite passes: `pytest tests/ -q`
- [ ] Monitoring timers active on headless
- [ ] Telegram alerts configured (optional but recommended)

See [memory/blocker-matrix.md](../memory/blocker-matrix.md) for full blocker details.
