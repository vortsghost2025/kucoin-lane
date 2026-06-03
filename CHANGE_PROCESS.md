# Change Process — Per-Change Discipline

**Established:** 2026-06-03T17:01Z
**Purpose:** Enable multi-agent (interior + exterior) review of all changes with full traceability

## Rules

Every logical change MUST follow this exact sequence:

1. **BEFORE test** — Run full test suite, record pass/fail count
2. **Make the change** — Single logical unit of work
3. **AFTER test** — Run full test suite, record pass/fail count, diff from BEFORE
4. **Journal update** — Add dated/timestamped entry to AUTONOMOUS_MONITORING_JOURNAL.md with:
   - What was changed (files, lines, purpose)
   - BEFORE test results (count, any failures)
   - AFTER test results (count, any failures, diff from before)
   - What the change achieves / why
   - Any observations or caveats
5. **Commit** — Detailed commit message with:
   - Title: `type(scope): summary`
   - Body: what changed, before/after test results, journal entry reference
   - Reference: "Journal Entry #N"

## Commit Message Format

```
type(scope): summary

CHANGES:
- file1: what changed
- file2: what changed

TESTING:
- Before: N tests passing (or N pass / M fail)
- After: N tests passing (or N pass / M fail)
- Diff: +X new tests, 0 regressions

JOURNAL: Entry #N — 2026-06-03T17:01Z
```

## Types
- `feat`: new feature
- `fix`: bug fix
- `refactor`: restructuring without behavior change
- `test`: adding/updating tests
- `docs`: documentation only
- `chore`: maintenance, config, tooling
- `research`: research scripts, data, analysis

## Why This Matters

Multiple AI agents (different models) can review progress at any time by reading:
1. Git log — detailed per-change commits with test evidence
2. Journal — narrative context, rationale, observations per change
3. Test suite — objective pass/fail proof that nothing regressed

This creates a complete audit trail that any agent can parse and evaluate.
