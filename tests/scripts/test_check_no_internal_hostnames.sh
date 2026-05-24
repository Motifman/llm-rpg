#!/usr/bin/env bash
# scripts/check_no_internal_hostnames.sh の挙動を pytest 非依存に確認する。
# 通常の pytest からも呼び出せるよう ``test_check_no_internal_hostnames.py`` から
# subprocess で実行される。
#
# 終了コード:
#   0: 全シナリオで期待通り
#   非 0: 期待外れ (テストで catch する)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/check_no_internal_hostnames.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q
git config user.email "test@test"
git config user.name "test"

# 1. 安全な内容なら 0 で抜ける
echo "## docs" > safe.md
echo "see example.ac.jp for academic format" >> safe.md
git add safe.md && git commit -q -m "safe"
if ! bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: safe content was flagged" >&2
  exit 1
fi

# 2. fun.bio.* を含むなら非 0
echo "HostName v108.fun.bio.keio.ac.jp" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: fun.bio FQDN was not flagged" >&2
  exit 1
fi

# 3. tesla.fun.bio.* も非 0
rm leak.md
echo "ProxyCommand ssh tesla.fun.bio.keio.ac.jp -W %h:%p" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: tesla.fun.bio FQDN was not flagged" >&2
  exit 1
fi

# 4. 一般 .ac.jp も非 0
rm leak.md
echo "host: machine.cs.example2.ac.jp" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: .ac.jp FQDN was not flagged" >&2
  exit 1
fi

# 5. example.ac.jp (ALLOW_LIST) はスルー
rm leak.md
echo "see example.ac.jp" > safe2.md
git add safe2.md && git commit -q -m "safe2"
if ! bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: allow-listed example.ac.jp was flagged" >&2
  exit 1
fi

# 6. --staged モードで staged 変更だけスキャン
rm safe2.md  # ファイルだけ消す (まだコミットしてない git rm でなく)
echo "machine.x.ac.jp" > leak.md
git add leak.md
if bash "$SCRIPT" --staged >/dev/null 2>&1; then
  echo "FAIL: --staged mode missed staged leak" >&2
  exit 1
fi

echo "all scenarios passed"
