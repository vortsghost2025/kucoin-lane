@echo off
REM KuCoin Lane Optimized Launch Script
REM Generated: 2026-06-09

cd /d S:\kucoin-lane

echo Starting KuCoin Lane with optimized config...
echo Creator Boost Threshold: 1.01
echo Min Signal Score: 0.35
echo Paper Trading: True
echo SOL Per Trade: 0.05
echo Cycle Interval: 15 min
echo Max Tokens: 10
echo.

REM Run creator pipeline first to populate Helius-resolved creators
echo [1/3] Running Creator Pipeline (Helius Resolution)...
python integrate_prelaunch_intelligence.py

echo.
echo [2/3] Running Intelligence Scans...
python -c "from tools.cp_prelaunch_scan import main; main()" 2>nul || powershell -Command "& .\tools\cp-prelaunch-scan.ps1 -Limit 50"
powershell -Command "& .\tools\cp-dex-scan.ps1 -FullScan -PumpFun -TopN 20"
powershell -Command "& .\tools\cp-social-scan.ps1 -FullScan -Watchlist \"SOL,BONK,WIF,JUP,PEPE\""

echo.
echo [3/3] Starting Continuous Paper Trading Loop...
python run_pipeline.py --mode paper --continuous --interval-min 15 --limit 10 --min-boost 1.01 --sol-per-trade 0.05 --paper-ledger data/paper_trades_ledger.json

pause