#!/usr/bin/env bash
# =============================================================================
# setup.sh — one-click download of the baseline detection weights + tokenizer/config
#            (PIXAR, SIDA, LISA) and the SAM ViT-H mask backbone.
#
# What it fetches (each is a full HF snapshot: weights + tokenizer + config):
#   PIXAR-7B   jiachengcui888/PIXAR-7B          (main detector)
#   PIXAR-13B  jiachengcui888/PIXAR-13B
#   SIDA-7B    saberzl/SIDA-7B                  (offline baseline)
#   SIDA-13B   saberzl/SIDA-13B
#   LISA-7B    xinlai/LISA-7B-v1               (offline baseline, seg-only)
#   LISA-13B   xinlai/LISA-13B-llama2-v1
#   SAM ViT-H  sam_vit_h_4b8939.pth  (dl.fbaipublicfiles.com) — mask decoder for PIXAR/SIDA
# CLIP ViT-L/14 (openai/clip-vit-large-patch14) is auto-downloaded at model-load time.
#
# NOT downloaded (per request): the ~260 GB PIXAR image datasets. Those are only
# needed for `test_parallel.py` metric evaluation, not for the inference in this
# toolkit. (Use setup/downloads/download_train.sh if you ever need them.)
#
# Idempotent: a `.download_done` marker per model means re-running is a no-op.
# Matches the pattern in setup/downloads/download_*.sh.
#
# Usage:
#   bash baselines/setup.sh                          # all 6 models + SAM
#   bash baselines/setup.sh --models "PIXAR-7B SIDA-7B LISA-7B"
#   bash baselines/setup.sh --check                  # report present/missing only
#   PRETRAINS=/data/tan1/pretrains bash baselines/setup.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PRETRAINS="${PRETRAINS:-${REPO_ROOT}/pretrains}"
HF_HOME_DIR="${HF_HOME:-/data/tan1/hf_cache}"
PYTHON="${PYTHON:-/home/omnidet/miniconda3/envs/pixar/bin/python}"
# `|| true` so a missing python does not trip `set -e` here — let the explicit
# `[ -x ... ]` guard below emit the friendly error instead.
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3 || command -v python || true)"

MODELS="PIXAR-7B PIXAR-13B SIDA-7B SIDA-13B LISA-7B LISA-13B"
CHECK_ONLY=0
DO_SAM=1

while [ $# -gt 0 ]; do
  case "$1" in
    --models)     MODELS="${2:?--models requires an argument}"; shift 2 ;;
    --check)      CHECK_ONLY=1; shift ;;
    --no-sam)     DO_SAM=0; shift ;;
    --pretrains)  PRETRAINS="${2:?--pretrains requires an argument}"; shift 2 ;;
    --python)     PYTHON="${2:?--python requires an argument}"; shift 2 ;;
    -h|--help)    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

# name -> HF repo id
repo_id() {
  case "$1" in
    PIXAR-7B)  echo "jiachengcui888/PIXAR-7B" ;;
    PIXAR-13B) echo "jiachengcui888/PIXAR-13B" ;;
    SIDA-7B)   echo "saberzl/SIDA-7B" ;;
    SIDA-13B)  echo "saberzl/SIDA-13B" ;;
    LISA-7B)   echo "xinlai/LISA-7B-v1" ;;
    LISA-13B)  echo "xinlai/LISA-13B-llama2-v1" ;;
    *) echo ""; return 1 ;;
  esac
}

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YEL='\033[0;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] $*${NC}"; }
sect() { echo -e "\n${CYAN}▶ $*${NC}"; }
warn() { echo -e "${YEL}$*${NC}"; }

echo "PRETRAINS = ${PRETRAINS}"
echo "PYTHON    = ${PYTHON}"
echo "HF_HOME   = ${HF_HOME_DIR}"
echo "MODELS    = ${MODELS}"
mkdir -p "${PRETRAINS}" "${HF_HOME_DIR}"

