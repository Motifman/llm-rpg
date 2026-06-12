# Research threads

> このディレクトリは **別スレッドで議論する話題の起点メモ** を集める場所。
>
> 「設計判断」「実装計画」とは区別する:
> - `docs/design_decisions.md` = 既に決めた判断と理由
> - `docs/memory_system/*_plan.md` 等 = 着手中 / 着手予定の実装計画
> - **`docs/research_threads/`** = まだ議論段階。実装に降ろすかどうかも未確定

各ファイルは「次に何を議論したいか」を整理した状態保存。実装に降りる準備が
できたら **新しい計画 doc / PR に切り出し**、ここに完了スタンプを残す。

## 現在の起点

| ファイル | 主題 | 起点となった会話 |
|---|---|---|
| [active_inference_and_predictive_error_learning.md](active_inference_and_predictive_error_learning.md) | 能動的推論 / 自由エネルギー原理を LLM agent に持ち込めるか | 2026-06-13: 「予測の方は人間が予測との誤差から学習するという知見から考えてみた」 |
| [dynamic_hierarchical_planning.md](dynamic_hierarchical_planning.md) | 動的な階層的計画と L4/L5 への統合 | 2026-06-13: 「プランは動的に変化していく必要がある。L4, L5 にプランを入れる話もありか?」 |

> 2026-06-13: 上記 2 スレッドは統合実装計画
> [docs/being_architecture_master_plan.md](../being_architecture_master_plan.md)
> に昇格した (議論ポイントへの決定一覧は同 doc §10)。計画レビュー合意後に
> 完了スタンプを付ける。

## 使い方

1. 議論したい話題が出たら、このディレクトリに新規 .md を作る
2. 「なぜこのスレッドが立ったか」「議論したいポイント」「次にやること候補」を書く
3. 別のセッションで議論を再開する際、その doc を最初に読み込む
4. 議論が収束して実装に降りたら、対応する計画 doc / PR を切り、本 doc に
   「完了スタンプ + 移行先リンク」を追記する

## 関連

- 既に降りた研究: `docs/memory_system/` (短期 / 長期記憶)
- 既に降りた研究: `docs/agent_continuity_roadmap/` (連続的存在)
- 設計判断の集約: `docs/design_decisions.md`
