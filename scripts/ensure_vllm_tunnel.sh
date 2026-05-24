#!/usr/bin/env bash
# vLLM への SSH トンネルを確認し、未接続なら $VLLM_SSH_HOST で起動する。
#
# 前提: ~/.ssh/config に Host エイリアスが定義されていること
#       (LocalForward $VLLM_LOCAL_PORT → リモートの vLLM port)。
# 実 FQDN は本リポジトリに書かない。docs/security_hosts_policy.md 参照。
#
# 使い方:
#   ./scripts/ensure_vllm_tunnel.sh          # 確認 + 必要なら起動
#   ./scripts/ensure_vllm_tunnel.sh --check  # 確認のみ (exit 1 if down)
#
# 環境変数:
#   VLLM_LOCAL_PORT  既定 18001 (Cursor 等との 8001 競合回避のため)
#   VLLM_SSH_HOST    既定 v108-vllm (リポジトリ既定の Host エイリアス名)

set -euo pipefail

LOCAL_PORT="${VLLM_LOCAL_PORT:-18001}"
SSH_HOST="${VLLM_SSH_HOST:-v108-vllm}"
API_BASE="http://127.0.0.1:${LOCAL_PORT}/v1/models"
CHECK_ONLY=false

if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=true
fi

vllm_reachable() {
  curl -sf -m 5 "${API_BASE}" >/dev/null 2>&1
}

if vllm_reachable; then
  echo "OK: vLLM reachable at ${API_BASE}"
  exit 0
fi

if $CHECK_ONLY; then
  echo "NG: vLLM not reachable at ${API_BASE}" >&2
  echo "Hint: run without --check to start tunnel: ssh -N ${SSH_HOST} &" >&2
  exit 1
fi

if pgrep -f "ssh -N ${SSH_HOST}" >/dev/null 2>&1 || pgrep -f "ssh -N -L ${LOCAL_PORT}:127.0.0.1:8001" >/dev/null 2>&1; then
  echo "SSH tunnel process exists but vLLM not responding; waiting..." >&2
  for _ in $(seq 1 10); do
    sleep 1
    if vllm_reachable; then
      echo "OK: vLLM reachable at ${API_BASE}"
      exit 0
    fi
  done
fi

echo "Starting SSH tunnel: ssh -N ${SSH_HOST} (local ${LOCAL_PORT} → remote vLLM)" >&2
ssh -N "${SSH_HOST}" &
for i in $(seq 1 15); do
  sleep 1
  if vllm_reachable; then
    echo "OK: vLLM reachable at ${API_BASE} (after ${i}s)"
    exit 0
  fi
done

echo "NG: tunnel started but vLLM still not reachable at ${API_BASE}" >&2
echo "Check the remote vLLM with your usual SSH access, e.g.:" >&2
echo "  ssh <your-host> 'curl -s http://127.0.0.1:8001/v1/models | head'" >&2
exit 1
