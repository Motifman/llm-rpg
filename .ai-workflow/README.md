# AI Workflow

Codex と Cursor の両方で共通利用する、軽量な feature 実装ワークフローです。

このディレクトリは単なる一時メモ置き場ではありません。会話で失われやすい判断、実装計画、進捗、レビュー結果を Markdown 成果物として蓄積し、次のターンや別エージェントに引き継ぐための作業基盤です。

## 目的

- `flow-` プレフィックスで一貫した操作感を保つ
- 会話だけに依存せず、Markdown 成果物で状態を引き継ぐ
- 実装途中の抜け漏れを `flow-status` / `flow-doctor` で検知する
- GSD ほど重くしすぎず、必要なところだけ構造化する
- 日本語前提で運用し、毎回「日本語で」と付け足さなくてもよい状態にする
- ユーザーとエージェントの認識ギャップを小さく保つ

## ディレクトリ構造

```text
.ai-workflow/
  README.md
  ideas/
    2026-03-15-example-idea.md
  features/
    example-feature/
      IDEA.md
      PLAN.md
      PROGRESS.md
      REVIEW.md
      SUMMARY.md
  templates/
    IDEA.md
    PLAN.md
    PROGRESS.md
    REVIEW.md
    SUMMARY.md
  references/
    questioning.md
    subagents.md
    review-standard.md
  scripts/
    flow.py
```

## ワークフロー全体像

1. `flow-idea`
   - アイデアを対話で具体化する
   - 関連コードを軽く調査する
   - `ideas/` に日付付きのアイデアメモを残す
   - 実装前の曖昧さを整理する
   - 少なくとも 1 回は質問ループを回して、目的と成功条件を合わせる

2. `flow-plan`
   - アイデアを feature に昇格させる
   - `features/<slug>/` を作る
   - `PLAN.md` に phase、成功条件、懸念点、既存コードの参照先を整理する
   - 実装準備が整った時点で専用ブランチに乗せる
   - draft plan を一度ユーザーにぶつけ、phase 分けや成功条件のズレを潰す

3. `flow-exec`
   - 指定 phase を実装する
   - 既存コードの構造、継承、例外、イベント、テスト形式に合わせる
   - 実装中の発見を `PLAN.md` と `PROGRESS.md` に反映する
   - phase ごとにテストとコミットを行う
   - 実装中の観測情報と plan の差分を整理し、次 phase へ引き継ぐ

4. `flow-review`
   - DDD、例外処理、仮実装禁止、テストの厳しさを点検する
   - 指摘を `REVIEW.md` に残す
   - 問題があれば phase を追加するか plan に差し戻す

5. `flow-ship`
   - `SUMMARY.md` を整える
   - push、PR、main 直 merge など、最後の出荷動線を整理する
   - 未解決事項があれば明示する

6. `flow-status`
   - feature の現在地と次アクションを要約する
   - 再開時の入口として使う

7. `flow-doctor`
   - ワークフローの抜け漏れを検知する
   - 足りない artifact や構造不足を見つける

## 命名規則

- skill 名はすべて `flow-*`
- `ideas/` のファイル名は `YYYY-MM-DD-slug.md`
- `features/` のディレクトリ名は安定した slug を使う
- feature の日付はディレクトリ名ではなく frontmatter の `created_at` で管理する

## feature の状態

`features/<slug>/IDEA.md` の frontmatter `status` を基準に進行管理します。

- `idea`
- `planned`
- `in_progress`
- `review`
- `done`
- `dropped`

## artifact の役割

- `IDEA.md`
  - なぜやるのか、何が問題か、何を明確化すべきかを残す
- `PLAN.md`
  - 実装戦略、phase 分割、成功条件、懸念点を残す
- `PROGRESS.md`
  - どこまで終わったか、どの commit か、何を学んだかを残す
- `REVIEW.md`
  - 実装とテストの問題点、追加対応の要否を残す
- `SUMMARY.md`
  - 最終的に何を出荷したか、何が残っているかを残す

## 参照ファイル

SKILL.md を必要以上に肥大化させないため、詳細ルールは `references/` に分ける。

- `references/questioning.md`
  - どの skill で、どの粒度で質問するか
- `references/subagents.md`
  - サブエージェントをどこで使い、どこで使いすぎないか
- `references/review-standard.md`
  - review 時に守る厳しめの基準
- `references/alignment-loop.md`
  - idea、plan、exec でズレをどう解消するか

## スクリプト

### アイデアファイルを作る

```bash
python .ai-workflow/scripts/flow.py new-idea --slug guild-market
```

### feature の骨組みを作る

```bash
python .ai-workflow/scripts/flow.py init-feature --slug guild-market
```

### 現在地を確認する

```bash
python .ai-workflow/scripts/flow.py status --slug guild-market
```

### 抜け漏れを検知する

```bash
python .ai-workflow/scripts/flow.py doctor --slug guild-market
python .ai-workflow/scripts/flow.py doctor
```

## サブエージェント

サブエージェントは常用ではなく、効果が高い場面だけ使います。

- `flow-plan`: コード調査と懸念洗い出しを並列化してよい
- `flow-review`: 実装レビューとテストレビューを分けてよい
- `flow-exec`: 基本はメインで実装し、必要なときだけ補助的に使う

## 運用メモ

- このディレクトリの Markdown は一時メモではなく成果物として扱う
- `docs/` には恒久ドキュメントを置き、このディレクトリには workflow artifact を置く
- skill は薄く、揺れやすい手順は script で固定する
- 詳細ルールは `references/` に逃がし、SKILL.md は呼び出し判断と手順の要点に集中させる
