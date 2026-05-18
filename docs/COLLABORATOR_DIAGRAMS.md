# KuCoin Lane — Collaborator Diagram Packet

**Audience:** Senior IT/security developer joining the project
**Purpose:** Orient quickly — system architecture, safety gates, collaboration workflow, deployment reality
**Date:** 2026-05-16

This packet separates intended bot architecture, planned development workflow, and current deployment reality. Diagrams 1 and 2 are the core orientation diagrams. Diagram 3 is included to keep implemented state distinct from target state.

> **⚠ CURRENT DEPLOYMENT REALITY (as of 2026-05-16):**
> KuCoin Lane is **NOT running in production**. Phase D (static validation) ✅, Phase F (dry-run startup) ✅ — one controlled cycle executed and verified on both Windows and headless. The bot is in `COLD_START` / `dry_run` mode on the headless machine — no live trading, no exchange API calls, no systemd services, no Docker containers. SESSION_STATE.json emitted at `lanes/kucoin/inbox/` with correct `status=shutdown`, `phase=terminating`, `final=true`, `cycle_count=1`.
>
> **What IS running on headless (100.95.40.99):** 4 monitoring lanes — **archivist, kernel, library, swarmmind** — each with 4 systemd daemons (heartbeat, lane-worker, relay-daemon, autonomous-executor). These lanes monitor the kucoin lane's state directory and heartbeat.
>
> Diagrams 1-2 below show the **INTENDED architecture**. Diagram 3 shows the **current live deployment reality**.

---

## Diagram 1: Runtime Trading Workflow — INTENDED Architecture

