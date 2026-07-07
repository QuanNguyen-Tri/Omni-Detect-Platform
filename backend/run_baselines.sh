#!/usr/bin/env bash
# =============================================================================
# run_baselines.sh — the one-click wrapper.
#
#   [--setup]  optionally download weights first (baselines/setup.sh)
#   everything else is forwarded verbatim to baselines/run.py
#
# Examples:
#   bash baselines/run_baselines.sh --input img.png --output_dir out --gpu 0
#   bash baselines/run_baselines.sh --input images/ --models PIXAR-7B LISA-7B --output_dir out
#   bash baselines/run_baselines.sh --setup --input batch.csv --output_dir out
#   bash baselines/run_baselines.sh --input img.png --output_dir out --dry-run
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-/home/omnidet/miniconda3/envs/pixar/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3 || command -v python || true)"

RUN_SETUP=0
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --setup) RUN_SETUP=1; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

if [ "${RUN_SETUP}" -eq 1 ]; then
  echo "▶ running setup.sh (weight download) ..."
  bash "${SCRIPT_DIR}/setup.sh"
fi

exec "${PYTHON}" "${SCRIPT_DIR}/run.py" "${ARGS[@]}"
