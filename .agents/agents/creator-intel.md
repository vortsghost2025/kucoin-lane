---
name: creator-intel
description: Creator Intelligence & Reputation — Helius resolution, alpha detection, serial launchers
version: 1.0.0
---

# @creator-intel — Creator Intelligence & Reputation

**Domain**: Wallet resolution via Helius, reputation scoring, alpha creator identification, serial launcher tracking  
**Primary Output**: Creator profiles with reputation score, alpha flags, historical performance  
**Context Keys Read**: `scan_results.*` (for new token mints)  
**Context Keys Written**: `creator_registry.*`, `health.api_latency.helius`

---

## Invocation

```bash
# Resolve creator for a token mint
@creator-intel resolve --mint BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump --helius

# Bulk resolve from recent scans
@creator-intel bulk --source phantom --limit 50

# Get creator profile
@creator-intel profile --wallet 7xK...pump

# List alpha creators
@creator-intel alphas --min-score 0.7
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `opportunity-solution-tree` | Map creator behaviors to outcomes (alpha vs rug) |
| `prioritize-features` | Prioritize Helius API calls by signal value |
| `user-segmentation` | Segment creators by behavior (alpha, serial, rugged, new) |
| `cohort-analysis` | Track creator cohorts by first-launch month |
| `source-driven-development` | Ground Helius API calls in official docs |
| `pm-skills/pm-data-analytics:cohort-analysis` | Creator cohort retention curves |

---

## Reputation Scoring

| Factor | Weight | Calculation |
|--------|--------|-------------|
| **Win Rate** | 30% | Tokens with >2× ROI / Total launches |
| **Avg ROI** | 25% | Geometric mean of all launches |
| **Rug Rate** | 20% | Launches with < 0.5× ROI / Total |
| **Volume** | 15% | Total SOL deployed across launches |
| **Consistency** | 10% | Std dev of launch intervals (lower = better) |

**Score Range**: 0.0 (rugged) → 1.0 (consistent alpha)  
**Alpha Threshold**: ≥ 0.70  
**Serial Launcher**: ≥ 5 launches, win rate > 40%

---

## Helius Resolution Flow

```
Token Mint → Helius getTokenAccountsByOwner (creator wallet)
  → getSignaturesForAddress (creator tx history)
  → Filter for token creation instructions
  → Aggregate launch history per creator
  → Compute reputation score
  → Cache in creator_registry
```

Rate limit: 100 req/s (Helius), batch requests where possible.

---

## Output Schema

```json
{
  "success": true,
  "creator": {
    "wallet": "7xK...pump",
    "first_seen": "2026-01-15T10:30:00Z",
    "total_launches": 23,
    "reputation_score": 0.82,
    "is_alpha": true,
    "is_serial": true,
    "stats": {
      "win_rate": 0.65,
      "avg_roi": 3.4,
      "rug_rate": 0.09,
      "total_volume_sol": 145.2,
      "avg_launch_interval_hours": 72.5
    },
    "recent_launches": [
      {"mint": "BAum...", "roi": 2.1, "at": "2026-06-10T19:11:25Z"},
      {"mint": "XyZ...", "roi": 0.3, "at": "2026-06-08T14:22:10Z"}
    ]
  }
}
```

---

## Context Updates

Writes to `creator_registry`:
- `total_creators`: count
- `alpha_creators`: list of wallets with score ≥ 0.7
- `serial_launchers`: list of wallets with ≥5 launches
- `last_resolved`: ISO timestamp

---

## Acceptance Criteria

- [ ] Helius resolution < 2s per wallet (batched)
- [ ] Reputation score matches manual audit on 20-sample test set
- [ ] Alpha creators list matches known alpha wallets (backtest)
- [ ] Serial launcher detection catches known serial deployers
- [ ] Cache hits reduce Helius calls by >80% on repeat scans
- [ ] Errors recorded to `health.anomalies` with wallet attribution