```mermaid
flowchart TB
    subgraph External["External / Market Data<br/><span style='font-size:0.8em'>⚠ Aspirational — no exchange connectivity</span>"]
        KF["KuCoin Feed<br/>(price, orderbook, ticker)"]
        CG["CoinGecko API<br/>(sentiment, macro)"]
        BW["Binance WebSocket<br/>(cross-exchange lead)"]
    end

    subgraph Intelligence["Intelligence / Signal Agents"]
        RD["RegimeDetector<br/>ADX + ATR → regime<br/>CRISIS/RANGING/TRENDING"]
        LL["LeadLagMonitor<br/>Binance→KuCoin spread<br/>→ DANGER signal"]
        WW["WhaleWatch<br/>CVD + order flow<br/>→ absorption/distribution"]
        MA["MarketAnalyzer<br/>RSI, volatility, entry<br/>timing validation"]
    end

    subgraph Orchestrator["Orchestrator"]
        IO["IntelligenceOrchestrator<br/>• Aggregates all signals<br/>• Decides LONG/SHORT/FLAT<br/>• Confidence score<br/>• Regime guard (v0–v4)<br/>• SNOEPILE freeze/thaw"]
    end

    subgraph RiskManager["Risk Manager — Absolute Veto"]
        RM["RiskManagementAgent<br/>• Pre-trade validation<br/>• Position sizing<br/>• Stop-loss/take-profit<br/>• Daily loss cap check<br/>• Notional minimum check"]
        CB["CircuitBreaker<br/>PnL window tracking"]
        PCB["PortfolioCircuitBreaker<br/>Drawdown from peak"]
        KC["KellyCriterion<br/>Quarter-Kelly sizing cap"]
    end

    subgraph Executor["Executor"]
        DE["DryRunExecutor<br/>• Cached OHLCV only<br/>• No exchange calls<br/>• Paper positions"]
        LE["LiveExecutor<br/>• KuCoin API via adapter<br/>• Real order placement<br/>• Stop-loss/take-profit orders<br/>• Margin trading"]
    end

    subgraph Exchange["KuCoin Exchange Boundary<br/><span style='font-size:0.8em'>⚠ Not connected — COLD_START</span>"]
        KA["KuCoinAdapter<br/>Auth / rate-limit / symbol format"]
        API["KuCoin REST API"]
    end

    subgraph MonitorAudit["Verification Layer"]
        MON["MonitoringAgent<br/>• JSONL event logs<br/>• Telegram alerts<br/>• Heartbeat writer"]
        AUD["AuditorAgent<br/>• Post-cycle safety audit<br/>• Re-validates all 4 safety layers<br/>• Reports violations"]
    end

    subgraph Persistence["State Persistence"]
        CP["CheckpointManager<br/>• Pickle serialization<br/>• SIGTERM auto-save<br/>• Atomic writes"]
        HB["bot_heartbeat.json<br/>written every 10s"]
        SS["SESSION_STATE.json<br/>declared per-cycle write<br/>(being completed)"]
    end

    subgraph Relay["Lane Relay → Archivist / Control Plane"]
        INBOX["inbox/<br/>heartbeat + messages"]
        OUTBOX["outbox/<br/>phenotype-summary<br/>alerts + escalation"]
        ARCH["Archivist-Agent<br/>constitutional governance<br/>checkpoint verification<br/>human escalation"]
    end

    KF --> RD
    KF --> LL
    KF --> WW
    CG --> MA
    BW --> LL

    RD --> IO
    LL --> IO
    WW --> IO
    MA --> IO

    IO -->|"LONG/SHORT/FLAT<br/>confidence, size"| RM
    RM -->|"APPROVED / REJECTED / REDUCED<br/>SL, TP, Kelly size"| IO

    RM --> CB
    RM --> PCB
    RM --> KC

    IO -->|"risk-cleared decision"| DE
    IO -->|"risk-cleared decision"| LE

    DE --> CP
    LE --> KA
    KA --> API

    LE --> MON
    DE --> MON
    IO --> MON
    RM --> MON

    MON --> AUD
    AUD -->|"violations →"| IO

    IO --> CP
    DE --> CP
    LE --> CP
    RM --> CP

    CP -->|"state_hash integrity"| SS
    CP --> HB

    MON -->|"alerts + heartbeats"| OUTBOX
    AUD -->|"audit failures"| OUTBOX
    RM -->|"circuit breaker HALT"| OUTBOX

    INBOX -->|"human override"| IO
    INBOX -->|"reset circuit breaker"| RM

    OUTBOX --> ARCH

    ARCH -.->|"P0 telegram<br/>code red: human"| HUMAN((Operator))

    style HUMAN fill:#f44,color:#fff,stroke:#c00
    style RM fill:#f80,color:#fff,stroke:#d60
    style CB fill:#f80,color:#fff,stroke:#d60
    style PCB fill:#f80,color:#fff,stroke:#d60
    style IO fill:#08f,color:#fff,stroke:#06d
    style LE fill:#f44,color:#fff,stroke:#c00
    style DE fill:#4a4,color:#fff,stroke:#282
    style AUD fill:#aa0,color:#fff,stroke:#880
    style OUTBOX fill:#66d,color:#fff,stroke:#44b
    style SS fill:#888,color:#fff,stroke:#666
```

**Caption (INTENDED):** The KuCoin Lane operates as a 4-role autonomous trading ensemble within a single process. External market data feeds intelligence agents (RegimeDetector, LeadLagMonitor, WhaleWatch, MarketAnalyzer) that pass signals to the Orchestrator. The Orchestrator decides trade direction with a confidence score, then submits to the RiskManager which has absolute veto — it can APPROVE, REJECT, or REDUCE every trade. If cleared, the Executor handles placement through either DryRun (paper, no API calls) or Live (real KuCoin orders) mode. Every cycle is logged by the MonitoringAgent and audited by the AuditorAgent for safety-layer correctness. CheckpointManager persists state on every cycle with hash-verified integrity. All alerts, escalations, and heartbeats flow through lane-relay (filesystem mount) to the Archivist-Agent, which escalates to human for P0 events like circuit breaker HALT. **Formerly known gap — CLOSED:** SESSION_STATE.json per-cycle writer was declared required; now implemented with `phase` and `final` fields, verified 302/302 tests green on Windows + headless. **Reality: This architecture is NOT live — kucoin bot is in COLD_START/dry_run, phases E+F queued, no exchange connectivity.**

---

## Diagram 2: Development and Review Workflow

