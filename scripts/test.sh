#!/usr/bin/env bash
set -euo pipefail

python -m pip check || {
  echo "Dependencies missing or inconsistent. Run ./scripts/setup.sh first."
  exit 1
}
pytest
