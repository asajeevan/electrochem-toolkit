#!/bin/bash
# Opens Cyclara on macOS without the app bundle. Run "Setup (Mac).command" once before the first use.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Run 'Setup (Mac).command' first: double-click it in this folder and wait until it says 'Setup finished'."
  read -n 1 -s -r -p "Press any key to close."; exit 1
fi
exec .venv/bin/python -m electrochem.studio "$@"
