# KuCoin-Lane AWS Architecture

> OUTPUT_PROVENANCE:
> agent: kilo
> lane: kucoin
> target: aws-architecture
> generated_at: 2026-05-16T06:15:00Z
> session_id: ws3a

## OBSERVABILITY_DOMAIN
infrastructure-architecture

## NEXT_SAFE_ACTION
Deploy kucoin-lane.service to Ubuntu headless, then evaluate EC2 migration

---

## 1. Current Deployment Model

KuCoin-Lane runs as a Docker container on the Ubuntu headless rig (`root@100.95.40.99`), integrated into the existing 4-daemon×N-lane systemd architecture.

```
┌─────────────────────────────────────────────┐
│           Ubuntu Headless (100.95.40.99)    │
│                                             │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ systemd      │  │ Docker               │  │
│  │ we4free-*    │  │ kucoin-lane          │  │
│  │ @kucoin      │  │ (docker-compose)     │  │
│  └─────────────┘  └──────────────────────┘  │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ Lane-relay filesystem               │    │
│  │ /home/we4free/agent/repos/          │    │
│  │ └── kucoin-lane/lanes/kucoin/       │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
         │
         │ SSHFS/CIFS mount
         ▼
┌─────────────────────────────────────────────┐
│           Windows Desktop (S:\)             │
│  S:\kucoin-lane\  ← local worktree          │
│  S:\Archivist-Agent\lanes\kucoin\  ← relay  │
└─────────────────────────────────────────────┘
```

## 2. Systemd Integration (4 daemons × kucoin lane)

KuCoin-Lane gets the same 4-daemon template as all other lanes:

| Daemon | Service | Purpose |
|--------|---------|--------|
| heartbeat | `we4free-heartbeat@kucoin.service` | Periodic heartbeat emission |
| lane-worker | `we4free-lane-worker@kucoin.service` | Inbox processing |
| relay-daemon | `we4free-relay-daemon@kucoin.service` | Inter-lane message relay |
| autonomous-executor | `we4free-autonomous-executor@kucoin.service` | Self-directed task execution |

### Lane-to-Repo Mapping Addition

Add to `/usr/local/bin/we4free-lane-daemon`:

```bash
kucoin)
    REPO_DIR="/home/we4free/agent/repos/kucoin-lane"
    ;;
```

### Deployment Steps

1. Clone repo to headless: `git clone https://github.com/vortsghost2025/kucoin-lane /home/we4free/agent/repos/kucoin-lane`
2. Add `kucoin)` case to `we4free-lane-daemon` script
3. Enable services: `systemctl enable we4free-heartbeat@kucoin we4free-lane-worker@kucoin we4free-relay-daemon@kucoin we4free-autonomous-executor@kucoin`
4. Start services: `systemctl start we4free-heartbeat@kucoin we4free-lane-worker@kucoin we4free-relay-daemon@kucoin we4free-autonomous-executor@kucoin`
5. Verify: `lane-ctl.sh list | grep kucoin`

## 3. Docker Deployment

The `docker-compose.yml` in kucoin-lane provides:

- Python 3.11-slim container
- Healthcheck on `/health`
- Volume mounts: `./data`, `./lanes`, `./config/.env`
- Restart policy: `unless-stopped`
- Resource limits: 512MB RAM, 1 CPU core

### Production Docker Compose Override

```yaml
# docker-compose.prod.yml
services:
  kucoin-lane:
    environment:
      - KUCOIN_EXECUTION_MODE=live
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '2'
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
```

## 4. AWS Migration Path (Future)

If/when the trading bot needs cloud hosting for uptime guarantees:

### Option A: EC2 (Simplest)

