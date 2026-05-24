#!/usr/bin/env bash
# check-no-internal-hostnames: allow-file
# ↑ このスクリプトは検出ロジックを試すために合成的な FQDN / IP リテラルを
# 含む必要がある。すべて RFC 5737 / IANA 予約相当の **合成的な名前** であり、
# 実在の組織を指さない。ファイル単位で漏洩防止チェックの対象外とする。
#
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

# 合成的な FQDN / IP (実在組織を指さない、テスト用ダミー)
SYNTHETIC_AC_FQDN="a.b.testorg.ac.jp"
SYNTHETIC_GO_FQDN="x.y.testagency.go.jp"
SYNTHETIC_PRIVATE_IP="10.1.2.3"
SYNTHETIC_PRIVATE_IP_192="192.168.5.10"

# 1. 安全な内容なら 0 で抜ける
echo "## docs" > safe.md
echo "see example.ac.jp for academic format" >> safe.md
git add safe.md && git commit -q -m "safe"
if ! bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: safe content was flagged" >&2
  exit 1
fi

# 2. 合成 .ac.jp FQDN は検出される
echo "HostName ${SYNTHETIC_AC_FQDN}" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: synthetic .ac.jp FQDN was not flagged" >&2
  exit 1
fi

# 3. .go.jp FQDN も検出される
rm leak.md
echo "ProxyCommand ssh ${SYNTHETIC_GO_FQDN}" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: synthetic .go.jp FQDN was not flagged" >&2
  exit 1
fi

# 4. プライベート IP (10.x.x.x) は検出される
rm leak.md
echo "endpoint: ${SYNTHETIC_PRIVATE_IP}" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: 10.x.x.x private IP was not flagged" >&2
  exit 1
fi

# 5. プライベート IP (192.168.x.x) も検出される
rm leak.md
echo "host=${SYNTHETIC_PRIVATE_IP_192}" > leak.md
git add leak.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: 192.168.x.x private IP was not flagged" >&2
  exit 1
fi

# 6. example.ac.jp (ALLOW_LIST に登録された IANA 予約 TLD) はスルー
rm leak.md
echo "see example.ac.jp" > safe2.md
git add safe2.md && git commit -q -m "safe2"
if ! bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: allow-listed example.ac.jp was flagged" >&2
  exit 1
fi

# 7. --staged モードで staged 変更だけスキャン
echo "${SYNTHETIC_AC_FQDN}" > leak.md
git add leak.md
if bash "$SCRIPT" --staged >/dev/null 2>&1; then
  echo "FAIL: --staged mode missed staged leak" >&2
  exit 1
fi

# 8. allow-file マーカー付きファイルはスキャン対象外
git reset -q HEAD leak.md
rm leak.md
cat > intentional.md <<INNER
<!-- check-no-internal-hostnames: allow-file -->
# Examples of forbidden FQDNs (documentation only)
- ${SYNTHETIC_AC_FQDN}
INNER
git add intentional.md && git commit -q -m "intentional"
if ! bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: allow-file marker did not exempt the file" >&2
  exit 1
fi

# 9. マーカーなしの同内容ファイルは検出される (negative control)
rm intentional.md
git rm -q intentional.md 2>/dev/null || true
echo "- ${SYNTHETIC_AC_FQDN}" > leak_again.md
git add leak_again.md
if bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: missing allow-file marker should not be exempt" >&2
  exit 1
fi

echo "all scenarios passed"
