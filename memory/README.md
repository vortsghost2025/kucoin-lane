# KuCoin Lane Memory Bank

PURPOSE: Persistent facts about kucoin-lane state, architecture, and findings.
This survives across sessions and agents. Journal entries are chronological;
memory entries are the accumulated truth.

## Contents

| File | Purpose |
|------|---------|
| `key-findings.md` | Accumulated key findings from all sessions |
| `blocker-matrix.md` | Live go-live blocker matrix, updated as blockers are resolved |
| `wire-map.md` | Which classes are wired into runtime vs dead code |

## Rules

- Memory is accumulated truth. When a finding is confirmed, it stays.
- Journal is chronological. When a session completes, it goes in journal/.
- Do not delete memory entries — only add or update.
- If a finding is disproven, mark it as SUPERSEDED with a reference to the new finding, do not delete.
