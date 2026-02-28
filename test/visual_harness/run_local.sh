#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

CENTER_PID=""
VISUAL_PID=""

cleanup() {
  local exit_code=$?
  set +e

  if [[ -n "${VISUAL_PID}" ]] && kill -0 "${VISUAL_PID}" 2>/dev/null; then
    kill "${VISUAL_PID}" 2>/dev/null || true
  fi

  if [[ -n "${CENTER_PID}" ]] && kill -0 "${CENTER_PID}" 2>/dev/null; then
    kill "${CENTER_PID}" 2>/dev/null || true
  fi

  wait "${VISUAL_PID}" 2>/dev/null || true
  wait "${CENTER_PID}" 2>/dev/null || true
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

echo "[visual-harness] starting center process..."
poetry run python test/visual_harness/run_center.py &
CENTER_PID=$!

sleep 1

echo "[visual-harness] starting ui process..."
poetry run python test/visual_harness/visual_harness.py \
  --host 127.0.0.1 \
  --port 8080 \
  --sensor-endpoint tcp://127.0.0.1:5555 \
  --display-endpoint tcp://127.0.0.1:5556 \
  --motor-endpoint tcp://127.0.0.1:5557 &
VISUAL_PID=$!

echo "[visual-harness] open http://localhost:8080"
echo "[visual-harness] press Ctrl+C to stop both processes"

wait -n "${CENTER_PID}" "${VISUAL_PID}"
