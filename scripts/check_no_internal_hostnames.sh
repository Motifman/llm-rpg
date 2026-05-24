#!/usr/bin/env bash
# 内部 / 組織 ホスト名らしき文字列の混入を検出する。
# pre-commit / CI / 手動実行のいずれでも使える。
#
# 使い方:
#   ./scripts/check_no_internal_hostnames.sh                # 作業ツリー全体を確認
#   ./scripts/check_no_internal_hostnames.sh --staged       # ステージ済み変更のみ確認
#
# パターン:
#   - 任意の TLD ``.ac.jp`` (日本の大学・研究機関)
#   - 既知の所属ドメイン断片 (この repo のメイン研究室)
#   - 一般的な internal-only TLD (.internal / .local / .lan)
#   - well-known JP 大学ドメイン (拡張余地)
#
# False positive 想定:
#   - external サンプル URL (e.g. example.ac.jp) → allow_list で除外
#   - `code` ブロック内のコメント説明 → 必要なら ALLOW_LIST 行で対応
#
# 設定:
#   ALLOW_LIST に正規表現を 1 行 1 件追加すると文字列単位で除外できる。
#   ファイル単位で除外したい場合は、対象ファイル先頭 30 行内に
#     # check-no-internal-hostnames: allow-file
#   を 1 行入れる。

set -euo pipefail

STAGED_ONLY=false
if [[ "${1:-}" == "--staged" ]]; then
  STAGED_ONLY=true
fi

# 検出パターン (egrep)
#
# 組織固有の具体名 (実 FQDN / 組織ドメイン断片) をこのファイルに書かないこと。
# 「自分の環境を晒さないためのチェッカー」が組織名で構成されていたら本末転倒。
#
# 検出対象は十分に汎用なカテゴリだけにする:
#   - 公的ドメイン階層: *.ac.jp / *.go.jp / *.lg.jp (日本のアカデミック / 行政)
#   - プライベート IP の具体値: 10.x.x.x / 192.168.x.x / 172.16-31.x.x
#
# 上記で拾えない特定 FQDN を追加で検出したい場合は、ALLOW_LIST と対称の
# DENY_LIST 機構を別途用意する想定 (本スクリプト本体には組織名を書かない)。
PATTERN_FQDN='[a-z0-9-]+\.[a-z0-9-]+\.(ac|go|lg)\.jp'
PATTERN_PRIVATE_IP='(\b10(\.[0-9]{1,3}){3}\b|\b192\.168(\.[0-9]{1,3}){2}\b|\b172\.(1[6-9]|2[0-9]|3[0-1])(\.[0-9]{1,3}){2}\b)'
PATTERN="(${PATTERN_FQDN}|${PATTERN_PRIVATE_IP})"

# 例外として許可する文字列パターン (1 行 1 正規表現)
# テスト用ダミー / プレースホルダー / 教材 URL 等
read -r -d '' ALLOW_LIST <<'EOF' || true
example\.(ac|go|lg)\.jp
your-org\.(ac|go|lg)\.jp
foo\.bar\.(ac|go|lg)\.jp
EOF

# ファイル単位のスキップマーカー。当該ファイルの先頭 30 行内に
#   # check-no-internal-hostnames: allow-file
# とコメントを書くと、そのファイル全体をスキャン対象から除外する。
#
# 主な用途:
#   - docs/security_hosts_policy.md (漏洩パターンを「書いてはいけない例」として
#     掲載するため、本文中に FQDN を含む必要がある)
#   - tests/scripts/test_check_no_internal_hostnames.sh (検出ロジック自体を
#     検証するため、テスト用の FQDN リテラルを含む必要がある)
ALLOW_FILE_MARKER='check-no-internal-hostnames:[[:space:]]*allow-file'

has_allow_file_marker() {
  head -n 30 "$1" 2>/dev/null | grep -Eq "$ALLOW_FILE_MARKER"
}

if $STAGED_ONLY; then
  # ステージ済み差分のみ
  target_files() {
    git diff --cached --name-only --diff-filter=ACM
  }
  scan() {
    git diff --cached -- "$1"
  }
else
  # 作業ツリー全体 (binary / vendor / lock などはスキップ)
  target_files() {
    git ls-files | grep -Ev '\.(png|jpg|jpeg|gif|ico|pdf|woff2?|ttf|otf|mp4|webm|lock|jsonl)$' | grep -Ev '^(node_modules|\.venv|venv|frontend/dist|tools/asset_pipeline/\.venv)/'
  }
  scan() {
    cat "$1"
  }
fi

violations=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  [[ -f "$f" ]] || continue
  # ファイル先頭の allow-file マーカーがあればスキャン対象外
  if has_allow_file_marker "$f"; then
    continue
  fi
  # 大文字を許容するため -i
  matches=$(scan "$f" 2>/dev/null | grep -EioI "$PATTERN" || true)
  [[ -z "$matches" ]] && continue
  # ALLOW_LIST に該当するものを除外
  filtered=$(echo "$matches" | while IFS= read -r m; do
    skip=false
    while IFS= read -r allow; do
      [[ -z "$allow" ]] && continue
      if echo "$m" | grep -Eqi "$allow"; then
        skip=true
        break
      fi
    done <<< "$ALLOW_LIST"
    if ! $skip; then
      echo "$m"
    fi
  done | grep -v '^$' || true)
  [[ -z "$filtered" ]] && continue
  echo "[NG] $f:" >&2
  echo "$filtered" | sed 's/^/    /' >&2
  violations=$((violations + 1))
done < <(target_files)

if [[ $violations -gt 0 ]]; then
  echo >&2
  echo "Internal/organizational hostname patterns detected in $violations file(s)." >&2
  echo "Replace with placeholders (e.g. <vllm-host>) and re-run." >&2
  echo "If a false positive, add a regex to ALLOW_LIST in this script." >&2
  exit 1
fi

echo "OK: no internal hostname patterns detected"
