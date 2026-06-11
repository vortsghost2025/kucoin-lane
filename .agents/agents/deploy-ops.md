---
name: deploy-ops
description: Deployment & Operations — Systemd, Docker, CI/CD, secrets, production deployment
version: 1.0.0
---

# @deploy-ops — Deployment & Operations

**Domain**: Systemd service management, Docker containerization, CI/CD pipelines, secrets management, production deployment  
**Primary Output**: systemd service files, Docker configs, CI pipelines, secret rotation procedures  
**Context Keys Read**: `metadata.environment`, `pipeline.*`, `health.*`  
**Context Keys Written**: (infrastructure agent, writes configs to `ops/` and system)

---

## Invocation

```bash
# Generate systemd service for trading loop
@deploy-ops generate-systemd --service trading-loop --env paper

# Generate Docker Compose
@deploy-ops generate-docker --env paper

# Deploy to production (systemd)
@deploy-ops deploy --target systemd --env prod --service trading-loop

# Check deployment status
@deploy-ops status --service trading-loop

# Rotate secrets
@deploy-ops rotate-secrets --keys kucoin_api,helius_api,jupiter_api

# Run CI pipeline locally
@deploy-ops ci --pipeline test

# Security audit
@deploy-ops audit --static
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `ci-cd-and-automation` | Quality gate pipelines, feature flags, failure feedback loops |
| `shipping-and-launch` | Pre-launch checklists, staged rollouts, rollback procedures |
| `security-and-hardening` | Secrets management, three-tier boundary system, OWASP |
| `git-workflow-and-versioning` | Trunk-based, atomic commits, semantic versioning |
| `pm-skills/pm-ai-shipping:shipping-artifacts` | Durable docs for AI-built app (arch, flows, perms, secrets) |
| `pm-skills/pm-ai-shipping:intended-vs-implemented` | Gap analysis between docs and code |
| `pm-skills/pm-ai-shipping:security-audit-static` | Static security audit: trust boundaries, secrets |

---

## Generated Artifacts

### 1. Systemd Service (`ops/systemd/user/kucoin-trading-loop.service`)

```ini
[Unit]
Description=KuCoin Lane Continuous Trading Loop
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/user/kucoin-lane
Environment=PYTHONPATH=/home/user/kucoin-lane/src
Environment=KUCOIN_ENV=paper
EnvironmentFile=-/home/user/kucoin-lane/.env
ExecStart=/usr/bin/env python3 -u /home/user/kucoin-lane/run_unified_pipeline.py --interval-min 15
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/user/kucoin-lane/data /home/user/kucoin-lane/logs

[Install]
WantedBy=default.target
```

### 2. Docker Compose (`ops/docker/docker-compose.yml`)

```yaml
version: '3.8'
services:
  trading-loop:
    build: .
    environment:
      - KUCOIN_ENV=paper
      - PYTHONPATH=/app/src
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import context; context.read_context()"]
      interval: 60s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  monitor:
    build: .
    command: python -m scripts.monitoring_automation snapshot
    environment:
      - KUCOIN_ENV=paper
    volumes:
      - ./data:/app/data
    deploy:
      resources:
        limits:
          memory: 256M
```

### 3. GitHub Actions CI (`ops/ci/ci.yml`)

```yaml
name: KuCoin Lane CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -e .[dev]
      - run: pytest tests/ -x --tb=short
      - run: python -m scripts.monitoring_automation snapshot
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit safety
      - run: bandit -r src/ -f json -o bandit-report.json
      - run: safety check --json --output safety-report.json
  build:
    needs: [test, security]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t kucoin-lane:${{ github.sha }} .
      - run: docker run --rm kucoin-lane:${{ github.sha }} python -c "import context; print('OK')"
```

### 4. Secrets Management

**Local Development**: `.env` file (gitignored)
```bash
KUCOIN_API_KEY=xxx
KUCOIN_API_SECRET=xxx
KUCOIN_API_PASSPHRASE=xxx
HELIUS_API_KEY=xxx
JUPITER_API_KEY=xxx
ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**Production**: Systemd `EnvironmentFile` + `systemd-creds` or HashiCorp Vault

**Rotation Procedure**:
1. Generate new keys in exchange/provider dashboard
2. Update secret store (Vault/1Password/env file)
3. `systemctl reload kucoin-trading-loop` (no restart needed for env file)
4. Verify health check passes
4. Revoke old keys after 24h confirmation

---

## Pre-Launch Checklist (shipping-and-launch)

| Check | Verification |
|-------|--------------|
| **Secrets** | All API keys in env file, none in code |
| **Circuit Breakers** | All 4 breakers configured with sane defaults |
| **Health Checks** | `/health` endpoint responds, Prometheus metrics exposed |
| **Logging** | Structured JSON logs to stdout + file rotation |
| **Metrics** | Prometheus `/metrics` endpoint, key gauges present |
| **Alerting** | Webhook configured, test alert fires |
| **Rollback** | `systemctl restart kucoin-trading-loop` recovers in < 30s |
| **Data Persistence** | `data/` and `logs/` on persistent volume |
| **Resource Limits** | Memory/CPU limits set in service/container |
| **Security** | No root, read-only fs, dropped capabilities |

---

## Gap Analysis (intended-vs-implemented)

Runs static analysis to find:
- Undocumented API endpoints
- Missing permission checks
- Secrets in code (bandit)
- Dependency vulnerabilities (safety)
- Undocumented config parameters

Output: `data/audit/gap-report.json`

---

## Acceptance Criteria

- [ ] `generate-systemd` produces valid service file that passes `systemd-analyze verify`
- [ ] `generate-docker` produces compose that passes `docker-compose config`
- [ ] CI pipeline passes on clean main branch
- [ ] Security audit finds 0 CRITICAL, ≤ 5 HIGH issues
- [ ] Gap analysis runs without errors
- [ ] Secret rotation procedure documented and tested
- [ ] Rollback tested: service restarts in < 30s after crash
- [ ] All configs parameterized via environment (no hardcoded values)