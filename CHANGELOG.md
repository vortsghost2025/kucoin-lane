# Changelog

All notable changes to kucoin-lane are documented here. Commits are listed newest-first.

## [0.3.0] — 2026-05-18

### Merged

- **Merge headless sync** — Resolved 3 merge conflicts (JOURNAL.md x2, execution_engine.py), restored local docs and monitoring artifacts from `.local-backup/`. 27 files changed, +3331/-259. (`89ca400`)

### Added

- **Monitoring automation** — `scripts/monitoring_automation.py` (410 lines) with snapshot/analyze subcommands, systemd timer installer `scripts/install_monitoring_timers.sh`, 8 service+timer unit pairs in `ops/systemd/`. Hourly/daily/weekly/monthly cadences. Artifacts in `docs/automation/`. (`39bfc85`)
- **HEAD DEPARTMENT VERDICT operator manual** — 8-mission operator decision table, monitoring artifacts, memory bank entries, session journal. (`fbce0e1`)
- **Documentation artifacts** — README.md, OPERATIONS_RUNBOOK.md, CHANGELOG.md (this file), cross-reference notes, blocker status updates.

### Changed

- **Circuit breaker wiring + cycle heartbeat** — Orchestrator now writes SESSION_STATE and heartbeat JSON on each cycle. (`3248ed2`)

### Fixed

- **BUG-007: config.py missing module-level aliases** — API key and trading mode aliases were only on the `Config` class, not at module level where other modules import them. (`e286209`)
- **BUG-006: stale `__init__.py` imports** — `data/__init__.py` and `src/__init__.py` referenced moved/renamed modules. (`561f4a3`)

## [0.2.0] — 2026-05-17

### Added

- **Session 4 Phase D evidence** — Journal updated with Phase D completion, TODO-006 closed, phase tracker and bug table updated. (`1862add`)
- **Session 4-5 monitoring work** — Monitoring automation, systemd timers, test suite updates, execution engine improvements, handoff snapshots. (`39bfc85`)

## [0.1.0] — 2026-05-16

### Added

- **Initial commit** — Merged kucoin-margin-bot + Deliberate-AI-Ensemble trading logic into a governed lane. 4-role ensemble (Intelligence → Orchestrator → Risk → Execution → Monitor → Auditor → Checkpoint). (`63d24e6`)
- **Lane-relay directory structure** — Placeholder directories for inbox/outbox/state with `.gitkeep`. (`014489a`)
- **AWS architecture doc + phenotype sync design** — Cloud deployment architecture and phenotype synchronization design document. (`6347a8a`)

### Changed

- **Removed Lane 4 label** — Lane numbers are governed by the Control Plane registry, not hardcoded. (`f691da1`)
- **Python-kucoin version pin fix** — `>=2.3.0` → `>=2.2.0` (2.3.0 not on PyPI, 2.2.0 is latest available). (`0cd15b9`)

### Added (continued)

- **Work journal** — Full traceability from extraction through Phase C. (`071ef0b`)
- **Journal refinement** — Refined standing authorization scope, entry format, Session 3 start. (`3079169`)