```mermaid
flowchart LR
    subgraph HumanGovernance["Human Governance"]
        SEAN["Sean (Operator)<br/>• Sets direction & constraints<br/>• Defines acceptance bar<br/>• Reviews architecture<br/>• Authorizes live trading"]
        COLLAB["Senior Collaborator<br/>• Security & architecture review<br/>• Hardening review<br/>• Deployment-readiness input"]
    end

    subgraph AgentLayer["Agent Layer (kilo/z-ai)"]
        AGENT["Coding Agent<br/>• Implements bounded tasks<br/>• Works within standing auth<br/>• Generates evidence + journal<br/>• Does NOT place live orders"]
    end

    subgraph CIQA["Validation Pipeline"]
        STATIC["Static Checks<br/>• TypeScript/Python typecheck<br/>• Linting"]
        TESTS["Unit Tests<br/>• 20+ test files<br/>• Dry-run validation<br/>• Phase D/E/F gates"]
        GOV["Governance Checks<br/>• OUTPUT_PROVENANCE<br/>• AGENTS.md compliance<br/>• Authorization scope verified"]
    end

    subgraph Staging["Staging / Dry Run"]
        LOCAL["Local Desktop (S:\)<br/>• Git worktree<br/>• Code edit + commit"]
        DRYRUN["DryRun Mode<br/>• Cached data only<br/>• No exchange calls<br/>• Paper position tracking"]
    end

    subgraph Production["Production (Headless Ubuntu) — INTENDED"]
        DOCKER["Docker Container<br/>docker-compose up"]
        SYSTEMD["systemd Daemons<br/>4 services × kucoin lane"]
        LIVE["LiveExecutor Mode<br/>Real KuCoin orders<br/>Risk-managed"]
    end

    subgraph CurrentDeploy["Current Live Deployment<br/>Headless 100.95.40.99"]
        MON4["4 Monitoring Lanes<br/>archivist | kernel | library | swarmmind<br/>← ACTIVE — each with 4 systemd daemons"]
        KUCOIN_REPO["kucoin-lane repo<br/>cloned, NOT running<br/>Phase D ✓ | Phase E ✓ | Phase F ✓"]
        ARCH_STATE["Archivist lanes/kucoin/state/<br/>heartbeat = COLD_START / dry_run<br/>inbox/outbox empty (.gitkeep)"]
        OLLAMA["ollama<br/>port 11434 (Tailscale only)"]
        TAILSCALE["tailscaled"]
    end

    subgraph Observe["Observe + Refine"]
        MON["Monitoring<br/>• Heartbeat files<br/>• JSONL event logs<br/>• Telegram alerts"]
        LOG["Journal<br/>• Work journal (JOURNAL.md)<br/>• Session log<br/>• Decision gates"]
        FAIL["Failure Capture<br/>→ Constraint refinement<br/>→ Safety rule hardening<br/>→ Pattern in Papers"]
    end

    SEAN -->|"direction, intent,<br/>constraints, acceptance"| AGENT
    COLLAB -->|"security review,<br/>architecture review"| SEAN

    AGENT -->|"code + tests +<br/>evidence artifact"| STATIC
    STATIC --> TESTS
    TESTS --> GOV
    GOV -->|"all pass"| AGENT
    GOV -->|"fail"| AGENT

    AGENT -->|"commit & push"| LOCAL
    LOCAL --> DRYRUN

    DRYRUN -->|"validated"| COLLAB
    
    COLLAB -->|"approved"| SEAN
    SEAN -->|"go live<br/>⚠ NOT YET AUTHORIZED"| DOCKER
    
    DOCKER --> SYSTEMD
    SYSTEMD --> LIVE

    KUCOIN_REPO -.->|"monitored by"| MON4
    ARCH_STATE -.->|"observed by"| MON4
    OLLAMA --> MON4

    LIVE --> MON
    LOCAL --> MON
    DRYRUN --> MON

    MON -->|"alerts, drift,<br/>failure patterns"| FAIL
    FAIL --> SEAN

    SEAN -->|"refined constraints,<br/>new safety rules"| AGENT

    style SEAN fill:#08f,color:#fff,stroke:#06d
    style COLLAB fill:#a4f,color:#fff,stroke:#82d
    style AGENT fill:#4a4,color:#fff,stroke:#282
    style GOV fill:#aa0,color:#fff,stroke:#880
    style LIVE fill:#f44,color:#fff,stroke:#c00
    style DRYRUN fill:#4a4,color:#fff,stroke:#282
    style FAIL fill:#f80,color:#fff,stroke:#d60
    style CurrentDeploy fill:#444,color:#fff,stroke:#666,stroke-dasharray: 5 5
    style MON4 fill:#4a4,color:#fff,stroke:#282
    style KUCOIN_REPO fill:#a80,color:#fff,stroke:#860
```

