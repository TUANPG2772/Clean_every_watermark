#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if [ ! -f .venv/clean-local-ready ]; then
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/clean-local-ready
fi
exec .venv/bin/python run.py "$@"