# ---- --check: report only ---------------------------------------------------
if [ "${CHECK_ONLY}" -eq 1 ]; then
  sect "Presence check (no downloads)"
  for m in ${MODELS}; do
    d="${PRETRAINS}/${m}"
    if [ -f "${d}/.download_done" ]; then
      echo "  [OK]      ${m}  ($(du -sh "${d}" 2>/dev/null | cut -f1))"
    elif [ -d "${d}" ] && [ -n "$(ls -A "${d}" 2>/dev/null)" ]; then
      echo "  [PARTIAL] ${m}  (present but unmarked — re-run setup to verify/resume)"
    else
      echo "  [MISSING] ${m}  -> $(repo_id "${m}")"
    fi
  done
  sam="${PRETRAINS}/sam_vit_h_4b8939.pth"
  if [ -f "${sam}.download_done" ]; then
    echo "  [OK]      SAM ViT-H ($(du -sh "${sam}" | cut -f1))"
  elif [ -f "${sam}" ]; then
    echo "  [PARTIAL] SAM ViT-H (present but unmarked — re-run setup to verify/resume)"
  else
    echo "  [MISSING] SAM ViT-H -> sam_vit_h_4b8939.pth"
  fi
  exit 0
fi

[ -x "${PYTHON}" ] || { echo "ERROR: no python interpreter found" >&2; exit 1; }
export HF_HOME="${HF_HOME_DIR}"

# ---- model snapshots --------------------------------------------------------
for m in ${MODELS}; do
  rid="$(repo_id "${m}")" || { warn "skip unknown model ${m}"; continue; }
  dest="${PRETRAINS}/${m}"
  # Idempotency is gated ONLY on the completion marker (written after the
  # snapshot returns). config.json lands early, so it must NOT count as "done" —
  # otherwise an interrupted download would be sealed as complete. With no
  # marker we always (re)enter snapshot_download, whose resume_download verifies
  # existing files and fetches only what's missing.
  if [ -f "${dest}/.download_done" ]; then
    log "[SKIP] ${m} already downloaded ($(du -sh "${dest}" 2>/dev/null | cut -f1))"
    continue
  fi
  if [ -d "${dest}" ] && [ -n "$(ls -A "${dest}" 2>/dev/null)" ]; then
    warn "[RESUME] ${m}: unmarked files present — verifying / resuming"
  fi
  sect "${m}  (HuggingFace: ${rid})"
  mkdir -p "${dest}"
  HF_HUB_ENABLE_HF_TRANSFER=1 "${PYTHON}" - "$rid" "$dest" <<'PY'
import sys
from huggingface_hub import snapshot_download
repo_id, dest = sys.argv[1], sys.argv[2]
snapshot_download(repo_id=repo_id, local_dir=dest,
                  local_dir_use_symlinks=False, resume_download=True, max_workers=4)
print(f"[OK] {repo_id} -> {dest}")
PY
  touch "${dest}/.download_done"
  log "[OK] ${m} -> ${dest} ($(du -sh "${dest}" | cut -f1))"
done

# ---- SAM ViT-H (mask decoder for PIXAR / SIDA) ------------------------------
if [ "${DO_SAM}" -eq 1 ]; then
  sam="${PRETRAINS}/sam_vit_h_4b8939.pth"
  # Skip only on the completion marker. Without it we run `wget -c`, which
  # resumes a partial .pth (or no-ops on an already-complete file) — a bare
  # `[ -f "${sam}" ]` guard would instead trust a truncated file forever.
  if [ -f "${sam}.download_done" ]; then
    log "[SKIP] SAM ViT-H present ($(du -sh "${sam}" | cut -f1))"
  else
    sect "SAM ViT-H (sam_vit_h_4b8939.pth, ~2.6 GB)"
    wget -c -O "${sam}" \
      "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"
    touch "${sam}.download_done"
    log "[OK] SAM ViT-H -> ${sam}"
  fi
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Weights ready under ${PRETRAINS}"
echo " CLIP ViT-L/14 (openai/clip-vit-large-patch14) auto-downloads at model load."
echo " Next:  bash baselines/run_baselines.sh --input <img|folder|list> --output_dir out"
echo "════════════════════════════════════════════════════════════"