**Caption:** Development follows a human-governed, agent-assisted loop. Sean sets direction and constraints; coding agents implement bounded tasks within standing authorization (non-destructive only, no live trading without explicit approval). Every change passes through validation pipeline (typecheck, tests, governance compliance), then dry-run locally before reaching the collaborator for security/architecture review. Only after collaborator sign-off and Sean's explicit go-live does code reach the headless Ubuntu production environment with LiveExecutor. All production behavior is monitored, journaled, and fed back into constraint refinement — this is the "failure → detection → correction → constraint hardening" loop documented in Sean's Papers. **Current reality:** The "Production (Headless Ubuntu)" block is aspirational. What IS running on headless are 4 monitoring lanes (archivist/kernel/library/swarmmind) with 16 systemd daemons and ollama. The kucoin repo is cloned but idle (Phase D done, E+F queued). **Key distinction:** This is not "Sean asks random AIs to edit a trading bot." It is a governed, verified, multi-gate development pipeline with explicit human authorization at every risk-relevant boundary — and the kucoin bot hasn't yet passed through all its gates to reach production.

---

## Diagram 3: Current Live Deployment — Headless (100.95.40.99)

```mermaid
flowchart TB
    subgraph Headless["Headless Ubuntu — Active Infrastructure"]
        subgraph Lanes["4 Monitoring Lanes (each: 4 systemd daemons)"]
            AR["archivist<br/>• constitutional governance<br/>• checkpoint verification<br/>• session registry<br/>• escalation handler"]
            KE["kernel<br/>• optimization artifacts<br/>• benchmark reports"]
            LI["library<br/>• knowledge retrieval<br/>• pattern search"]
            SW["swarmmind<br/>• multi-agent coordination<br/>• task routing"]
        end

        subgraph Services["Support Services"]
            OLL["ollama (port 11434)<br/>Tailscale-only"]
            TS["tailscaled"]
        end

        subgraph KucoinState["kucoin-lane — NOT RUNNING"]
            REPO["Repo cloned at<br/>agent/repos/kucoin-lane/"]
            PHASE["Phase Progression<br/>D (static validation) ✅<br/>E (unit tests) ✅<br/>F (dry-run startup) ✅<br/>SESSION_STATE artifact verified"]
            HB["Archivist lanes/kucoin/state/<br/>heartbeat.json<br/>status=COLD_START<br/>execution_mode=dry_run<br/>cycle_count=0"]
            RELAY["inbox/outbox/state dirs<br/>exist but empty<br/>(only .gitkeep)"]
        end
    end

    subgraph WindowsDev["Windows Desktop (S:\\) — Active"]
        LD["Lattice Deck<br/>Next.js observability<br/>dashboard"]
        REPOS["Code repos + worktrees"]
        CP["Control Panel scripts<br/>cp-headless-status.sh"]
    end

    subgraph External["GitHub Remote"]
        GH["we4free/kucoin-lane"]
    end

    AR <-->|"peer relay"| KE
    AR <-->|"peer relay"| LI
    AR <-->|"peer relay"| SW
    KE <-->|"peer relay"| LI
    KE <-->|"peer relay"| SW
    LI <-->|"peer relay"| SW

    AR -->|"monitors →"| HB
    KE -->|"monitors →"| PHASE
    LI -->|"indexes patterns"| REPO
    SW -->|"task coordination"| AR

    OLL -->|"embeddings / LLM"| LI
    TS -->|"connectivity"| AR

    REPO --> PHASE
    PHASE --> HB
    HB --> RELAY

    REPOS -->|"git push"| GH
    GH -->|"git pull"| REPO

    LD -.->|"reads state"| AR
    LD -.->|"reads state"| HB
    CP -.->|"via SSH"| Headless

    style AR fill:#08f,color:#fff,stroke:#06d
    style KE fill:#4a4,color:#fff,stroke:#282
    style LI fill:#a4f,color:#fff,stroke:#82d
    style SW fill:#f80,color:#fff,stroke:#d60
    style KucoinState fill:#a80,color:#fff,stroke:#860
    style PHASE fill:#a80,color:#fff,stroke:#860
    style HB fill:#aa0,color:#fff,stroke:#880
    style REPO fill:#888,color:#fff,stroke:#666
    style LD fill:#08f,color:#fff,stroke:#06d
    style OLL fill:#4a4,color:#fff,stroke:#282
```