```
┌────────────────────────────────────────────┐
│  AWS Account                               │
│  ┌──────────────────────────────────────┐  │
│  │  VPC: 10.0.0.0/16                    │  │
│  │  ┌────────────────────────────────┐  │  │
│  │  │  Private Subnet: 10.0.1.0/24   │  │  │
│  │  │  ┌──────────────────────────┐  │  │  │
│  │  │  │  EC2 t3.medium           │  │  │  │
│  │  │  │  (Ubuntu 24.04)          │  │  │  │
│  │  │  │  - Docker                │  │  │  │
│  │  │  │  - kucoin-lane container │  │  │  │
│  │  │  │  - systemd daemons       │  │  │  │
│  │  │  └──────────────────────────┘  │  │  │
│  │  └────────────────────────────────┘  │  │
│  └──────────────────────────────────────┘  │
│                                            │
│  ┌──────────────┐  ┌───────────────────┐  │
│  │ SSM Param    │  │ CloudWatch        │  │
│  │ Store        │  │ Logs + Alarms     │  │
│  │ (API keys)   │  │ (heartbeat)       │  │
│  └──────────────┘  └───────────────────┘  │
└────────────────────────────────────────────┘
```

**Components:**
- **EC2 t3.medium** — sufficient for single trading pair, Python workload
- **SSM Parameter Store** — API credentials (replaces .env file)
- **CloudWatch Logs** — structured JSON log ingestion
- **CloudWatch Alarms** — heartbeat stale > 5min → SNS alert
- **No NAT Gateway** — outbound-only (API calls to exchanges); use public subnet with security group

### Option B: ECS Fargate (Serverless)

More complex but removes EC2 management:

- ECS Task Definition with kucoin-lane Docker image (ECR)
- Fargate launch type, 0.5vCPU / 1GB
- SSM Parameter Store for secrets
- CloudWatch Logs via awslogs driver
- Application Auto Scaling not needed (single bot instance)

### Option C: Keep On-Prem (Current)

The Ubuntu headless rig already provides:
- Always-on uptime (systemd auto-restart)
- Lane-relay integration (filesystem-based)
- SSH access from Windows desktop
- Docker isolation

**Recommendation:** Stay on-prem until uptime requirements exceed headless reliability. The 4-daemon systemd architecture already provides self-healing. Migrate to AWS only if:
- Headless rig experiences >1hr/month downtime
- Regulatory requirements demand cloud audit trails
- Multi-region redundancy is needed

## 5. Secret Management

### Current (On-Prem)
- `.env` file on headless rig (owned by `we4free` user, mode 600)
- `.env.example` in repo (no real values)

### AWS Migration (Future)
- SSM Parameter Store `/kucoin-lane/api-key`, `/kucoin-lane/api-secret`, `/kucoin-lane/api-passphrase`
- KMS key for encryption at rest
- IAM role on EC2 instance profile with `ssm:GetParameter` permission
- No hardcoded credentials in code or container env

## 6. Monitoring Integration

### On-Prem
- systemd journal logs (journald)
- JSONL event log files in `data/events/`
- Control-Plane `cp-headless-status.sh` includes kucoin lane
- Heartbeat file: `lanes/kucoin/state/heartbeat.json`

### AWS Migration (Future)
- CloudWatch Log Group: `/kucoin-lane/events`
- CloudWatch Metric Filter: HALT/FLAT events → alarm
- CloudWatch Alarm: no heartbeat for 5 minutes → SNS → operator
- X-Ray tracing optional (low priority for trading bot)

## 7. Backup and Recovery

### On-Prem
- Git repo = state recovery (checkpoint_manager.py persists to `data/checkpoints/`)
- Docker volume `./data` = persistent state
- Daily git auto-commit of checkpoint files

### AWS Migration (Future)
- EBS snapshot daily (automated via Lifecycle Manager)
- S3 checkpoint backup (sync from container)
- RDS not needed (no SQL database)

## 8. Network Security

### On-Prem
- Outbound-only: KuCoin API + Binance WebSocket + CoinGecko + Telegram API
- No inbound ports from internet
- SSH access via Tailscale/ZeroTier only

### AWS Migration (Future)
- Security Group: deny all inbound, allow outbound 443
- No public IP needed (use SSM Session Manager for SSH)
- VPC Endpoint for SSM (if private subnet)
- WAF not applicable (no HTTP server)

---

_This document covers both current on-prem deployment and future AWS migration options. No AWS resources should be provisioned until the on-prem deployment is validated and uptime requirements justify cloud hosting._
