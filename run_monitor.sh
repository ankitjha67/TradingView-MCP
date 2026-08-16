#!/usr/bin/env bash
# Keep the monitor running independently of the shell that started it.
#
#   ./run_monitor.sh                 # follow whatever TradingView chart is open
#   ./run_monitor.sh --capital 50000 # any monitor flag passes straight through
#
# Writes tv_active_chart.md and tv_active_chart.json into this directory, fresh at
# every bar close. Stop with Ctrl+C, or `pkill -f quant.monitor` if detached.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$HERE/src"
export PYTHONIOENCODING=utf-8
cd "$HERE"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

exec "$PY" -m tradingview_mcp.core.quant.monitor \
    --capital "${CAPITAL:-50000}" \
    --currency "${CURRENCY:-INR}" \
    --risk "${RISK:-1.0}" \
    --out . \
    "$@"
