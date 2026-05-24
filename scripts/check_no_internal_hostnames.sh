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
#   ALLOW_LIST に正規表現を 1 行 1 件追加すると除外できる。

set -euo pipefail

STAGED_ONLY=false
if [[ "${1:-}" == "--staged" ]]; then
  STAGED_ONLY=true
fi

# 検出パターン (egrep)
#
# 検出対象 (どれも 3 階層以上のホスト名 / メールアドレス形式):
#   - 日本のアカデミックドメイン: *.ac.jp / *.go.jp / *.lg.jp
#   - 既知の internal ラボドメイン: *.fun.bio.* (本リポジトリ特有)
#   - keio.ac.jp ドメイン全般
#
# 単なる「.local」「.internal」のような短い TLD は誤検知が多すぎるため対象外。
# 必要なら ALLOW_LIST にプロジェクト固有の例外を足す。
PATTERN='([a-z0-9-]+\.[a-z0-9-]+\.(ac|go|lg)\.jp|[a-z0-9-]+\.fun\.bio\.[a-z.]+|[a-z0-9-]+\.keio\.ac\.jp|tesla\.fun\.bio\.[a-z.]+)'

# 例外として許可する文字列パターン (1 行 1 正規表現)
# テスト用ダミー / プレースホルダー / 教材 URL 等
read -r -d '' ALLOW_LIST <<'EOF' || true
example\.(ac|go|lg)\.jp
your-org\.(ac|go|lg)\.jp
foo\.bar\.(ac|go|lg)\.jp
EOF

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
