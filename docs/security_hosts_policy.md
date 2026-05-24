# インフラ識別情報を public リポジトリに書かない方針

<!-- このドキュメント自身が「具体名は伏せる」を実践する。検出器パターンも組織固有名を含めない。 -->

## 何を守るか

本リポジトリは public OSS であり、git history (PR / Issue / commit 本文 / diff) はすべて世界中から参照可能です。
**実 FQDN・組織ドメイン・ジャンプホスト名・プライベート IP・組織メールアドレス** などのインフラ識別情報が混入すると、以下のリスクが生じます:

- **組織特定**: ドメインから所属組織が逆引きできる
- **外部からの probe**: 攻撃者が DNS lookup → ポートスキャンに利用
- **OSINT 連鎖**: 著者の他リポジトリ・SNS と紐付けて行動範囲を推測可能
- **委託先・連携先の暴露**: ジャンプホスト名から内部ネットワーク構造を推測される

## 書いてはいけないカテゴリ (具体名は意図的に伏せる)

| カテゴリ | 例の形式 | なぜ NG か |
|---|---|---|
| 完全 FQDN | `<host>.<org>.<tld>` | DNS lookup で実在確認可能 |
| ジャンプ / 踏み台ホスト名 | 同上 | 内部ネットワーク構造を露出 |
| プライベート IP の具体値 | `10.X.Y.Z`, `192.168.X.Y`, `172.16-31.X.Y` | サブネット設計を露出 |
| 公的・組織グループドメイン | `.ac.jp` / `.go.jp` / `.lg.jp` 等の階層付き FQDN | 所属カテゴリの示唆 |
| 組織メールアドレス | `user@<organization-domain>` | 個人 + 所属の特定 |
| 社内システム識別子 | プロダクト名 + 環境名の組み合わせ | 内部命名規則の露出 |

> **本ドキュメント自身が原則を守ること**: 具体名 (どの大学・研究室・ホスト) は書かない。検出器スクリプトも具体名でなくカテゴリで判定する。

## 書いてよい例 (プレースホルダ)

```
<vllm-host>          各自が ~/.ssh/config で実値に差し替える
<jump-host>          同上
my-vllm              ホストエイリアス (任意の文字列、組織情報なし)
127.0.0.1:18001      localhost + ローカルポート
example.ac.jp        IANA 予約の教材用 TLD (ALLOW_LIST 済み)
192.0.2.1            RFC 5737 ドキュメント用 IP
```

## どこに実値を書くか

| 場所 | 用途 | リポジトリ管理 |
|---|---|---|
| `~/.ssh/config` | SSH Host エイリアスと FQDN | **なし** (ユーザーローカル) |
| `.env` (gitignored) | API endpoint URL / API key | **なし** (cp .env.example .env してから編集) |
| `~/.config/llm-rpg/` 等 | 各自の好みの設定 | **なし** |

## 自動チェック

`scripts/check_no_internal_hostnames.sh` が以下の**カテゴリ**を検出します (組織固有名は意図的に含めない):

- `.ac.jp` / `.go.jp` / `.lg.jp` 階層の 3 段 FQDN
- プライベート IP の具体値 (`10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`)

```bash
# 作業ツリー全体
bash scripts/check_no_internal_hostnames.sh

# ステージ済み変更だけ (commit 前)
bash scripts/check_no_internal_hostnames.sh --staged

# make 経由
make check-no-internal-hostnames
```

教材・サンプル URL (`example.ac.jp` 等の IANA 予約 TLD) は `ALLOW_LIST` (スクリプト内) に正規表現で追加して例外化できます。

**ファイル単位の例外**: 検出パターンを意図的に含めたいファイル (検出ロジック自身を試す test など) の先頭 30 行内に以下のコメントを 1 行入れます。

```text
# check-no-internal-hostnames: allow-file
```

(Markdown では `<!-- check-no-internal-hostnames: allow-file -->` 形式で OK)

新規ファイルにマーカーを足す場合は、**なぜ例外なのかの理由を併記**してください (本人や将来の自分・他人が後で監査できるように)。

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
