#!/usr/bin/env python3
"""Deploy Ops Agent Entry Point"""

import sys
import argparse
import json
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

OPS_DIR = Path(__file__).parent.parent.parent / "ops"
SYSTEMD_DIR = OPS_DIR / "systemd" / "user"
DOCKER_DIR = OPS_DIR / "docker"
CI_DIR = OPS_DIR / "ci"

SYSTEMD_SERVICE_TEMPLATE = """[Unit]
Description=KuCoin Lane Continuous Trading Loop
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={workdir}
Environment=PYTHONPATH={workdir}/src
Environment=KUCOIN_ENV={env}
EnvironmentFile=-{workdir}/.env
ExecStart=/usr/bin/env python3 -u {workdir}/run_unified_pipeline.py --interval-min 15
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
ReadWritePaths={workdir}/data {workdir}/logs

[Install]
WantedBy=default.target
"""

DOCKER_COMPOSE_TEMPLATE = """version: '3.8'
services:
  trading-loop:
    build: .
    environment:
      - KUCOIN_ENV={env}
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
      - KUCOIN_ENV={env}
    volumes:
      - ./data:/app/data
    deploy:
      resources:
        limits:
          memory: 256M
"""

CI_TEMPLATE = """name: KuCoin Lane CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{python-version: '3.11'}}
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
"""

def generate_systemd(service="trading-loop", env="paper"):
    """Generate systemd service file."""
    workdir = str(Path(__file__).parent.parent.parent)
    content = SYSTEMD_SERVICE_TEMPLATE.format(workdir=workdir, env=env)
    
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    service_path = SYSTEMD_DIR / f"kucoin-{service}.service"
    service_path.write_text(content)
    
    timer_content = f"""[Unit]
Description=KuCoin Lane {service} Timer
Requires=kucoin-{service}.service

[Timer]
OnBootSec=1min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
"""
    timer_path = SYSTEMD_DIR / f"kucoin-{service}.timer"
    timer_path.write_text(timer_content)
    
    return {
        "success": True,
        "service_file": str(service_path),
        "timer_file": str(timer_path),
    }

def generate_docker(env="paper"):
    """Generate Docker Compose file."""
    DOCKER_DIR.mkdir(parents=True, exist_ok=True)
    compose_path = DOCKER_DIR / "docker-compose.yml"
    compose_path.write_text(DOCKER_COMPOSE_TEMPLATE.format(env=env))
    
    dockerfile = DOCKER_DIR / "Dockerfile"
    dockerfile_content = """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install -e .
CMD ["python", "run_unified_pipeline.py", "--interval-min", "15"]
"""
    dockerfile.write_text(dockerfile_content)
    
    return {
        "success": True,
        "compose_file": str(compose_path),
        "dockerfile": str(dockerfile),
    }

def generate_ci():
    """Generate CI pipeline."""
    CI_DIR.mkdir(parents=True, exist_ok=True)
    ci_path = CI_DIR / "ci.yml"
    ci_path.write_text(CI_TEMPLATE)
    
    return {"success": True, "ci_file": str(ci_path)}

def deploy_systemd(service="trading-loop", env="paper"):
    """Deploy systemd service."""
    result = generate_systemd(service, env)
    
    # Reload systemd and enable
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", f"kucoin-{service}.timer"], check=True)
        subprocess.run(["systemctl", "--user", "start", f"kucoin-{service}.timer"], check=True)
        status = subprocess.run(["systemctl", "--user", "status", f"kucoin-{service}.timer"], capture_output=True, text=True)
        result["deployed"] = True
        result["status"] = status.stdout
    except subprocess.CalledProcessError as e:
        result["deployed"] = False
        result["error"] = e.stderr
    
    return result

def check_status(service="trading-loop"):
    """Check deployment status."""
    try:
        status = subprocess.run(["systemctl", "--user", "status", f"kucoin-{service}.timer"], capture_output=True, text=True)
        return {"active": status.returncode == 0, "output": status.stdout}
    except:
        return {"active": False, "error": "systemctl not available"}

def rotate_secrets(keys):
    """Rotate API secrets."""
    # This would integrate with secret manager (Vault, 1Password, etc.)
    # For now, document the process
    key_list = keys.split(",") if keys else ["kucoin_api", "helius_api", "jupiter_api"]
    
    steps = [
        f"1. Generate new {key} in provider dashboard" for key in key_list
    ] + [
        "2. Update secret store (Vault/1Password/.env)",
        "3. systemctl --user reload kucoin-trading-loop",
        "4. Verify health check passes",
        "5. Revoke old keys after 24h confirmation"
    ]
    
    return {"keys": key_list, "steps": steps}

def run_ci(pipeline="test"):
    """Run CI pipeline locally."""
    # Run tests
    result = subprocess.run(["pytest", "tests/", "-x", "--tb=short"], capture_output=True, text=True)
    
    # Run security checks
    sec_result = subprocess.run(["bandit", "-r", "src/", "-f", "json"], capture_output=True, text=True)
    
    # Build Docker
    build_result = subprocess.run(["docker", "build", "-t", "kucoin-lane:local", "."], capture_output=True, text=True)
    
    return {
        "tests": {"passed": result.returncode == 0, "output": result.stdout[-500:]},
        "security": {"passed": sec_result.returncode == 0, "output": sec_result.stdout[-500:]},
        "build": {"passed": build_result.returncode == 0, "output": build_result.stdout[-500:]},
    }

def audit_static():
    """Run static security audit."""
    # Run bandit
    bandit_result = subprocess.run(["bandit", "-r", "src/", "-f", "json"], capture_output=True, text=True)
    
    # Run safety
    safety_result = subprocess.run(["safety", "check", "--json"], capture_output=True, text=True)
    
    # Gap analysis (intended vs implemented)
    gaps = [
        "Document API rate limit handling in dex-scanner",
        "Add integration test for risk-mgr circuit breakers",
        "Document secret rotation procedure in DEPLOY.md",
    ]
    
    return {
        "bandit": json.loads(bandit_result.stdout) if bandit_result.stdout else {"issues": []},
        "safety": json.loads(safety_result.stdout) if safety_result.stdout else {"vulnerabilities": []},
        "gaps": gaps,
    }

def main():
    parser = argparse.ArgumentParser(description="Deploy Ops Agent")
    parser.add_argument("action", choices=["generate-systemd", "generate-docker", "generate-ci", "deploy", "status", "rotate-secrets", "ci", "audit"])
    parser.add_argument("--service", type=str, default="trading-loop")
    parser.add_argument("--env", choices=["paper", "prod"], default="paper")
    parser.add_argument("--target", choices=["systemd", "docker"], default="systemd")
    parser.add_argument("--keys", type=str)
    parser.add_argument("--pipeline", type=str, default="test")
    parser.add_argument("--static", action="store_true")
    args = parser.parse_args()
    
    if args.action == "generate-systemd":
        result = generate_systemd(args.service, args.env)
    elif args.action == "generate-docker":
        result = generate_docker(args.env)
    elif args.action == "generate-ci":
        result = generate_ci()
    elif args.action == "deploy":
        result = deploy_systemd(args.service, args.env)
    elif args.action == "status":
        result = check_status(args.service)
    elif args.action == "rotate-secrets":
        result = rotate_secrets(args.keys)
    elif args.action == "ci":
        result = run_ci(args.pipeline)
    elif args.action == "audit":
        result = audit_static()
    
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()