#!/usr/bin/env bash
# KuCoin Lane — Live Paper Trading Dashboard
# Reads container logs + state to show signals, intelligence, trades, and health
set -euo pipefail

CONTAINER="kucoin-lane"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'
CYN='\033[0;36m'; MAG='\033[0;35m'; RST='\033[0m'; BOLD='\033[1m'

docker_exec() {
  if [ $# -eq 1 ] && [[ "$1" == *'*'* ]]; then
    echo '1980' | sudo -S docker exec "$CONTAINER" sh -c "$1" 2>/dev/null
  else
    echo '1980' | sudo -S docker exec "$CONTAINER" "$@" 2>/dev/null
  fi
}

docker_logs() {
    echo '1980' | sudo -S docker logs --tail "${1:-300}" "$CONTAINER" 2>&1 | grep -v "\[sudo\]" | grep -v "password"
}

clear
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════════╗${RST}"
echo -e "${BOLD}║         KUCOIN LANE — Paper Trading Dashboard                   ║${RST}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════════╝${RST}"
echo ""

# ── Container Health ──
echo -e "${BLU}── Container ──${RST}"
STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "NOT_FOUND")
UPTIME=$(docker inspect --format='{{.State.StartedAt}}' "$CONTAINER" 2>/dev/null || echo "N/A")
RESTARTS=$(docker inspect --format='{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo "N/A")
if [ "$STATUS" = "running" ]; then
    echo -e "  Status:    ${GRN}RUNNING${RST}"
else
    echo -e "  Status:    ${RED}${STATUS}${RST}"
fi
echo -e "  Started:   ${UPTIME}"
echo -e "  Restarts:  ${RESTARTS}"
echo ""

# ── Session State ──
echo -e "${BLU}── Session State ──${RST}"
SS=$(docker_exec cat /app/lanes/kucoin/inbox/SESSION_STATE.json 2>/dev/null || echo "{}")
echo "$SS" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(f\"  Mode:     {d.get('mode','N/A')}\")
    print(f\"  Status:   {d.get('status','N/A')}\")
    print(f\"  Phase:    {d.get('phase','N/A')}\")
    print(f\"  Cycle:    {d.get('cycle','N/A')}\")
    print(f\"  Uptime:   {d.get('uptime_seconds',0):.0f}s\")
except: print('  No session state')
" 2>/dev/null
echo ""

# ── Return Report (latest) ──
echo -e "${BLU}── Last Return Report ──${RST}"
RR_FILE=$(docker_exec 'ls -t /app/agent-logs/return-report-*.json 2>/dev/null | head -1')
if [ -n "$RR_FILE" ]; then
docker_exec cat "$RR_FILE" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    cb = 'TRIPPED' if d.get('circuit_breaker_active') else 'OK'
    tp = 'PAUSED' if d.get('trading_paused') else 'ACTIVE'
    print(f\"  Balance:    \${d.get('account_balance', 'N/A')}\")
    print(f\"  CB Status:  {cb}\")
    print(f\"  Trading:    {tp}\")
    print(f\"  Audit:      {'PASS' if d.get('audit_passed') else 'FAIL'}\")
    print(f\"  Violations: {len(d.get('violations', []))}\")
    print(f\"  Stage:      {d.get('stage', 'N/A')}\")
    print(f\"  Duration:   {d.get('cycle_duration_seconds', 'N/A')}s\")
    print(f\"  Updated:    {d.get('timestamp', 'N/A')}\")
except Exception as e: print(f'  Parse error: {e}')
" 2>/dev/null
else
    echo "  No return reports found"
fi
echo ""

# ── Strategy Signal ──
echo -e "${BLU}── Strategy Signal ──${RST}"
SIG=$(docker_logs 300 | grep "\[STRATEGY\]" | tail -1 | sed 's/.*INFO //')
if [ -n "$SIG" ]; then
    ACTION=$(echo "$SIG" | grep -oP 'action=\w+' | cut -d= -f2)
    CONF=$(echo "$SIG" | grep -oP 'confidence=[\d.]+' | cut -d= -f2)
    if [ "$ACTION" = "BUY" ]; then
        COLOR=$GRN
    elif [ "$ACTION" = "SELL" ]; then
        COLOR=$RED
    else
        COLOR=$YEL
    fi
    echo -e "  ${COLOR}${SIG}${RST}"
else
    echo "  No strategy signal in recent logs"
fi
echo ""

# ── Regime ──
echo -e "${BLU}── Regime Detector ──${RST}"
REG=$(docker_logs 300 | grep "Regime:" | tail -1 | sed 's/.*INFO //')
if [ -n "$REG" ]; then
    echo -e "  ${MAG}${REG}${RST}"
else
    echo "  No regime data in recent logs"
fi
echo ""

# ── Whale / CVD ──
echo -e "${BLU}── Whale Watch / CVD ──${RST}"
WHALE=$(docker_logs 300 | grep "Whale Watch:" | tail -1 | sed 's/.*INFO //')
if [ -n "$WHALE" ]; then
    echo -e "  ${CYN}${WHALE}${RST}"
else
    echo "  No whale/CVD data in recent logs"
fi
echo ""

# ── Intelligence Summary ──
echo -e "${BLU}── Intelligence (last cycle) ──${RST}"
docker_logs 300 | grep "\[INTELLIGENCE\]" | tail -5 | while read -r line; do
    echo "  $(echo "$line" | sed 's/.*INFO //')"
done
echo ""

# ── Live Pre-Launch Creator Event ──
echo -e "${BLU}── Live Pre-Launch Creator ──${RST}"
LIVE=$(docker_exec cat /app/data/latest_live_prelaunch.json 2>/dev/null || echo "{}")
echo "$LIVE" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read() or '{}')
    if not d or not d.get('mint'):
        print('  No live pre-launch events yet')
    else:
        tags = ','.join(d.get('tags', [])) or 'none'
        intel = d.get('external_creator_intelligence', {}) or {}
        sources = ','.join(intel.get('source_names', [])) or 'none'
        print(f\"  Token:     {d.get('symbol','?')} {d.get('mint','')[:10]}...\")
        print(f\"  Creator:   {d.get('creator','')[:16]}...\")
        print(f\"  Score:     {d.get('reputation_score', 0):.3f}\")
        print(f\"  Tags:      {tags}\")
        print(f\"  Sources:   {sources}\")
        print(f\"  Updated:   {d.get('timestamp','N/A')}\")
except Exception as e: print(f'  Parse error: {e}')
" 2>/dev/null
echo ""

# ── Paper Trades ──
echo -e "${BLU}── Paper Trades ──${RST}"
PT=$(docker_exec cat /app/state/paper_trades_ledger.json 2>/dev/null || echo "[]")
echo "$PT" | python3 -c "
import sys, json
try:
    trades = json.loads(sys.stdin.read())
    if not trades:
        print('  No trades yet (HOLD/SELL-skip only)')
    else:
        for t in trades[-5:]:
            print(f\"  {t.get('timestamp','')} {t.get('pair','')} {t.get('side','')} @ {t.get('price','')} size={t.get('size','')}\")
        print(f'  Total trades: {len(trades)}')
except: print('  No trades ledger found')
" 2>/dev/null
echo ""

# ── Last 3 Cycles ──
echo -e "${BLU}── Last 3 Cycles ──${RST}"
docker_logs 500 | grep "CYCLE.*COMPLETE" | tail -3 | while read -r line; do
    echo "  $(echo "$line" | sed 's/.*\[DryRunExecutor\] //' | sed 's/.*INFO //')"
done
echo ""

# ── Risk Warnings ──
echo -e "${BLU}── Risk Warnings ──${RST}"
WARNINGS=$(docker_logs 300 | grep -iE "WARNING|Daily loss" | tail -3)
if [ -n "$WARNINGS" ]; then
    echo -e "  ${YEL}$(echo "$WARNINGS" | sed 's/.*WARNING /WARN: /' | head -3)${RST}"
else
    echo -e "  ${GRN}None${RST}"
fi
echo ""

# ── Errors ──
echo -e "${BLU}── Recent Errors ──${RST}"
ERRORS=$(docker_logs 500 | grep -iE "^.*ERROR|CRITICAL|Traceback" | tail -3)
if [ -n "$ERRORS" ]; then
    echo -e "  ${RED}$(echo "$ERRORS" | sed 's/.*ERROR /ERR: /' | head -3)${RST}"
else
    echo -e "  ${GRN}None${RST}"
fi
echo ""
echo -e "${BOLD}──────────────────────────────────────────────────────────────────${RST}"
echo -e "Auto-refresh: ${CYN}watch -n 10 ./dashboard.sh${RST}"
