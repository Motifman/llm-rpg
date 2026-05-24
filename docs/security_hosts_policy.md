<!-- check-no-internal-hostnames: allow-file
このドキュメントは「書いてはいけない例」を意図的に掲載するため、本文中に
実 FQDN を含む。漏洩防止チェックの対象外として扱う。 -->

# インフラ識別情報を public リポジトリに書かない方針

## 何を守るか

本リポジトリは public OSS であり、git history (PR / Issue / commit 本文 / diff) はすべて世界中から参照可能です。
**実 FQDN・組織ドメイン・ジャンプホスト名などのインフラ識別情報** が混入すると、以下のリスクが生じます:

- **組織特定**: ドメインから所属研究室・大学が逆引きできる
- **外部からの probe**: 攻撃者が DNS lookup → ポートスキャンに利用
- **OSINT 連鎖**: 著者の他リポジトリ・SNS と紐付けて行動範囲を推測可能
- **委託先・連携先の暴露**: ジャンプホスト名から内部ネットワーク構造を推測される

## 書いてはいけない例

```
v108.fun.bio.keio.ac.jp         # NG: 完全な FQDN
tesla.fun.bio.keio.ac.jp         # NG: ジャンプホスト名
192.168.x.x / 10.x.x.x           # NG: プライベート IP の具体値
*.ac.jp / *.go.jp 系 FQDN         # NG: 組織グループを示唆
user@machine.internal-domain     # NG: メールアドレス + 内部ドメイン
```

## 書いてよい例 (プレースホルダ)

```
<vllm-host>                       # OK: 各自が ~/.ssh/config で実値に差し替える
<jump-host>                       # OK: 同上
my-vllm                           # OK: ホストエイリアス (任意の文字列、組織情報なし)
127.0.0.1:18001                   # OK: localhost + ローカルポート
example.ac.jp                     # OK: 教材用ダミー (ALLOW_LIST 済み)
```

## どこに実値を書くか

| 場所 | 用途 | リポジトリ管理 |
|---|---|---|
| `~/.ssh/config` | SSH Host エイリアスと FQDN | **なし** (ユーザーローカル) |
| `.env` (gitignored) | API endpoint URL / API key | **なし** (cp .env.example .env してから編集) |
| `~/.config/llm-rpg/` 等 | 各自の好みの設定 | **なし** |

## 自動チェック

`scripts/check_no_internal_hostnames.sh` が以下のパターンを検出します:

- `*.ac.jp` / `*.go.jp` / `*.lg.jp` 系の FQDN
- 既知 internal ラボドメイン (`fun.bio.*`, `tesla.fun.bio.*`)
- `*.keio.ac.jp`

```bash
# 作業ツリー全体
bash scripts/check_no_internal_hostnames.sh

# ステージ済み変更だけ (commit 前)
bash scripts/check_no_internal_hostnames.sh --staged

# make 経由
make check-no-internal-hostnames
```

教材・サンプル URL は `ALLOW_LIST` (スクリプト内) に正規表現で追加して例外化できます。

**ファイル単位の例外** (本ドキュメントのように「漏洩例」を意図的に掲載する場合): 対象ファイルの先頭 30 行内に以下のコメントを 1 行入れます。

```text
# check-no-internal-hostnames: allow-file
```

(Markdown では `<!-- check-no-internal-hostnames: allow-file -->` 形式で OK)

このリポジトリで現在マーカー指定されているのは:

- `docs/security_hosts_policy.md` (本ドキュメント。漏洩例を掲載するため)
- `tests/scripts/test_check_no_internal_hostnames.sh` (検出ロジックを試すため、テスト用ダミー FQDN を含む)

新規ファイルにマーカーを足す場合は、その理由をコメントに併記してください。

## pre-commit hook の推奨設定

`.git/hooks/pre-commit` (個人設定、リポジトリ管理外) に以下を追加:

```bash
#!/usr/bin/env bash
exec ./scripts/check_no_internal_hostnames.sh --staged
```

## 万一漏洩した場合

1. **既に push されていない**: `git commit --amend` / `git rebase` で書き換える
2. **push 済み (open PR)**: PR を close → ブランチを force-push でリベース → 新規 PR で対応 (`git push --force-with-lease`)
3. **main にマージ済み**: history rewrite は co-author の合意が必要。**rotate / takedown** を優先 (該当ホストの DNS を停止 / SSH key 更新 / 公開鍵リスト掃除)
4. **commit author email の組織ドメイン**: `git config user.email` を public 用に変更し、`git rebase -i` で過去のコミットを reset author

## 関連

- `scripts/check_no_internal_hostnames.sh`
- `tests/scripts/test_check_no_internal_hostnames.py` (CI gate)
- `.env.example` (placeholder のみ。実値は `.env` で各自管理)