**Caption:** This is the actual production topology as of 2026-05-16. The 4 monitoring lanes (archivist, kernel, library, swarmmind) are the active infrastructure — each is a systemd service ensemble with heartbeat, lane-worker, relay-daemon, and autonomous-executor daemons. They communicate peer-to-peer via lane-relay filesystem mounts and monitor the kucoin lane's state directory. The kucoin lane itself is present (repo cloned, phase tracker at D ✅) but **not executing**: its heartbeat reads `COLD_START` / `dry_run`, cycle_count=0, and relay inbox/outbox/state directories are empty (only .gitkeep files). ollama runs on port 11434 (Tailscale-only) providing embeddings/LLM for the library lane. The Lattice Deck (Next.js observability dashboard) and control panel scripts live on the Windows desktop only — not deployed on headless.

**Key insight for collaborators:** When you join, the 4-lane monitoring mesh is the live system you should understand first. The kucoin trading bot is the *next* lane to go live, once Phases E+F pass and Sean authorizes the transition from COLD_START.

---

## What These Diagrams Tell a Collaborator in 30 Seconds

1. **The bot is a 4-role ensemble** — Orchestrator (decides) → RiskManager (vetoes) → Executor (acts) → Auditor (verifies). No single agent touches both decision-making and the exchange. **But: this architecture is NOT yet live.**
2. **Safety is structural, not aspirational** — RiskManager has absolute veto, circuit breakers are independent, auditor re-validates after every cycle, and human escalation is wired for P0 events.
3. **Development is governed, not wild** — Agents implement bounded tasks within explicit authorization. Every path to production passes through tests, governance checks, dry-run validation, collaborator review, and Sean's explicit go-live signal.
4. **Paper F is real** — The system actually does "failure → detection → correction → constraint refinement." It's not theoretical. The journal, heartbeat monitoring, alert pipeline, and lane-relay are live.
5. **What IS live: 4 monitoring lanes** — Archivist, kernel, library, and swarmmind are running on headless with 16 systemd daemons. They form a peer-relay mesh that monitors the kucoin lane's state. KuCoin bot is in COLD_START, Phase D ✅, E ✅, F ✅, SESSION_STATE artifact verified.

## Questions Collaborators Should Ask

1. **Phases D ✅ E ✅ F ✅ are complete.** What is the next gate before sustained dry-run (Phase G)? Should the session state artifact path be registered in the monitoring lanes' heartbeat consumer?
2. **The 4 monitoring lanes are live.** Should we evaluate their health and reliability before adding kucoin to the production mesh?
3. **The risk layer uses hardcoded asset configs** (BTC/ETH/SOL/USDT) in `risk_manager.py`. Should these be externalized before live trading?
4. **Auditor does not halt trading on failure** — only flags. Is this the right tradeoff, or should audit failure block the next cycle?
5. **ollama is running but not yet integrated** with the library lane for embeddings. Is this a dependency for kucoin lane operations?
6. **Lattice Deck (Next.js dashboard)** exists on Windows only. Should it be deployed on headless before kucoin goes live?
7. **~~CLOSED~~ SESSION_STATE.json per-cycle writer** — implemented with `phase`/`final` fields, 302/302 tests green on both platforms.

---

OUTPUT_PROVENANCE:
  agent: kilo
  lane: kucoin
  generated_at: 2026-05-16T15:48:00-04:00
  session_id: we4free-lattice-deck-2026-05-16-v2
  target: collaborator-orientation-diagrams
