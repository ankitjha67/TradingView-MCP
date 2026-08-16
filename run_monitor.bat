@echo off
REM Keeps the monitor running independently of any shell session.
REM Launch with:  start "" run_monitor.bat     (or double-click it)
setlocal
set PYTHONPATH=%~dp0src
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python -m tradingview_mcp.core.quant.monitor --capital 50000 --currency INR --risk 1.0 --out .
