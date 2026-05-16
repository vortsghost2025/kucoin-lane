# Compact Restore Phenotype Sync Design

> OUTPUT_PROVENANCE:
> agent: kilo
> lane: kucoin
> target: phenotype-sync-design
> generated_at: 2026-05-16T06:15:00Z
> session_id: ws3d

## OBSERVABILITY_DOMAIN
state-recovery

## NEXT_SAFE_ACTION
Implement compact phenotype snapshots in checkpoint_manager.py

---

## 1. Problem

When the kucoin-lane bot restarts after a crash or update, it must restore its operational state ("phenotype") — open positions, risk parameters, circuit-breaker state, and coordination state. The current checkpoint_manager.py saves signal-level checkpoints, but a full phenotype snapshot is needed for rapid restore.

## 2. Phenotype Definition

The phenotype is the minimal state needed to resume operations without re-syncing from exchange API:

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-05-16T06:00:00Z",
  "coordination_state": "IDLE",
  "execution_mode": "dry_run",
  "positions": {
    "BTC-USDT": {
      "side": "long",
      "entry_price": 104500.0,
      "quantity": 0.001,
      "stop_loss": 103500.0,
      "take_profit": 106500.0,
      "opened_at": "2026-05-16T05:30:00Z"
    }
  },
  "risk_state": {
    "daily_pnl": -12.50,
    "daily_loss_cap": 100.0,
    "circuit_breaker_active": false,
    "portfolio_circuit_breaker_active": false,
    "consecutive_losses": 0,
    "trades_today": 3
  },
  "regime_state": {
    "current_regime": "RANGING",
    "last_detection_at": "2026-05-16T05:55:00Z"
  },
  "heartbeat_seq": 847
}
```

## 3. Compact Encoding

To minimize disk I/O and sync latency:

1. **Delta compression**: Only store fields that changed since last snapshot
2. **Binary pickle for full snapshots**: `checkpoint_manager.py` already uses pickle for signal checkpoints
3. **JSON for delta snapshots**: Human-readable, diffable, lane-relay compatible
4. **Rolling window**: Keep last 24 full snapshots + unlimited deltas (compacted on housekeeping)

### Snapshot Types

| Type | Format | Trigger | Size Estimate |
|------|--------|---------|---------------|
| Full | pickle | Startup, HALT, hourly | ~5KB |
| Delta | JSON | Every trade, state transition | ~500B |
| Compact | JSON (minified) | Heartbeat | ~200B |

## 4. Sync Protocol

### Local Sync (Same Machine)

```
checkpoint_manager.py
  → write full snapshot: data/phenotypes/phenotype_{timestamp}.pkl
  → write delta: data/phenotypes/delta_{seq}.json
  → update latest pointer: data/phenotypes/latest.json → {"full": "phenotype_20260516T06.pkl", "seq": 847}
```

### Cross-Lane Sync (via Lane-Relay)

Phenotype summary can be broadcast to Archivist for system-wide state awareness:

```
kucoin-lane/outbox/
  → phenotype-summary.json (compact, no positions detail)
  → {"schema_version":"1.0","coordination":"IDLE","mode":"dry_run",
     "positions_count":1,"daily_pnl":-12.50,"cb_active":false}
```

### Cross-Rig Sync (Windows ↔ Ubuntu)

Git-based: phenotype files in `data/phenotypes/` are gitignored (local state only). Cross-rig sync uses lane-relay filesystem mount (SSHFS/CIFS), not git.

For disaster recovery:
1. Full snapshots are also written to `data/checkpoints/` (already git-tracked if <1MB)
2. On new rig, clone repo → restore latest full snapshot → replay deltas from exchange API

## 5. Restore Procedure

### Fast Path (Full snapshot available)

```python
def restore_phenotype(checkpoint_dir: Path) -> dict:
    latest = json.loads((checkpoint_dir / "latest.json").read_text())
    full_path = checkpoint_dir / latest["full"]
    phenotype = pickle.loads(full_path.read_bytes())
    
    # Verify age
    age_hours = (datetime.utcnow() - phenotype["timestamp_dt"]).total_seconds() / 3600
    if age_hours > 24:
        logger.warning(f"Phenotype snapshot is {age_hours:.1f}h old, re-syncing from exchange")
        return None
    
    # Verify positions still exist on exchange
    if phenotype.get("positions"):
        adapter = get_exchange_client()
        live_positions = adapter.get_positions()
        for symbol in list(phenotype["positions"].keys()):
            if symbol not in live_positions:
                logger.warning(f"Position {symbol} no longer exists on exchange, removing from phenotype")
                del phenotype["positions"][symbol]
    
    return phenotype
```

### Slow Path (No valid snapshot)

1. Call `deterministic_startup.py` three-stage startup (CLEANUP → INIT → VERIFY)
2. INIT stage re-syncs positions from exchange API
3. Risk state resets to safe defaults (daily_pnl=0, CB inactive)
4. Coordination state enters COLD_START

## 6. Integration Points

| Component | Change Required |
|-----------|----------------|
| `checkpoint_manager.py` | Add `save_phenotype()` / `restore_phenotype()` methods |
| `orchestrator.py` | Call `save_phenotype()` on state transitions; call `restore_phenotype()` during COLD_START |
| `risk_manager.py` | Expose `get_risk_state()` / `restore_risk_state()` for phenotype inclusion |
| `execution_engine.py` | Expose `get_positions_state()` for phenotype inclusion |
| `monitor_agent.py` | Log phenotype save/restore events to JSONL |
| `deterministic_startup.py` | Stage 1 (CLEANUP) includes phenotype restore attempt |

## 7. File Layout

```
data/
├── phenotypes/
│   ├── latest.json              # Pointer to current full snapshot
│   ├── phenotype_20260516T06.pkl  # Full snapshots (pickle)
│   ├── phenotype_20260516T07.pkl
│   └── delta_847.json           # Delta snapshots (JSON)
│   └── delta_848.json
├── checkpoints/                 # Signal checkpoints (existing)
├── events/                      # JSONL event log (existing)
└── logs/                        # Application logs (existing)
```

## 8. Housekeeping

- Full snapshots older than 7 days: delete (keep last 24 hourly + 7 daily)
- Delta snapshots older than 24 hours: compact into next full snapshot
- `latest.json` is always up-to-date (atomic write via temp+rename)
- Total disk budget: ~5MB (negligible)

---

_This design is ready for implementation. Priority: P2 (after systemd deployment and WS3a/WS3b validation)._
