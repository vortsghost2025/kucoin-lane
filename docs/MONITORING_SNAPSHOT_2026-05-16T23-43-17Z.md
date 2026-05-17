OUTPUT_PROVENANCE:
  agent: codex/gpt-5.2
  lane: kucoin
  generated_at: 2026-05-16T23:43:17Z
  session_id: codex-current
  purpose: fresh-monitoring-snapshot

# Monitoring Snapshot — 2026-05-16T23:43:17Z

## KuCoin Lane (Headless Runtime State)
- Host: `we4free@100.95.40.99`
- Repo: `/home/we4free/agent/repos/kucoin-lane`
- Git: `HEAD=1862add`, `branch=main`
- Runtime artifacts present:
  - `lanes/kucoin/inbox/SESSION_STATE.json`
  - `bot_heartbeat_dry_run.json`
- `SESSION_STATE.json` (parsed):
  - `timestamp`: `2026-05-16T20:34:02.553291`
  - `status`: `shutdown`
  - `phase`: `terminating`
  - `final`: `true`
  - `cycle`: `1`
- `bot_heartbeat_dry_run.json` (parsed):
  - `timestamp`: `2026-05-16T20:34:02.552700`
  - `status`: `shutdown`
  - `cycle`: `1`

## Headless Service Topology
- KuCoin-specific systemd lane units (`we4free-*@kucoin`): **none found**
- Governance lane units active count (`archivist|kernel|library|swarmmind`): **16**
  - 4 lanes × (`heartbeat`, `lane-worker`, `relay-daemon`, `autonomous-executor`)

## Control Plane Monitoring Feed
- Source: `S:/WE4FREE-Control-Plane/headless-observations/latest-summary.json`
- `generated_at_iso`: `2026-05-16T23:40:05+00:00`
- `all_healthy`: `true`
- `lane_count`: `4`
- lane statuses:
  - `archivist: healthy`
  - `kernel: healthy`
  - `library: healthy`
  - `swarmmind: healthy`

## Lattice Deck Ingest Readiness (Code Wiring)
- Headless sync reads KuCoin artifacts via SSH paths in:
  - `S:/WE4FREE-Lattice-Deck/src/lib/services/headless-sync.ts`
  - `KUCOIN_SESSION_PATH` and `KUCOIN_HEARTBEAT_PATH`
- KuCoin mapping into dashboard contract occurs in:
  - `S:/WE4FREE-Lattice-Deck/src/lib/services/dataAdapter.ts`
  - `mapKucoinToContract(...)`
  - `syncHeadlessData()` consumed by status/timeline/continuity adapters

## Interpretation
- Monitoring mesh is live and healthy for the 4 governance lanes.
- KuCoin lane is present with valid dry-run terminal artifacts, but not running as a live systemd lane service.
- Lattice and Control Plane are wired to observe KuCoin state artifacts when present.
