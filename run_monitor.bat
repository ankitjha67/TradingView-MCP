@echo off
REM Keeps the monitor running independently of any shell session.
REM Launch with:  start "" run_monitor.bat     (or double-click it)
REM
REM   set NO_LLM=1  before launching for numbers only, skipping the commentary call.
REM
REM Writes tv_active_chart.md and tv_active_chart.json into this directory, fresh
REM at every bar close.
REM
REM Only one monitor may own this directory at a time; a second launch exits with
REM the first one's PID rather than quietly racing it for the same report files.
setlocal
set PYTHONPATH=%~dp0src
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

REM Commentary is on unless asked otherwise — leaving it off by default meant the
REM report silently lacked the analysis the LLM settings were configured for.
set LLM_FLAG=--llm
if defined NO_LLM set LLM_FLAG=

python -m tradingview_mcp.core.quant.monitor --capital 50000 --currency INR --risk 1.0 %LLM_FLAG% --out . %*
