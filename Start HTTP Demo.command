#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo "First follow the Python setup in README.md."
  read -r "?Press Enter to close."
  exit 1
fi
exec .venv/bin/python server.py --demo-http
