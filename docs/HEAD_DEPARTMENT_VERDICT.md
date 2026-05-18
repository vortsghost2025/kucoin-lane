# KuCoin Lane — HEAD DEPARTMENT VERDICT

OUTPUT_PROVENANCE:
agent: kucoin-headless-agent (opencode/deepseek-v4-flash-free)
lane: kucoin
target: sean-operating-workflow
status: in-progress (Mission 1 complete, proceeding sequentially)

> **Documentation hierarchy:** `memory/` is the canonical structured source. This file is the narrative companion. When facts conflict, `memory/` wins. See the [Documentation Relationship Map](../README.md#documentation-relationship-map) in the root README for the full map of docs → memory → governance relationships.

---

## MISSION 1 — SYSTEM MAP FOR THE OPERATOR

### How to read this map

This is not an architecture diagram. It is an **operator decision table**. For each surface, it answers:
1. What is it for?
2. What work goes there?
3. What work does NOT go there?
4. What outputs should I expect?
5. What tells me it's healthy?
6. What does failure look like?

---

### Archivist

| Question | Answer |
|----------|--------|
| **Role** | Governance gatekeeper & lane-relay hub. Owns the inbox/outbox fabric that connects all lanes. Ratifies, quarantines, or escalates claims. Maintains the governance artifact trail. |
| **Good tasks** | Lane-relay routing, inbox/outbox processing, governance policy enforcement, provenance ratification, artifact quarantine, cross-lane coordination requests, authority escalation |
| **Bad tasks** | Lane-local development, code changes in any lane, monitoring snapshots, research analysis, trading operations |
| **Expected outputs** | Processed inbox items, ratified/quarantined artifacts, lane-relay state, heartbeat-authority.json, governance escalation records, cp-operator-recs |
| **Health signals** | Inbox processing cadence is regular (no pileup), outbox deliveries flow, heartbeats current, no blocked/expired items accumulating, Archivist inbox shows cp-operator-recs arriving |
| **Failure modes** | Inbox backlog grows → lanes can't relay state → stale artifacts propagate. Unprocessed quarantine → degraded governance. Archivist goes silent → no lane has cross-lane visibility. Hallmark: items sit in action-required or blocked for days. |

**Operator check:** `ls Archivist-Agent/lanes/*/inbox/action-required` — any items older than 24h means relay is stalling.

---

### Library

| Question | Answer |
|----------|--------|
| **Role** | Evidence classification & truth assessment. Takes raw findings, classifies them as confirmed/partially confirmed/inferred/unresolved, maintains durable evidence corpus. |
| **Good tasks** | Evidence intake, truth classification, provenance verification, contradiction detection, cross-session reconciliation, drift baseline maintenance |
| **Bad tasks** | Lane-local development, trading operations, real-time monitoring, governance enforcement, emergency response |
| **Expected outputs** | Classified evidence records, truth assessments, provenance verification results, drift baselines, contradiction reports, intake classification from lanes |
| **Health signals** | Journal is current (entries within last 24h), evidence intake is flowing, no large backlog of unclassified items, truth files are being updated, session-owner alignment is stable |
| **Failure modes** | Journal gap → no one knows what Library has or hasn't classified. Stale evidence → decisions based on old data. Misclassification → wrong truth propagates. Hallmark: library-status supervision card goes stale, journal gap exceeds 3 days. |

**Operator check:** Open `docs/supervision/library-status-*.md` in Control Plane. If the most recent is >1 week old, Library is unsupervised.

---

### SwarmMind

| Question | Answer |
|----------|--------|
| **Role** | Multi-agent optimization & coordination plane. Runs agent swarms for complex tasks, manages broadcast communication, maintains system state across agents. |
| **Good tasks** | Multi-agent orchestration, broadcast messaging, optimization campaigns, cross-agent evidence collection, drift-baseline production, resilience policy integration |
| **Bad tasks** | Lane-local git mutations*, singleton agent work, real-time trading execution, governance enforcement (*exception: SwarmMind's own repo) |
| **Expected outputs** | System state reports, drift baselines, verified evidence bundles, broadcast messages, optimization results, e2e probe results, terminology alignment |
| **Health signals** | System state report is current, evidence baselines are updating, broadcast flows work, no stalled probes or hung agent swarms |
| **Failure modes** | System state goes stale → agents operate on outdated baselines. Broadcast failure → agents desync. Swarm gets stuck → no optimization output. Hallmark: SYSTEM_STATE_REPORT is >1 week old, or e2e-probe-results show failures. |

**Operator check:** `ls SwarmMind/docs/system-state/SYSTEM_STATE_REPORT_*.md` — most recent timestamp should be within days.

---

### Kernel-Lane

| Question | Answer |
|----------|--------|
| **Role** | Core system operations & infrastructure. Compilation targets, benchmarks, performance baselines, low-level system integrity. |
| **Good tasks** | Infrastructure builds, benchmark runs, performance baselines, system integrity checks, CUDA/toolchain compilation, baseline metrics |
| **Bad tasks** | Trading decisions, governance enforcement, research analysis, evidence classification |
| **Expected outputs** | Compiled artifacts, benchmark reports, baseline_key_metrics.csv, performance comparisons, system integrity proofs |
| **Health signals** | Builds succeed, benchmarks produce expected metrics, baselines are current, no stalled compilation jobs |
| **Failure modes** | Build failures → dependent lanes can't deploy. Stale baselines → performance regression undetected. Hallmark: baseline_key_metrics.csv is stale or missing. |

**Operator check:** `ls Kernel-Lane/artifacts/` — recent build artifacts should exist. `ls Kernel-Lane/baselines/` — should be current.

---

### KuCoin Lane

| Question | Answer |
|----------|--------|
| **Role** | KuCoin margin trading bot. Dry-run safe, live-trade capable. Self-healing, self-upgrading, fully autonomous within bounded safety constraints. |
| **Good tasks** | Trading cycles (dry-run first), safety audits, monitoring pipeline maintenance, readiness verification, state durability checks |
| **Bad tasks** | Governance enforcement for other lanes, cross-lane coordination without Archivist relay, research that belongs in Research Intake, evidence classification that belongs in Library |
| **Expected outputs** | SESSION_STATE.json, bot_heartbeat.json/hourly snapshots, trade results (dry-run), audit results, monitoring analysis (daily/weekly/monthly), portfolio state |
| **Health signals** | 302/302 tests pass, SESSION_STATE is current, bot_heartbeat shows recent cycles, monitoring snapshots are updating hourly, auditor passes clean, circuit breaker is not active |
| **Failure modes** | SESSION_STATE stale → bot not running. Tests fail → regression undetected. Auditor detects violations but doesn't halt → trading continues in degraded state (current gap B3). Circuit breaker classes defined but not wired → no real safety layer (current gap B2). No systemd service → doesn't survive reboot (current gap B1). |

**Operator check:** `cat lanes/kucoin/inbox/SESSION_STATE.json` — timestamp should be minutes not hours/days stale. `ls bot_heartbeat_dry_run.json` — should exist with recent cycle data.

---

### Control Plane

| Question | Answer |
|----------|--------|
| **Role** | System supervision, observability, and change control. The operator's dashboard into the whole ecology. Monitors lane health, produces supervision cards, enforces change control, tracks live sessions. |
| **Good tasks** | Cross-lane health snapshots, supervision card production, live-session tracking, change control enforcement, provenance verification, precommit gate checks, operator dashboard maintenance |
| **Bad tasks** | Lane-local execution, trading, evidence classification, governance enforcement (that's Archivist's job), research |
| **Expected outputs** | Supervision cards (per lane: library-status, kucoin-status, etc.), cp-supervise reports, live-session convergence artifacts, change control records, agent-logs, headless-observations |
| **Health signals** | Supervision cards are current (within days), headless-observations are updating, agent-logs have recent entries, change control is being enforced |
| **Failure modes** | Supervision cards go stale → operator blind to lane health. Change control not enforced → unauthorized mutations. Live-session tracking lost → can't tell if agents are working. Hallmark: supervision cards >1 week old, or agent-logs empty for days. |

**Operator check:** `ls docs/supervision/` — there should be recent (<1 week) files for each lane. `ls agent-logs/` — should have recent session logs.

---

### Research Intake

| Question | Answer |
|----------|--------|
| **Role** | Anomaly intake & experiment design. Takes unusual observations (session continuity phenomena, persistent unexplained behavior, recurring bugs) and designs bounded experiments to investigate them without inflating them into theories. |
| **Good tasks** | Anomaly triage, experiment design, bounded investigation, work-order creation, cross-session continuity analysis, hypothesis testing |
| **Bad tasks** | Trading execution, governance enforcement, real-time monitoring, production code changes not related to research |
| **Expected outputs** | Work orders (numbered, tracked), experiment results, anomaly classification, research packets, recommendations for lane assignments |
| **Health signals** | Work orders are being processed, experiments produce clear results (confirmed/refuted), no build-up of uninvestigated anomalies |
| **Failure modes** | Anomalies inflate into theories ungrounded in evidence. Work orders pile up unprocessed. Experiments don't produce clear yes/no results. Hallmark: work-order list grows without resolution, or anomalies are reclassified without new evidence. |

**Operator check:** `ls WE4FREE-Research-Intake/work-orders/` — check the most recent files. If there are 10+ open orders, research is backlogged.

---

### Federation

| Question | Answer |
|----------|--------|
| **Role** | Experimental product plane. Runs alternative architectures, protocol experiments, and integration tests that don't belong in a production lane. |
| **Good tasks** | Protocol experiments, cross-system integration tests, alternative architecture exploration, agent communication protocol design, broadcast system development |
| **Bad tasks** | Production trading, governance enforcement for live lanes, evidence classification for live findings |
| **Expected outputs** | Agent context docs, architecture maps, build summaries, protocol validation results, agent communication tests |
| **Health signals** | Experiments produce clear outcomes, agent communication tests pass, architecture maps are being updated |
| **Failure modes** | Experimental results not captured → learnings lost. Federation drifts from lane reality → experiments irrelevant. Hallmark: architecture maps are stale or experiments run without documented outcomes. |

**Operator check:** `ls federation/ARCHITECTURE_MAP.md` — is it current? `ls federation/BUILD_SUMMARY*.md` — recent summaries indicate active experimentation.

---

### Lane / Plane Responsibility Model (Quick Reference)

```
GOVERNANCE LAYER
  Archivist — gatekeeper, relay, quarantine, ratification
  Control Plane — supervision, observability, change control

EVIDENCE LAYER
  Library — classification, truth assessment, durability

COORDINATION LAYER
  SwarmMind — multi-agent optimization, broadcast, swarms
  Federation — experimental product plane

OPERATIONS LAYER
  Kernel-Lane — infrastructure, builds, benchmarks
  KuCoin Lane — trading bot, monitoring, readiness

RESEARCH LAYER
  Research Intake — anomaly intake, experiment design, hypothesis testing
```

---

### Mission 1: Key Takeaway for Sean

**You don't have to monitor everything.** The system has natural health indicators:

1. **SESSION_STATE.json freshness** tells you if KuCoin is alive
2. **Supervision card freshness** tells you if Control Plane is watching
3. **Inbox backlog** tells you if Archivist is relaying
4. **Journal gap** tells you if Library is classifying
5. **System state report** tells you if SwarmMind is coordinating

If all five are current, the ecology is healthy. Check those five things first, nothing else.

---

*Journal entry: /mnt/s/kucoin-lane/journal/2026-05-18_headless_readiness_pass.md (this and subsequent mission outputs being appended sequentially)*

---

## MISSION 2 — FROM NEW LAPTOP TO FULL OPERATIONS WORKFLOW

### PHASE 0 — Access & Identity

**Goal:** Connect to the right machine, confirm your identity, avoid working on the wrong host.

| Step | Action | Verification |
|------|--------|-------------|
| 0.1 | Connect to Tailnet (Tailscale). `tailscale status` should show the headless machine. | ✅ `tailscale status` shows expected hostnames |
| 0.2 | SSH into the headless. `ssh we4free@<headless-host>` | ✅ You get a shell on the correct host |
| 0.3 | Confirm host identity. `hostname && cat /etc/hostname && uptime` | ✅ Hostname matches expected. Uptime should be plausible (not just rebooted) |
| 0.4 | Confirm datetime. `date -u +%Y-%m-%dT%H:%M:%SZ` | ✅ Time is correct. Wrong datetime breaks git, SESSION_STATE timestamps, and monitoring freshness. |
| 0.5 | Check who else is connected. `w` or `who` | ✅ Know if other sessions exist. If someone else is working, coordinate. |
| 0.6 | Jump to home directory. `cd /home/we4free/agent/repos` | ✅ You see the repo root |

**What can go wrong:**
- Wrong host: `hostname` doesn't match → disconnect and reconnect to correct host
- Can't reach tailnet: check `tailscale status`, try `tailscale up` or restart tailscale
- SSH key issues: check `~/.ssh/authorized_keys`, or use tailscale SSH (`ssh we4free@<tailnet-name>`)
- SSH to WSL path instead of headless: double-check the hostname/IP

---

### PHASE 1 — Headless Health Check

**Goal:** Before trusting the system, verify it's alive and coherent.

**The Five-Pulse Check** (in order, ~60 seconds):

```
1. Is the repo dir intact?
   ls kucoin-lane/src/
   → Should show intelligence/, execution/, risk/, monitoring/, data/ dirs

2. Is git clean?
   cd kucoin-lane && git status
   → Ideally clean. Dirty is ok if documented. Diverged is a problem.

3. Is the S: drive mounted?
   ls /mnt/s/kucoin-lane/inbox/SESSION_STATE.json
   → If SESSION_STATE.json is missing or days stale, the system may not
     have written state recently. This is the single most important
     health indicator.

4. Are the tests passing?
   cd kucoin-lane && source venv/bin/activate && pytest tests/ -q
   → Should report 302 passed (or close to it). If tests are failing,
     don't trust the system until you understand why.

5. Are the agents running?
   systemctl --user list-units --type=service --state=running 2>/dev/null
     | grep -i kucoin
   → Currently: none (B1). Other lanes: 16/16 services active.
   → Fallback: check ps aux for any python/kucoin processes
```

**Decision gate:** If any of the five checks fail, investigate before proceeding to Phase 2. If all five pass, the system is safe to operate.

**What must be healthy before trusting the system:**
- SESSION_STATE.json must be less than 1 hour stale (for a running system) or less than 24h stale (for an idle one that shut down cleanly)
- Tests must pass (regression means something changed that isn't understood)
- S: drive must be accessible (no monitoring data will make sense without it)
- Git must not be diverged from remote (if it is, figure out why before pushing/pulling)

---

### PHASE 2 — Operator Dashboard & Observability Check

**Goal:** Understand the current state of all lanes before assigning work.

**What to open first (in order):**

| # | What | Why | How |
|---|------|-----|-----|
| 1 | **SESSION_STATE.json** | Formal lane state — is KuCoin alive? | `cat /mnt/s/kucoin-lane/lanes/kucoin/inbox/SESSION_STATE.json` |
| 2 | **latest-monitoring-snapshot.md** | Human-readable summary of monitoring | `cat kucoin-lane/docs/automation/latest-monitoring-snapshot.md` |
| 3 | **Control Plane supervision cards** | Cross-lane health snapshots | `ls /mnt/s/WE4FREE-Control-Plane/docs/supervision/` |
| 4 | **Library journal** | Is Library classifying evidence? | `ls /mnt/s/self-organizing-library/journal/ 2>/dev/null` or check latest entry |
| 5 | **System state report** | Is SwarmMind coordinating? | `cat /mnt/s/SwarmMind/docs/system-state/SYSTEM_STATE_REPORT_*.md` (most recent) |
| 6 | **Research Intake work-orders** | Any open anomalies? | `ls /mnt/s/WE4FREE-Research-Intake/work-orders/` |
| 7 | **Agent-logs** | Previous session traces | `cat kucoin-lane/agent-logs/latest-kucoin-session.md` |

**How to read stale-vs-live indicators:**

| Artifact | Fresh means | Stale means |
|----------|-------------|-------------|
| SESSION_STATE | < 1h (running), < 24h (idle) | Bot hasn't written recently |
| Monitoring snapshot | < 2h | Systemd timer may have failed |
| Supervision card | < 1 week | Control Plane hasn't checked that lane |
| Library journal | < 24h | Library isn't producing evidence |
| System state report | < 1 week | SwarmMind may be stalled |
| Agent-logs | < 24h if agent was active | Session ended, no recent work |

**What to consider safe to ignore:**
- Individual test log files in `test_logs/` — they accumulate; check only if debugging
- `firebase-debug.log` — noise unless you're debugging Firebase
- Single stale monitoring snapshot on a known-idle system (e.g., overnight when no cycles ran)

**What must investigate:**
- SESSION_STALE when the bot should be running
- Supervision cards all stale simultaneously
- Growing inbox backlog in any Archivist lane inbox

---

### PHASE 3 — Choosing Which Lane to Task

**Decision rule:** Match the work type to the surface that owns it.

| If you want to... | Send it to... | Example prompt |
|-------------------|---------------|----------------|
| Run a trading cycle | KuCoin Lane | "Run one dry-run cycle and report results" |
| Check cross-lane health | Control Plane | "Snapshot all lane health indicators" |
| Classify a finding as truth | Library | "Classify this auditor mismatch finding: [link]" |
| Investigate a weird anomaly | Research Intake | "Here's an anomaly I noticed: [desc]" |
| Escalate a governance question | Archivist | "Route this to authority for ratification" |
| Coordinate multiple agents | SwarmMind | "Orchestrate a multi-agent audit of X" |
| Build/compile/benchmark | Kernel-Lane | "Run the benchmark suite and report" |
| Experiment with a protocol | Federation | "Prototype this agent communication pattern" |

**What does NOT go where:**
- Do NOT ask Archivist to do monitoring (that's Control Plane's job)
- Do NOT ask Library to trade (that's KuCoin's job)
- Do NOT ask KuCoin to classify evidence (that's Library's job)
- Do NOT ask SwarmMind to mutate another lane's repo (that's the lane's job)
- Do NOT ask Research Intake to write production code in a lane (that's the lane's job, Research Intake produces recommendations)

---

### PHASE 4 — Launching Work Responsibly

**A good prompt packet contains:**

```
OUTPUT_PROVENANCE:
agent: [which agent type]
lane: [which lane]
target: [what file or surface]

CONTEXT:
[2-3 sentences of relevant context]

TASK:
[Clear, bounded description of what to do]

CONSTRAINTS:
- Do not mutate [X]
- Do not print secrets
- Verify with [Y]
- If blocked, [do Z]

DELIVERABLE:
[What to produce: report, file, test output, etc.]

VERIFICATION:
[How to confirm it's done: pytest path, specific test name, file check]
```

**Every agent assignment should include:**
1. **Provenance** — who sent it, from which lane
2. **Target** — what surface or file to work on
3. **Constraints** — what not to do (especially: no live trading, no secret printing, no cross-repo mutation without authorization)
4. **Mutation permissions** — exactly which files/repos may be changed
5. **Verification expectations** — how to prove the work is correct
6. **Blocked behavior** — what to do if stuck (stop, document, escalate, continue with what you can)

**How to prevent agents from asking every 90 seconds:**
- Set explicit context on whether this is a bounded single task ("run this test and report") vs open-ended exploration ("investigate and produce recommendations")
- Bounded tasks get completion expectations; open-ended tasks get time budgets
- "If you're stuck for more than 3 tool calls without progress, document what's blocking you and stop, don't spin"

---

### PHASE 5 — Monitoring Live Work

**How to watch without micromanaging:**

| Signal | Interpretation |
|--------|----------------|
| Tool calls are making visible progress in file system / outputs | Working normally |
| Same tool call repeated 3+ times | Stuck — may need operator intervention |
| Long silence (>2 min) without progress | Likely hitting a timeout, permission prompt, or MCP failure |
| Agent asks same question repeatedly | False progress — it's looping |
| Agent produces identical output twice | Repetition — may need a reset |
| Agent reports "waiting for permissions" or "blocked" | Permission prompt — check for filesystem prompts |

**What artifacts should be refreshed while it runs:**
- SESSION_STATE.json (if running a trading cycle, it should update every cycle)
- Agent-logs heartbeat (should see new entries every ~10-15 min)
- If monitoring the monitoring: hourly_snapshots.jsonl should add lines on the hour

**What to do when an agent seems stuck:**
1. Check the latest output — is it actually stuck or just processing?
2. Check file system — did it create partial artifacts?
3. Check for filesystem permission prompts (common in opencode)
4. If truly stuck: `Ctrl+C` and re-prompt with more specific instructions

---

### PHASE 6 — Completion & Truth Classification

**What counts as DONE:**

| Evidence type | What it means | Trust level |
|---------------|---------------|-------------|
| `pytest tests/ -q` passes | All unit tests pass | **High** — verification is automated |
| File was created with expected content | Output exists | **Medium** — content quality must be verified |
| Runtime check (`python -c "import X"` passes) | Module loads correctly | **High** — import chain verified |
| File refs are accurate | Output references real line numbers | **Medium** — requires manual spot-check |
| State before/after comparison | Change is documented | **High** — provenance trail exists |
| Live HTTP verification | API responds correctly | **High** — external confirmation |
| Type check passes | No type errors | **Medium** — depends on coverage |
| Agent claims "it works" | No verification provided | **Low** — do not accept without evidence |

**What counts as report only:**
- Findings from observational passes (no mutations)
- Anomaly descriptions without resolution
- Recommendations for future work
- Architecture analysis that doesn't change code

**What counts as claimed but not proven:**
- "Tests pass" without running them
- "I fixed the bug" without showing the diff
- "It should work because the logic is correct" without runtime verification

**When Library should audit a result:**
- Any finding that becomes a blocker (B1-B7 level)
- Any cross-lane pattern (e.g., auditor-governance mismatch appears in multiple lanes)
- Any result that contradicts prior truth classification
- Any finding that Research Intake escalated

**When Archivist should ratify or quarantine:**
- A finding that changes governance policy
- A claim that can't be verified but might be important (quarantine)
- A result that needs to be relayed to another lane
- A claim that conflicts with established governance (escalate to authority)

---

### PHASE 7 — End of Session & Continuity Preservation

**What must be journaled:**
- What was the task? (one line)
- What was actually done? (brief)
- What was verified? (tests passed, files created, etc.)
- What is unresolved? (blockers, questions for next session)
- What should the next agent do? (clear next action)

**What must enter memory bank:**
- New architectural findings (e.g., "CircuitBreaker class exists but is not wired")
- Changed blocker status (e.g., "B3 now fixed")
- New persistent truths (e.g., "SESSION_STATE write path verified coherent")
- Cross-lane patterns (e.g., "auditor-governance mismatch may exist in other lanes")

**What should be compactrestore-safe:**
- Memory bank files (key-findings.md, blocker-matrix.md, wire-map.md)
- Journal entries (chronological record of what happened)
- HEAD_DEPARTMENT_VERDICT.md or equivalent final deliverables
- SESSION_STATE.json with final=true if shutting down

**What live session breadcrumbs to preserve:**
- `agent-logs/latest-kucoin-session.md` — full session trace
- `agent-logs/kucoin-session-heartbeats.jsonl` — heartbeat record
- SESSION_STATE.json with final=true and phase=terminating

**Handoff checklist before walking away:**

```
[ ] Journal written to S:/kucoin-lane/journal/YYYY-MM-DD_*.md
[ ] Memory bank updated (key-findings.md, blocker-matrix.md)
[ ] FINAL heartbeat written with summary and next action
[ ] Agent session state finalized (SESSION_STATE.json final=true)
[ ] Bot heartbeat finalized (final=true)
[ ] Git status clean (or documented why dirty)
[ ] Tests verified passing
[ ] What the next agent should do is recorded
```

---

### Mission 2: Key Takeaway for Sean

**The five-pulse check (Phase 1) is your shield against stale-state blindness.** Always do it before trusting any surface. It takes 60 seconds and prevents your entire session from being built on false assumptions.

**Phase 7 is the most important phase for continuity.** A 2-minute journal and memory bank update determines whether the next agent can continue your work or has to rediscover everything.

---

## MISSION 3 — SECURITY & SAFETY DOCTRINE

### 1. Secret Handling

**Principle:** Secrets never leave the headless. Agents inspect paths, not values.

| Secret Type | Where It Lives | Who May Access | What Agents May Do |
|-------------|---------------|----------------|-------------------|
| API keys (KuCoin, CoinGecko) | `.env` file, environment variables | KuCoin lane runtime only | Verify `.env` exists; **never print, log, or transmit** key values |
| Trading credentials | `config.py` (reads from env vars) | KuCoin lane runtime only | Inspect that config loads; **never print or expose** |
| Webhook/dashboard secrets | environment variables | Lane that registered them | Verify presence; **never print or include in output** |
| SSH keys | `~/.ssh/` | Operator only | Agents should never touch these |
| Tailscale keys | tailscale state | Operator only | Agents should never touch these |

**Rules:**
- An agent may check `os.environ.get("KUCOIN_API_KEY") is not None` to verify a key is set, but may **never** print its value
- An agent may read `.env` to confirm the file exists and has expected variable names, but may **never** output the values
- Any agent output containing a secret must be redacted immediately — the session that produced it should be flagged for review
- If an agent needs to know "is this credential configured?", it asks the runtime, not the file

**Current state:** KuCoin lane's `config.py` reads from environment variables only. `.env` is in `.gitignore`. No plaintext secrets in code. ✅

---

### 2. Mutation Boundaries

**Principle:** No lane silently modifies another lane's repo. Cross-repo changes require explicit operator authorization.

**Rule table:**

| Change type | Authorization needed | Verification |
|-------------|---------------------|--------------|
| Mutate your own lane's code | Lane-local decision | Tests pass, git tracks changes |
| Read another lane's artifacts | No auth needed (read-only) | Provenance logged |
| Write to another lane's inbox | Archivist relay convention | Path matches expected contract |
| Mutate another lane's source code | **Explicit operator approval required per change** | Diff reviewed, provenance logged |
| Create a new file in another lane's docs/ | Operator consent for that file | Path and purpose documented |
| Delete or move files in another lane | **Operator approval + Archivist knowledge** | Never done without explicit written authorization |

**How to enforce in practice:**
- The operator states mutation permissions in every prompt packet (Phase 4 standard)
- Agents default to read-only unless explicitly authorized to write
- Cross-lane coordination goes through Archivist inbox/outbox, not direct git pushes
- Any agent caught mutating without authorization = session integrity review

**Current state:** No known cross-lane mutation violations in KuCoin session. Good practice established.

---

### 3. Drift & Stale-State Hazards

**Principle:** Stale artifacts look identical to fresh ones. The only defense is checking timestamps.

| Hazard | How It Looks | How to Detect It |
|--------|-------------|------------------|
| Stale SESSION_STATE | File exists, looks valid | Check `timestamp` field against current time |
| Stale monitoring snapshot | Markdown looks normal | Check "Last updated" timestamp |
| Agent reports healthy from old data | Agent says "all good" | Cross-check SESSION_STATE and heartbeat freshness |
| Local/headless divergence | Same repo, different states | `git status` and `git log --oneline -5` on both machines |
| Stale hourly snapshot | Snapshot exists but no new entries | Check last entry timestamp vs current hour |
| Stale supervision card | Card exists but references old state | Check the dateline in the card |

**Defense procedures:**

1. **Before trusting any artifact, check its timestamp.** If no timestamp exists, assume it's stale.
2. **Cross-verify from two independent sources.** For example: SESSION_STATE + heartbeat + `ps aux` for a running process.
3. **SESSION_STATE.json is the canonical source of truth for KuCoin lane health.** If it's fresh, the bot is alive. If it's stale, don't trust any downstream monitoring that depends on it.
4. **Derived views are never truth.** `latest-monitoring-snapshot.md` is a summary; SESSION_STATE.json is truth. If they disagree, truth wins.
5. **When in doubt, re-verify from the live system.** Run a test, check a process, inspect a file.

**Current state:** Monitoring pipeline correctly separates formal state (SESSION_STATE) from derived views (snapshots). Freshness checking is manual but straightforward.

---

### 4. Monitoring Integrity

**Principle:** Monitoring observes truth. It does not create truth.

**The monitoring hierarchy (from most to least authoritative):**

```
Level 1 — Raw truth
  SESSION_STATE.json       → "Bot wrote this state"
  bot_heartbeat.json       → "Bot heartbeated at this time"
  systemd journal          → "System logged this event"
  git log / git status     → "This is the actual repo state"

Level 2 — Derived monitoring
  latest-monitoring-snapshot.md  → Summary of Level 1 + context
  hourly_snapshots.jsonl         → Time-series of Level 1 snapshots
  MONITORING_ANALYSIS_daily.md   → Trend analysis from snapshots

Level 3 — Supervision & audit
  Control Plane supervision cards → Cross-lane health assessment
  Library truth classifications   → Evidence durability
  Archivist ratification          → Governance seal
```

**Rules:**
- Level 2 must never overwrite Level 1. Monitoring snapshots are derived, not authoritative.
- If Level 2 contradicts Level 1, **Level 1 wins**. Surface the contradiction, don't mask it.
- Monitoring summaries should surface contradictions explicitly: "SESSION_STATE says final=true but heartbeat says cycle=active"
- All monitoring artifacts must include a `source` or `derived_from` field pointing to their Level 1 origin

**Current state:** KuCoin monitoring follows this correctly. Snapshots derive from SESSION_STATE + heartbeat without overwriting them. ✅

---

### 5. Tool-Call and MCP Reliability

**Principle:** Tool calls fail. Agents degrade gracefully, document the failure, and continue with bounded work.

| Failure mode | What to do | What NOT to do |
|-------------|-----------|----------------|
| Timeout (>30s) | Retry once, then skip and document | Don't retry indefinitely |
| Permission prompt | Report "blocked on filesystem permission" | Don't silently hang |
| File not found | Check alternative paths, report if missing | Don't assume it exists and report success |
| MCP unavailable | Fall back to bash equivalent if safe; otherwise document and skip | Don't stall the entire task |
| Partial output | Report what you got and what's missing | Don't claim complete |
| Stale/cached output | Re-fetch from source if possible | Don't use stale data without flagging it |
| SSH check fails | Report "cannot reach remote" | Don't assume remote state |
| venv/test path mismatch | Verify Python version and venv path | Don't run outside venv |

**Agent degradation pattern:**
```
1. Identify the failure precisely (which tool, what input, what error)
2. Distinguish: work not done vs work disproven
3. Attempt the safest alternate check (e.g., if glob fails, try bash ls)
4. Record the failure in output with enough context to debug
5. Continue with remaining bounded work if possible
6. Escalate only if the failure blocks the entire task
```

**Current state:** This standard is aspirational — no formal policy document exists yet. Agents handle tool failures ad-hoc.

---

### 6. Trading-Specific Strictness for KuCoin

**Principle:** KuCoin lane trades money. This requires twice the verification of any other operation.

| Constraint | Current state | What's needed for live |
|------------|--------------|----------------------|
| Dry-run only | ✅ Enforced by config, mode flag, ExecutionEngine(DryRunMode) | Must explicitly switch to LiveMode |
| No live API keys in .env | ✅ `.env` not present | Must create `.env` with credentials |
| Circuit breaker wired | ❌ Not wired (B2) | Must wire CircuitBreaker class into orchestrator |
| Auditor hard-blocks on violations | ❌ Warning-only (B3) | Must activate circuit breaker on audit failure |
| Systemd service | ❌ Not defined (B1) | Must define and enable service for auto-restart |
| PortfolioCircuitBreaker persistence | ❌ Not wired (B7) | Must wire persistent state |
| Session state survives crash | ✅ SIGTERM/SIGINT handled | SIGKILL gap is acceptable edge case |

**Before live activation, the following evidence must exist:**
1. All 7 blockers (B1-B7) resolved or explicitly accepted
2. Circuit breaker executed at least once in dry-run (proven by test output)
3. Auditor detected violations and halted the cycle (proven by test/log output)
4. Systemd service auto-restarted the bot at least once (proven by journalctl)
5. SESSION_STATE survived restart (proven by timestamp comparison)
6. 7 consecutive days of dry-run without safety violations

**The no-live-trading constraint must be restated in every prompt packet that involves trading operations.** It is the most important constraint in the system.

---

### 7. Restore and Compaction Safety

**Principle:** After a restore or compact handoff, re-verify against live artifacts before trusting state.

**What to preserve across restores:**
- Memory bank files (key-findings.md, blocker-matrix.md, wire-map.md)
- Journal entries (chronological record)
- HEAD_DEPARTMENT_VERDICT.md (final deliverables)
- SESSION_STATE.json (formal state)

**What to re-verify after restore:**
- Git status: `git status` and `git log --oneline -3` — confirm correct branch and recent commits
- SESSION_STATE freshness: compare timestamp to current time
- Test baseline: `pytest tests/ -q` — confirm tests still pass
- S: drive mount: can you still access `/mnt/s/`?
- Import chain: `python -c "from src.monitoring.auditor import AuditorAgent; print('ok')"`
- Any blocker status from memory bank: check if it's still accurate by re-inspecting the relevant file

**What compact summaries can mislead about:**
- "Tests pass" without re-running them (dependency drift, file system changes)
- "SESSION_STATE was fresh" without re-checking (time passed)
- "Blocker was resolved" without re-verifying (the fix might not survive compaction)
- Agent claims from prior sessions that haven't been re-verified against current runtime

**How to re-ground a compacted session:**
1. Run the five-pulse check (Phase 1)
2. Read the memory bank for accumulated truths
3. Read the latest journal entry for the most recent work
4. Pick ONE unresolved item from the journal and carry it forward
5. Re-verify before trusting (don't take the journal's word for test status — re-run)

**Current state:** No formal compactrestore system exists in KuCoin lane. The memory bank + journal structure (just created) is the first step toward it.

---

### Mission 3: Key Takeaway for Sean

**Two rules prevent 90% of the security/safety issues in this ecology:**
1. Never print secrets. An agent can verify they exist without exposing them.
2. Always check timestamps before trusting an artifact. Stale looks identical to fresh.

**On live trading: 6 evidence requirements must be met before activation.** The most important is testable circuit breaker behavior — if it's never been observed to halt a cycle, you don't know it works.

---

## MISSION 4 — MULTI-PLANE WORKFLOW DESIGN

### WORKFLOW A: New Engineering Task (Fixing a Bug)

**Scenario:** A dry-run cycle shows auditor detects violations but doesn't halt trading. You want this gap fixed.

**Step-by-step:**

| Step | Who | What | Evidence Produced |
|------|-----|------|-------------------|
| A1 | **Sean** | Discover the bug. Run a dry-run cycle, see `audit_passed=False` logged as CRITICAL but trading continues. | Observation in agent-logs |
| A2 | **KuCoin Lane** | Trace the auditor execution path. Confirm: auditor returns `audit_passed=False`, orchestrator ignores it. | File refs: orchestrator.py:841-853, auditor.py:execute() |
| A3 | **Library** | Classify the finding. "Auditor violations are warning-only" — is this a design intent or a bug? Check git history, governance docs. | Library truth classification: "Confirmed — governance says hard-blocking, runtime is warning-only" |
| A4 | **Research Intake** | Optional: if this pattern appears in other lanes (same auditor-governance mismatch), open a work order. | Research work-order: "Cross-lane auditor governance mismatch investigation" |
| A5 | **Sean** | Decide: fix the gap. Authorize KuCoin lane to mutate orchestrator.py with a one-line change. | Prompt packet with mutation permission |
| A6 | **KuCoin Lane** | Implement the fix. Add `self.activate_circuit_breaker(...)` at orchestrator.py:848 when audit fails. Run tests. | `pytest tests/ -q` → 302 passed |
| A7 | **Control Plane** | Verify the change. Check supervision card for KuCoin lane. Confirm circuit breaker fires on audit violation in next dry-run. | Updated supervision card, test output showing CB activation |
| A8 | **Archivist** | Relay the change record. The fix and its verification go through inbox for ratification. | Processed inbox item, ratified change record |
| A9 | **Library** | Update truth classification. "B3 resolved — auditor now activates circuit breaker." Mark the old classification as SUPERSEDED. | Updated truth record |
| A10 | **Sean** | Verify end-to-end. Run a dry-run that triggers an audit violation, confirm CB fires, confirm session state reflects it. | Session trace in agent-logs |

**Total operator time:** ~15 minutes (discovery + authorization + verification).  
**Agent work:** ~30 minutes distributed across 4 surfaces.

---

### WORKFLOW B: Research Anomaly / Session Continuity Discovery

**Scenario:** You notice a long-lived session behaves differently after compact handoff. The same agent returns different answers to the same question before and after.

**Step-by-step:**

| Step | Who | What | Evidence Produced |
|------|-----|------|-------------------|
| B1 | **Sean** | Notice the anomaly during a session. "This agent answered X before compaction and Y after — same question." | Raw observation in agent-logs |
| B2 | **KuCoin Lane** | (Or whichever lane owns the session) Document the two answers, the timing, the compact event. Preserve exact prompts and responses. | Timestamped comparison record |
| B3 | **Research Intake** | Open a work order. "Session continuity anomaly: agent response changed across compact boundary." Design a bounded experiment. | Research work-order with experiment design |
| B4 | **KuCoin Lane** | Run the experiment. Same prompt before compact, same prompt after. Record results for 3+ trials. | Experiment output: response pairs |
| B5 | **Library** | Classify the experiment results. If difference is consistent, classify as "confirmed anomaly." If inconsistent, "partially confirmed — needs more data." | Truth classification |
| B6 | **Control Plane** | Update supervision card for the anomaly. Track whether it's being actively investigated or parked. | Supervision card entry |
| B7 | **Research Intake** | Based on classification: either escalate (if real anomaly) or close (if noise). If escalation: what would disprove the hypothesis? | Updated work-order with conclusion or next experiment |
| B8 | **Archivist** | If the anomaly has cross-lane implications (e.g., all agents may shift after compact), relay to other lanes. | Broadcast to lane inboxes |
| B9 | **Library** | If confirmed: add to durable evidence corpus. "Session continuity can shift agent responses after compact." | Permanent evidence entry |

**Rules for not inflating:**
- A single observation is not an anomaly. It's an anecdote.
- 3+ consistent observations with controlled conditions = anomaly.
- If an experiment doesn't have a "what would disprove this" clause, it's not an experiment yet.
- Research Intake's job is to bound the investigation, not to prove the hypothesis.

---

### WORKFLOW C: Headless Operational Issue (Stale Monitoring)

**Scenario:** You reconnect to the headless and notice the monitoring snapshot is from 3 days ago. KuCoin heartbeat hasn't updated in 2 days.

**Step-by-step:**

| Step | Who | What | Evidence Produced |
|------|-----|------|-------------------|
| C1 | **Sean** | Five-pulse check: SESSION_STATE is stale, snapshot is stale, heartbeat is stale. | Initial observation |
| C2 | **Control Plane** | Check systemd status. `systemctl --user status kucoin-lane-monitoring-hourly.timer` — is the timer active? Check journalctl for errors. | Systemd status report |
| C3 | **KuCoin Lane** | Check if the bot process is running. `ps aux | grep python` — is there a python process? If yes, why isn't it writing state? If no, when did it exit? | Process state |
| C4 | **Kernel-Lane** | If timer failed, check system resources. Disk full? OOM kill? Check `dmesg`, `df -h`, `free -h`. | Resource report |
| C5 | **Sean** | Triage decision tree: Is the bot running or not? | |
| | | **If running:** Why isn't it writing state? Check write permissions, S: drive mount status, disk space. | |
| | | **If not running:** Why did it stop? Check logs, exit code, journalctl. Was it intentional (SIGTERM) or crash (SIGKILL/panic)? | |
| C6 | **KuCoin Lane** | If S: drive unmounted: remount and restart monitoring. If bot crashed: check last session state (SESSION_STATE from before crash) and determine if recovery is needed. | Recovery action log |
| C7 | **Control Plane** | After recovery: confirm monitoring timer is active, snapshot was written, heartbeat is flowing. Updated supervision card. | Fresh supervision card |
| C8 | **Library** | Classify the incident. Was this a known failure mode? Does it need a new procedure? | Classification: confirmed incident |
| C9 | **Archivist** | If the incident revealed a new class of failure (e.g., "S: drive drops under load"), relay to other lanes so they can add monitoring for it. | Lane broadcast |

**What gets fixed vs merely documented:**
- S: drive mount issue: fix it (remount, add fstab entry if needed)
- Bot crash without clear cause: document for Research Intake
- Timer failure: fix the timer or replace it
- Each incident gets a journal entry even if "won't fix" — because the same failure may happen to a different lane

---

### WORKFLOW D: KuCoin Lane Readiness / Safety Review

**Scenario:** You want to trust KuCoin lane to remain dry-run-safe and observable overnight without supervision.

**Step-by-step:**

| Step | Who | What | Verification |
|------|-----|------|-------------|
| D1 | **KuCoin Lane** | Run full safety audit: 302 tests pass, auditor detects violations, circuit breaker fires, SESSION_STATE writes every cycle. | `pytest tests/ -q`, audit log, SESSION_STATE timestamp |
| D2 | **Control Plane** | Verify monitoring pipeline: hourly snapshot is being written, heartbeat is flowing, supervision card exists. | Latest snapshot timestamp < 1h, heartbeat timestamp < 1h |
| D3 | **Control Plane** | Verify systemd service: if defined, check it's enabled and active. If not (B1), document as risk. | `systemctl --user is-enabled kucoin-lane` |
| D4 | **Library** | Classify readiness blockers: B2 (circuit breaker dead code) and B3 (auditor warning-only) must be resolved before unattended operation. | Truth: "B2 and B3 are hard blockers for unattended dry-run" |
| D5 | **KuCoin Lane** | Wire circuit breaker (fix B2). Wire auditor → CB activation (fix B3). Verify both produce observable state changes. | Test evidence, audit log showing CB activation |
| D6 | **Control Plane** | After fixes: run a 6-hour unattended test. Check SESSION_STATE at T+1h, T+3h, T+6h. | SESSION_STATE timestamps across 6 hours |
| D7 | **KuCoin Lane** | Produce overnight-readiness report. "B1-B7 status: B2 resolved, B3 resolved, B1/B4/B6 accepted risk, B5/B7 noted." | Readiness report |
| D8 | **Archivist** | Ratify the readiness assessment. If artifacts route through Archivist inbox, confirm they're processed. | Ratified readiness record |
| D9 | **Sean** | Decision: approve unattended dry-run, or require more fixes. Record decision in journal. | Journal entry |

**Prerequisites for unattended dry-run:**
- B2 and B3 must be resolved (circuit breaker + auditor actually halt on violations)
- B1 (systemd service) is required for unattended — if headless reboots, lane must restart
- B4 (API keys) is not a blocker for dry-run
- Monitoring pipeline must be verified independently (not by the lane itself)

---

### Mission 4: Key Takeaway for Sean

**Workflow B is the hardest to get right.** The temptation is to inflate a single observation into a theory. Research Intake's job is to be the skeptic: design experiments that could disprove the hypothesis, and don't classify until you have 3+ controlled observations.

**Workflow D is the most important for unattended trust.** If you can't prove the system can detect and halt on its own violations, you shouldn't leave it unsupervised.

---

## MISSION 5 — TOOL-CALL ERROR HANDLING AND TRANSPARENCY STANDARD

### The Standard

When a tool call fails, the agent must apply this decision sequence:

```
1. IDENTIFY the failure precisely
   → Which tool? What input? What error message?
   → "glob failed with 'Bad message (os error 74)' on pattern **/*.py"

2. DISTINGUISH: work not done vs work disproven
   → "I could not search for that pattern" (not done)
   → "The search returned no results" (disproven — the thing wasn't found)
   → These are different! Don't conflate them.

3. ATTEMPT the safest alternate check
   → glob failed → try `find` or `ls` instead
   → MCP read timed out → try bash `cat` instead
   → File not found at expected path → check alternate paths (with leading / or without)
   → Permission denied on S: drive → check mount, try with /mnt/s/ prefix
   → If no safe alternate exists, skip to step 4

4. RECORD the failure
   → Include: what failed, what you tried instead, what that gave you
   → If it blocked work, say "BLOCKED: [reason]"
   → If you worked around it, say "WORKAROUND: [what you did]"

5. CONTINUE with bounded work if possible
   → If one file can't be read, read the others
   → If one test can't run, run the rest
   → If the main approach failed, document what's missing and move on

6. ESCALATE only when necessary
   → Escalate when: the failure blocks the ENTIRE task AND no alternate path exists
   → Do NOT escalate for: partial failures, minor variations, expected permission prompts
```

### Specific Failure Patterns in This Ecosystem

| Failure | Typical Cause | Safest Alternate | When to Escalate |
|---------|--------------|-----------------|------------------|
| `rg: Bad message (os error 74)` on glob | Corrupted filesystem cache on S: drive mount | Use `find` or `ls` directly via bash | If no file search works at all — filesystem may be degraded |
| `Read` tool returns "file does not exist" | Path is wrong (relative vs absolute, with/without `/mnt/s/`) | Try the other path format. `ls` first to confirm existence. | If file truly doesn't exist and is critical |
| `Edit` fails: "oldString not found" | Content changed since last read, or whitespace mismatch | Re-read the file, confirm current content, adjust oldString | After 2 retries with fresh reads |
| MCP tool times out (>30s) | Network latency, large file, or MCP service busy | Retry once. If second attempt also times out, use bash alternative. | If the failure blocks the critical path and no bash alternative exists |
| Permission prompt ("Allow?") | Filesystem write outside allowed dirs | Do NOT auto-allow. Report the prompt. | Always — operator must decide |
| `venv/bin/python` not found | Running outside venv, or wrong directory | Activate venv first: `source venv/bin/activate` | If venv is corrupted — needs rebuild |
| `pytest` reports fewer/more tests than expected | Test count drift (new tests added, some removed) | Note the new count. Check if difference is expected. | If count dropped significantly (>10) without explanation |
| SSH check fails | Tailnet down, hostname wrong, SSH key issue | Try `ping <host>` first. Check `tailscale status`. | If can't reach headless at all — operator may need to be on-machine |
| S: drive path resolves differently | Windows path `S:\` vs Linux `/mnt/s/` | Always use `/mnt/s/` on headless Linux. Never use `S:\` in bash. | If both conventions fail — drive may not be mounted |
| File empty when expected to have content | Truncated write, or found wrong file | Check file size with `ls -la`. Check if it's a .gitkeep placeholder. | If critical state file is empty and should have content |

### Policy

1. **An agent must never report success when a tool call failed.** Partial success is "partial success," not "success."
2. **An agent must never silently retry more than twice.** After two failures, document and move on.
3. **Permission prompts are operator escalations.** Never auto-accept filesystem permissions.
4. **Stale data is worse than no data.** If a tool call returns data you can't verify as fresh, flag it as potentially stale.
5. **Tool failures must be recorded in output.** A journal entry or heartbeat that doesn't mention the failures it encountered is incomplete.
6. **The standard applies to all agents in all lanes.** It's not KuCoin-specific.

---

### Mission 5: Key Takeaway for Sean

**The most common failure in this ecosystem is path confusion.** Windows paths (`S:\`) vs Linux paths (`/mnt/s/`), absolute vs relative, leading slash vs no leading slash. When an agent reports "file not found," the first thing to check is which path format it tried.

**The second most common is the S: drive's `os error 74` on glob.** This is a known quirk of FUSE filesystem mounts. The fix is to use `find`/`ls` directly via bash instead of the glob tool. If you see this, the answer is not "fix the glob" — it's "use a different tool."

---

## MISSION 6 — MONITORING AND TRANSPARENCY STACK

### LAYER 1: Raw Truth Artifacts

**Purpose:** Immutable records of what actually happened. These are the source of truth — everything else derives from them.

**Examples:**
- `SESSION_STATE.json` — Formal lane state from ExecutionEngine
- `bot_heartbeat_dry_run.json` — Cycle-level heartbeat from ExecutionEngine
- `hourly_snapshots.jsonl` — Append-only time-series of monitoring state
- `systemd journal` — System-level event log
- `git log` — Every mutation tracked
- `agent-logs/kucoin-session-heartbeats.jsonl` — Session-level heartbeats

**What it must never be confused with:** Derived views. A monitoring snapshot summarizes truth; it is not truth. SESSION_STATE.json is truth.

**Freshness expectations:**
- SESSION_STATE: every trading cycle (~1-5 min if running)
- Heartbeat: every cycle
- Hourly snapshots: every hour on the hour
- Git: depends on mutation rate
- Agent heartbeats: every ~10-15 min during a session

**Who owns it:** The producing lane (KuCoin for SESSION_STATE, systemd for journal, etc.)

---

### LAYER 2: Derived Monitoring Views

**Purpose:** Human-readable summaries and trends derived from Layer 1. Make the system observable without reading raw JSON.

**Examples:**
- `latest-monitoring-snapshot.md` — Human-readable summary of SESSION_STATE + heartbeat
- `MONITORING_ANALYSIS_daily*.md` — Trend analysis from hourly snapshots
- `MONITORING_ANALYSIS_weekly*.md` — Weekly trend summary
- `MONITORING_ANALYSIS_monthly*.md` — Monthly trend summary
- Control Plane supervision cards (`docs/supervision/*-status-*.md`)

**What it must never be confused with:** Raw truth. A derived view can be stale even when truth is fresh (e.g., snapshot script failed but bot kept running). Always check Layer 1 timestamps to validate Layer 2 freshness.

**Freshness expectations:**
- Monitoring snapshot: < 2h (hourly timer + small processing delay)
- Daily analysis: < 30h (run once per day)
- Weekly analysis: < 8 days
- Monthly analysis: < 35 days
- Supervision cards: < 1 week (they're human-mediated, not automated)

**Who owns it:** Control Plane (supervision cards), KuCoin lane (monitoring analysis scripts)

---

### LAYER 3: Evidence & Audit Views

**Purpose:** Rigorous classification of findings. Not real-time — durable. Answers "what do we know to be true?"

**Examples:**
- Library truth classifications (confirmed / partially confirmed / inferred / unresolved)
- Provenance checks (who produced what, when, by what authority)
- Contradiction tables (when two sources disagree)
- Block matrices (B1-B7 style)
- Headless/local reconciliation reports

**What it must never be confused with:** Monitoring views. Monitoring says "the bot is running." Evidence says "we confirmed the bot writes SESSION_STATE before every shutdown." One is real-time, the other is a durable claim.

**Freshness expectations:**
- Truth classifications: updated when new evidence arrives or existing evidence is superseded
- Block matrices: updated when a blocker is resolved
- Contradiction tables: updated when contradictions are discovered
- These are not on a timer — they update on events

**Who owns it:** Library

---

### LAYER 4: Research Escalation Views

**Purpose:** Track anomalies that might be significant but aren't yet classified. Prevent observations from inflating into theories without evidence.

**Examples:**
- Research Intake work-orders (numbered, with experiment designs)
- Anomaly tracking records (what was observed, when, under what conditions)
- Cross-session continuity observations
- Persistent unexplained differences between expected and observed behavior

**What it must never be confused with:** Evidence. A research work-order is not a confirmed finding. It's a hypothesis waiting to be tested. Until Library classifies it, it's not truth.

**Freshness expectations:**
- Work-orders: updated when experiments produce results
- No timer — event-driven

**Who owns it:** Research Intake

---

### What Sean Should Keep Open

**Always-visible (check on connection):**
1. `cat /mnt/s/kucoin-lane/lanes/kucoin/inbox/SESSION_STATE.json` — Is the bot alive?
2. `ls /mnt/s/kucoin-lane/docs/automation/latest-monitoring-snapshot.md` — What's the monitoring summary?
3. `ls /mnt/s/WE4FREE-Control-Plane/docs/supervision/ | tail -5` — When were the last supervision cards written?

**Check during a session:**
4. `tail -3 /mnt/s/kucoin-lane/agent-logs/kucoin-session-heartbeats.jsonl` — Are heartbeats flowing?
5. `cat /mnt/s/kucoin-lane/bot_heartbeat_dry_run.json 2>/dev/null` — Latest cycle state

**Check after returning from away:**
6. The "return from being away" report (see below)

### The "Return From Being Away" Report

A standard 4-command report to run after any absence:

```bash
# 1. Lane health
echo "=== SESSION_STATE ==="
cat /mnt/s/kucoin-lane/lanes/kucoin/inbox/SESSION_STATE.json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\")} | Phase: {d.get(\"phase\")} | Final: {d.get(\"final\")} | Timestamp: {d.get(\"timestamp\")}')" \
  || echo "NO SESSION_STATE"

# 2. Monitoring freshness
echo "=== LATEST SNAPSHOT ==="
head -5 /mnt/s/kucoin-lane/docs/automation/latest-monitoring-snapshot.md 2>/dev/null \
  | grep -i -E "timestamp|last.*update|generated" || echo "NO SNAPSHOT"

# 3. Heartbeat cadence
echo "=== RECENT HEARTBEATS ==="
tail -3 /mnt/s/kucoin-lane/agent-logs/kucoin-session-heartbeats.jsonl 2>/dev/null \
  | python3 -c "import sys,json; [print(json.loads(l).get('ts','?')) for l in sys.stdin]" \
  || echo "NO HEARTBEATS"

# 4. Test baseline
echo "=== TEST STATUS ==="
cd /home/we4free/agent/repos/kucoin-lane && \
  venv/bin/pytest tests/ -q 2>&1 | tail -1 || echo "TESTS FAILED"
```

This report should be the first thing you run after `ssh` in. It tells you in ~5 seconds whether the system is healthy, stale, or broken.

---

### Mission 6: Key Takeaway for Sean

**The four-command return report is your most valuable monitoring tool.** It checks all four layers in under 5 seconds. Make it a habit — run it before doing anything else.

**Never confuse layers.** If the monitoring snapshot looks fine but SESSION_STATE is stale, the snapshot is lying by omission. Layer 1 is always the tiebreaker.

---

## MISSION 7 — GAP ANALYSIS

### P0 — Causes Unsafe or Confusing Operation Now

| ID | Gap | Current Symptom | Evidence | Recommended Remedy | Lane Owner |
|----|-----|----------------|----------|-------------------|-----------|
| P0.1 | **KuCoin lane has no systemd service** | Lane won't survive reboot. If headless restarts, KuCoin stays down. | `systemctl --user list-units --type=service` shows 16/16 services for other lanes, 0 for kucoin | Define `kucoin-lane.service` and `kucoin-lane.timer` following existing lane patterns | KuCoin |
| P0.2 | **Circuit breaker classes defined but never wired** | Formal safety layer doesn't execute. `CircuitBreaker`, `PortfolioCircuitBreaker`, `KellyPositionSizer` are dead code. | `grep -r "CircuitBreaker(" src/intelligence/orchestrator.py` returns nothing. Wire map confirms. | Wire PortfolioCircuitBreaker into orchestrator's post-cycle safety path | KuCoin |
| P0.3 | **Auditor violations are warning-only, not hard-blocking** | Governance (ROLES.md:187-189) says audit failure activates circuit breaker. Runtime only logs CRITICAL. | `orchestrator.py:841-853` checks `audit_passed` but does not call `activate_circuit_breaker()` | Add `self.activate_circuit_breaker()` at orchestrator.py:848 when audit fails | KuCoin |
| P0.4 | **No automated freshness contracts** | Timestamps checked manually. No tool warns when SESSION_STATE goes stale during unattended operation. | Current practice relies on Sean remembering to check timestamps | Define timestamp-based freshness contracts for all monitoring artifacts; add a check to the monitoring automation | Control Plane |

### P1 — Major Workflow Drag or Observability Weakness

| ID | Gap | Current Symptom | Evidence | Recommended Remedy | Lane Owner |
|----|-----|----------------|----------|-------------------|-----------|
| P1.1 | **No "return from being away" report** | Sean has to remember which 4-7 files to check after a break. Different each time. | This was identified in Mission 6 as something that should exist but doesn't | Create a single shell script (`~/bin/return-report.sh`) that checks SESSION_STATE, heartbeat, monitoring snapshot, and test baseline in one command | Control Plane |
| P1.2 | **SwarmMind system state report is stale** | Last report: 2026-04-30. That's 18 days stale as of 2026-05-18. | `ls /mnt/s/SwarmMind/docs/system-state/SYSTEM_STATE_REPORT_*.md` shows April date | Refresh system state report, or establish why it's no longer being produced | SwarmMind |
| P1.3 | **Library journal gap not fully resolved** | Supervision card from 2026-05-12 flagged a 3-day journal gap. Status unknown. | `docs/supervision/library-status-2026-05-12.md` identifies the gap | Control Plane should re-check Library journal and close the supervision loop | Control Plane |
| P1.4 | **Archivist inboxes monitored manually** | No automated alerting when inbox backlog grows or items sit in action-required. | Inbox inspection shows items in blocked/expired directories across multiple lanes | Add inbox backlog monitoring to Control Plane's supervision checks | Control Plane / Archivist |
| P1.5 | **No cross-lane health summary** | Sean has to check 5+ locations to understand overall system health. | Mission 1 identifies 5+ health indicators across different surfaces | Produce a single cross-lane health summary page that aggregates all key indicators | Control Plane |
| P1.6 | **KuCoin `circuit_breaker_active` is in-memory only** | Restart resets circuit breaker state. No persistence across crashes. | `orchestrator.py` uses simple boolean, not PortfolioCircuitBreaker class | Wire PortfolioCircuitBreaker (which has persistence) into the orchestrator | KuCoin |
| P1.7 | **Test baseline drift detection is manual** | No alert when test count changes. Currently Sean notices or doesn't. | No automated test count tracking in monitoring pipeline | Add test count + pass rate to the monitoring snapshot | KuCoin / Control Plane |

### P2 — Polish or Future Leverage

| ID | Gap | Current Symptom | Evidence | Recommended Remedy | Lane Owner |
|----|-----|----------------|----------|-------------------|-----------|
| P2.1 | **Windows vs Linux path duality undocumented** | New agents waste time guessing `S:\` vs `/mnt/s/`. | Tool-call failures from path confusion are common (Mission 5) | Document the path convention in AGENTS.md or a shared config | Archivist / Global governance |
| P2.2 | **`asset_configs` hardcoded for 3 pairs** | Adding a new trading pair requires code change. | `src/risk/risk_manager.py:76-92` defines SOL/BTC/ETH only | Make asset configs data-driven (JSON file or env vars) | KuCoin |
| P2.3 | **`sys.path.insert(0,...)` in risk_manager.py** | Fragile import pattern. Works but breaks if directory structure changes. | `src/risk/risk_manager.py:12` | Replace with proper package imports or relative imports | KuCoin |
| P2.4 | **No compactrestore protocol for KuCoin lane** | Session continuity relies on agent memory, not formal protocol. | Noted in Mission 3 restore section | Define compactrestore format and re-verification steps | KuCoin / Research Intake |
| P2.5 | **Research Intake work-order lifecycle not automated** | Work-orders tracked as markdown files. No status transitions (open → in-progress → resolved → closed). | `ls work-orders/` shows 8 numbered items + README + test1.txt | Add status metadata to work-orders (frontmatter or tracking file) | Research Intake |
| P2.6 | **No formal "operator consent" mechanism for cross-lane mutations** | Currently handled by convention (prompt packet includes "may mutate X"). Not enforced. | Mutation boundaries described in Mission 3 are aspirational | Define a lightweight consent format (e.g., required frontmatter field in cross-lane prompts) | Archivist / Global governance |
| P2.7 | **S: drive mount reliability unknown** | If S: drive drops, all cross-lane visibility is lost. No monitoring for this. | No evidence of failure, but also no evidence of resilience testing | Add S: drive mount check to systemd timer or monitoring automation | Control Plane |

### Where the System Works Only Because Sean Remembers the Ritual

| Ritual | What Happens If Forgotten |
|--------|--------------------------|
| Checking SESSION_STATE timestamp | Operate on stale state, make decisions based on old data |
| Running `pytest` before trusting output | Accept claims that can't be verified |
| Checking which lane to task (Phase 3) | Send trading work to Research Intake, or research to KuCoin |
| Adding provenance to prompt packets | Agents guess at boundaries, may mutate wrong things |
| Writing journal entries at session end | Next agent starts from zero context |
| Checking S: drive is mounted | All path-based operations fail silently |
| Remembering `/mnt/s/` not `S:\` | Repeated tool-call failures |

**Remedy:** Each of these rituals should eventually have a tool or automation that enforces or reminds. The "return from being away" report addresses the first two. Provenance templates address the fourth. The others need systematic solutions.

### Where a New Operator Would Likely Break It

| Scenario | Likely Failure | Why |
|----------|---------------|-----|
| First connection to headless | Can't find the repo | Expects it in home dir, doesn't check `/mnt/s/` |
| First cross-lane task | Mutates wrong repo | No clear "go here, not there" guidance on mutation boundaries |
| First "return" after break | Skips timestamp check | Assumes monitoring snapshot = truth, doesn't verify SESSION_STATE |
| First anomaly observation | Inflates it into a theory | Doesn't know about Research Intake's role as skeptic |
| First systemd service creation | Copies wrong pattern | Other lanes' service files exist but conventions vary |
| First live trading consideration | Misses evidence requirements | No checklist for what must be proven before activation |

**Remedy:** This document (HEAD_DEPARTMENT_VERDICT.md) addresses all of these explicitly.

---

### Mission 7: Key Takeaway for Sean

**The P0 gaps (P0.1-P0.4) are the ones that make the system unsafe right now.** The other 18 are important but won't cause a failure on their own.

**The rituals you remember are the system's real safety net.** Every one of them will fail if you're tired, distracted, or interrupted. Automate them.

---

## MISSION 8 — HEAD-DEPARTMENT VERDICT

### 1. Executive Summary

**The WE4FREE ecology is governable and observable enough for sustained work, but fragile in specific ways that must be acknowledged rather than ignored.**

**KuCoin lane is dry-run safe and will be unattended-ready once 4 items are addressed** (wire circuit breaker, harden auditor, add systemd service, automate return report). The monitoring pipeline is well-designed. The formal safety layer doesn't execute — that's the single most important finding.

**Across the ecology, the pattern is the same: the bones are good, the execution gaps are real, and the system relies on Sean remembering rituals that should be automated.** This verdict identifies what to fix, what to accept, and what to watch.

---

### 2. What Was Inspected

| Surface | What Was Checked | Result |
|---------|-----------------|--------|
| **KuCoin Lane** | Full repo: src/ (all modules), tests/ (302 tests), governance/ docs, agent-logs, monitoring artifacts, SESSION_STATE, heartbeat | Comprehensive audit |
| **Archivist** | Inbox/outbox per lane, governance docs, lane-relay conventions | Survey (read-only) |
| **Control Plane** | Supervision cards, reports, docs, agent-logs, headless-observations | Survey |
| **Library** | Lanes/inbox, evidence conventions, supervision card from Control Plane | Survey |
| **SwarmMind** | System state report, lane-info.json, evidence, docs | Survey |
| **Research Intake** | Work-orders, design docs, src | Survey |
| **Kernel-Lane** | Directory structure, artifacts, baselines | Survey |
| **Federation** | Agent context, architecture maps, build summaries | Survey |
| **Global Governance** | COVENANT.md, CONSTITUTION_PRESERVING_RESILIENCE.md, .global/ directory | Survey |
| **S: Drive** | Mount status, lane directory layout, inbox/outbox/state conventions | Verified |

**Not inspected (read-only constraint):** Library journal contents, SwarmMind git history, Archivist git history, Control Plane git history, Research Intake source code details, Federation source code details.

---

### 3. System Map

(See Mission 1 above — operator-focused decision table for all 8 surfaces)

---

### 4. Recommended New Laptop → Full Operations Workflow

(See Mission 2 above — 7-phase workflow from PHASE 0 access to PHASE 7 continuity preservation)

---

### 5. Lane/Plane Responsibility Model

(See Mission 1 above — layering: Governance (Archivist + Control Plane), Evidence (Library), Coordination (SwarmMind + Federation), Operations (Kernel + KuCoin), Research (Research Intake))

---

### 6. Security/Safety Doctrine

(See Mission 3 above — 7 doctrines: secrets, mutation boundaries, drift/stale-state, monitoring integrity, tool-call reliability, trading strictness, restore/compaction)

---

### 7. Monitoring/Transparency Stack

(See Mission 6 above — 4 layers from raw truth through derived views through evidence through research escalation, with the 4-command return report)

---

### 8. Tool-Call Failure Handling Standard

(See Mission 5 above — 6-step decision sequence with ecosystem-specific failure patterns)

---

### 9. End-to-End Workflows

(See Mission 4 above — Workflow A (engineering fix), B (research anomaly), C (operational issue), D (readiness review))

---

### 10. Gap Matrix

(See Mission 7 above — 4 P0, 7 P1, 7 P2 gaps, plus ritual-dependency analysis and new-operator failure scenarios)

---

### 11. Recommended Immediate Changes for Sean's Actual Practice

**Changes to how you operate, not to the repos:**

1. **Run the 4-command return report on every connection.** Before doing anything else. It takes 5 seconds and prevents stale-state blindness.

2. **Add provenance to every prompt packet.** Even short ones. Three lines at the top: who sent it, which lane, what the target is. This trains both the agent and future-you.

3. **Journal at session end.** Two minutes. What was the task, what was done, what's unresolved. The next agent (or you next week) will thank you.

4. **Don't trust "tests pass" without re-running.** If an agent says "tests pass" but your session has been going for hours, the state may have drifted. Re-run before accepting.

5. **Surface contradictions, don't resolve them.** When two sources disagree, write both versions down. The resolution can wait. The contradiction must be documented.

6. **If an agent is stuck, check for permission prompts first.** In this ecosystem, 80% of "stuck" agents are waiting for a filesystem approval they can't auto-accept.

---

### 12. Recommended Changes for the Repos/Planes

**Separated from operator habit changes — these are code/system changes:**

| Change | Lane | Why Now | Effort | Risk |
|--------|------|---------|--------|------|
| Wire PortfolioCircuitBreaker into orchestrator | KuCoin | P0.2 — safety layer doesn't execute | ~20 lines | Low (additive, changes no existing behavior) |
| Wire auditor → circuit breaker activation | KuCoin | P0.3 — governance gap | 1 line | Low (additive) |
| Define kucoin-lane systemd service | KuCoin | P0.1 — won't survive reboot | ~30 lines following existing patterns | Low |
| Add SESSION_STATE freshness check to monitoring | KuCoin / Control Plane | P0.4 — unattended safety | ~15 lines | Low |
| Create return-report.sh | Control Plane | P1.1 — reduce ritual burden | ~20 lines | Low |
| Refresh SwarmMind system state | SwarmMind | P1.2 — stale coordination baseline | 1 session | Medium (depends on SwarmMind availability) |
| Re-check Library journal gap | Control Plane | P1.3 — close supervision loop | 1 read-only check | None |
| Add test count to monitoring snapshot | KuCoin / Control Plane | P1.7 — drift detection | ~10 lines | Low |
| Make asset_configs data-driven | KuCoin | P2.2 — extensibility | ~30 lines | Low (additive) |
| Fix sys.path.insert(0) in risk_manager.py | KuCoin | P2.3 — fragile import | 1 line | Low |
| Add status metadata to Research Intake work-orders | Research Intake | P2.5 — lifecycle tracking | ~30 min | Low |
| Document Windows/Linux path convention | Global / Archivist | P2.1 — reduce agent confusion | 1 doc | None |

---

### 13. What Should Be Assigned Next

| Surface | Assignment | Why |
|---------|-----------|-----|
| **Archivist** | Verify lane-relay contracts for all lanes. Confirm inbox/outbox routing between every pair of lanes that should communicate. | The inbox/outbox fabric is the nervous system. If it's miswired, no cross-lane coordination works. |
| **Library** | Classify the 7 gaps from Mission 7's readiness findings (auditor mismatch, dead code, contract, monitoring map, B1-B7). Determine which are confirmed and which need more evidence. | These findings are currently KuCoin-local. Library should make them durable evidence. |
| **Control Plane** | Create the return-report.sh script and the cross-lane health summary page. Re-check Library journal gap. | These are the highest-leverage operator UX improvements. |
| **Research Intake** | Take the auditor-governance mismatch as a candidate cross-lane pattern. Determine whether other lanes have the same auditor-warning-only behavior. | If this pattern is systemic, it's a P0 architecture issue, not a KuCoin bug. |
| **KuCoin** | Wire circuit breaker (B2), fix auditor (B3), add systemd service (B1). In that order. | These are the P0 gaps. Circuit breaker first because it's the safety layer. Auditor second because it's the detection layer. Systemd last because it only matters if the other two work. |

---

### 14. Ecosystem Assessment

| Dimension | Verdict | Evidence |
|-----------|---------|----------|
| **Governable enough for sustained work?** | **Yes** | Governance docs exist (ROLES.md, lane-relay.json, COVENANT.md, global governance). Mutation boundaries are understood. Inbox/outbox relay convention is established. The gaps are in enforcement, not structure. |
| **Observable enough for sustained work?** | **Partially** | Monitoring pipeline (SESSION_STATE → snapshots → analysis) is well-designed. But there's no cross-lane health summary, no automated freshness contracts, and the "return from being away" ritual is manual. You can see any one lane clearly, but you can't see all of them at once. |
| **Fragile in specific ways?** | **Yes** | 1) Relies on Sean remembering rituals (no automation for 4+ critical checks). 2) Safety layer defined but not wired (circuit breaker, auditor enforcement). 3) Cross-lane visibility is manual (5+ separate locations to check). 4) S: drive mount is single point of failure for all cross-lane operations. 5) Stale state (SwarmMind system report, potential Library journal gap) can propagate without detection. |

---

### 15. Exact Document Files Created/Updated

**Files created in this session:**

| File | Location | Purpose |
|------|----------|---------|
| `HEAD_DEPARTMENT_VERDICT.md` | `S:/kucoin-lane/docs/` | Full 8-mission verdict (this document) |
| `journal/2026-05-18_headless_readiness_pass.md` | `S:/kucoin-lane/` | Session journal with completed work, files read, next steps |
| `memory/README.md` | `S:/kucoin-lane/` | Memory bank conventions |
| `memory/key-findings.md` | `S:/kucoin-lane/` | Accumulated truths from readiness pass |
| `memory/blocker-matrix.md` | `S:/kucoin-lane/` | B1-B7 with severities |
| `memory/wire-map.md` | `S:/kucoin-lane/` | What's wired into runtime vs dead code |
| `agent-logs/latest-kucoin-session.md` | `kucoin-lane/` (repo root) | Full readiness pass report (predates kucoinheadless.txt load) |
| `agent-logs/kucoin-session-heartbeats.jsonl` | `kucoin-lane/` (repo root) | 5 heartbeat entries across session |

**No files were mutated outside `kucoin-lane` or `S:/kucoin-lane/`.**

---

### 16. Verification Performed

| Check | Result |
|-------|--------|
| `venv/bin/pytest tests/ -q` | 302 passed (verified multiple times) |
| `venv/bin/python -m py_compile src/monitoring/auditor.py` | OK |
| `venv/bin/python -m py_compile src/risk/risk_manager.py` | OK |
| `venv/bin/python -m py_compile src/intelligence/orchestrator.py` | OK |
| `venv/bin/python -c "from src.monitoring.auditor import AuditorAgent; print('ok')"` | OK |
| All 3 dead-code risk classes import OK | Verified |
| SESSION_STATE write path verified | Confirmed coherent |
| lane-relay.json contract verified | Path matches |
| S: drive mount verified | Accessible at `/mnt/s/` |
| Control Plane systemd status | 16/16 services for other lanes, 0 for kucoin |
| KuCoin working tree | Dirty with partial (wrong-API) circuit breaker wiring attempts |

---

### 17. Open Uncertainties

| Uncertainty | Why It Matters | How to Resolve |
|-------------|---------------|----------------|
| Whether CircuitBreaker/KellyPositionSizer were ever wired and disconnected | Affects whether re-wiring is restoration or new integration | Git archaeology (Control Plane did partial — confirmed never wired from inception) |
| Whether the auditor-governance mismatch exists in other lanes | If systemic, it's an architecture pattern, not a KuCoin bug | Research Intake investigation |
| Whether SwarmMind system state is intentionally not being updated or just forgotten | Affects whether coordination layer is degraded | Control Plane check |
| Whether Library journal gap was resolved | Affects Library's reliability as evidence layer | Control Plane re-check |
| What the partial circuit breaker wiring in working tree was attempting | Uncommitted changes call wrong API methods (`is_triggered()` instead of `check_circuit()`/`check()`) | Review dirty tree, decide to keep or discard |
| Whether S: drive mount is reliable under load | If it drops during unattended operation, all cross-lane monitoring fails | Add mount check to monitoring automation |
| Whether any other lane has stale artifacts that look fresh | The same stale-state hazard applies everywhere | Apply the timestamp-checking discipline from Mission 3 across all lanes |

---

### Final Verdict

The WE4FREE ecology is **worth operating carefully**. The architecture is sound, the governance framework exists, the monitoring pipeline is well-designed, and the gaps are bounded and fixable.

**The system will not surprise-fail if you check timestamps and verify before trusting.** But it will quietly degrade if you don't.

**KuCoin lane specifically:** Dry-run safe now. Ready for unattended dry-run after 4 focused changes (wire CB, harden auditor, systemd service, return report). Not ready for live trading and should not be discussed until at least 7 consecutive days of unattended dry-run without safety violations.

**The headless operation model works.** The infrastructure supports it. The monitoring supports it. The gaps are in ritual automation and enforcement, not in fundamental architecture.

---

*This is the completed HEAD DEPARTMENT VERDICT for the 2026-05-18 KuCoin headless session. All 8 missions addressed. Ready for handoff.*
