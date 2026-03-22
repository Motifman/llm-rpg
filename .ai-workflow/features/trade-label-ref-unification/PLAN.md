---
id: feature-trade-label-ref-unification
title: Trade の `trade_label` / `trade_ref` 契約一本化
slug: trade-label-ref-unification
status: planned
created_at: 2026-03-22
updated_at: 2026-03-22
branch: codex/trade-label-ref-unification
---

# Objective

`trade_accept` / `trade_cancel` / `trade_decline` の対象指定を `trade_ref` に一本化し、`trade_label` 互換パスによる二重管理を解消する。あわせて、取引所仮想ページの page-local ref 契約と説明文を SNS 仮想ページと同じ発想に揃え、LLM が「現在のスナップショットから `r_trade_*` をコピーして使う」流れを迷わず実行できる状態にする。

# Success Criteria

- `trade_accept` / `trade_cancel` / `trade_decline` のツール定義から `trade_label` が消え、`trade_ref` だけが外部契約として見える。
- `guild_shop_trade_resolver` と `trade_executor` に `trade_label` 前提の mutation 解決経路が残らない。
- current state / prompt / availability 上で、LLM に `T*` ラベルを actionable な取引対象として見せないか、少なくとも mutation 契約と矛盾しない形に整理される。
- `tests/application/llm/test_tool_definitions.py`、`test_available_tools_provider.py`、`test_tool_command_mapper.py`、必要に応じて wiring / current-state 系テストで `trade_ref` 契約が固定される。

# Alignment Loop

- Initial phase proposal:
  - まず public contract と露出面の曖昧さを潰し、その後に内部解決経路とテストを `trade_ref` 一本へ畳む 3 phase 案を想定した。
- User-confirmed success definition:
  - 識別子は LLM にとって簡潔で、一貫していることを優先する。
  - tool description / refresh 文言の統一も同 feature に含める。
- User-confirmed phase ordering:
  - 3 phase ではなく 2 phase に圧縮する。
- Cost or scope tradeoffs discussed:
  - `available_trades` と `TradeToolRuntimeTargetDto` の `T*` ラベルが current state 側に残っているため、単に executor だけ直すと「見えるが使えない」ラベルが残る。
  - `trade-page-tool-gating` 完了済みの基盤を前提にできる一方、definition / provider / mapper / wiring テストの更新範囲は広い。

# Scope Contract

- In scope:
  - `trade_accept` / `trade_cancel` / `trade_decline` の public contract を `trade_ref` のみに揃える
  - `guild_shop_trade_resolver` / `trade_executor` の `trade_label` mutation 経路を削除または責務整理する
  - `available_trades`、availability resolver、UI current context の trade mutation 導線を `trade_ref` 契約と整合させる
  - `trade_ref` と `trade_page_refresh` の説明文を SNS 仮想ページ系と同じスタイルへ寄せる
  - 関連テストの追加・更新
- Out of scope:
  - Guild / Shop / SNS など他機能の label/ref 契約変更
  - `inventory_item_label`、`target_player_label`、`listing_label` など別用途ラベルの改名
  - `r_trade_*` の命名変更や page session アーキテクチャの作り直し
  - ドメイン層に新しい識別子概念を持ち込むこと
- User-confirmed constraints:
  - 後方互換は不要とみなし、`trade_ref` 一本化を優先する
  - LLM の識別しやすさを最優先にし、他仮想ページの `r_*` 系と一貫させる
  - 文言統一も今 feature に含める
- Reopen alignment if:
  - `available_trades` ベースの非ページ mutation 導線を正式に残す必要が判明した場合
  - `trade_ref` 単独では運用上識別しづらく、新しい短縮表示を併記する必要が出た場合
  - `trade_page_tool_gating` の既存テスト前提が想定以上に崩れ、phase を分割し直す必要が出た場合

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
  - `src/ai_rpg_world/application/llm/services/executors/trade_executor.py`
  - `src/ai_rpg_world/application/llm/services/_argument_resolvers/guild_shop_trade_resolver.py`
  - `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - `src/ai_rpg_world/application/llm/services/ui_context_builder.py`
  - `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
- Existing exceptions, events, inheritance, and test patterns to follow
  - `TradePageSessionService.resolve_trade_ref` を通す page-local ref 解決パターン
  - `invalid_arg_result(...)` を使う executor のエラー返却パターン
  - `test_tool_definitions.py` の schema/assertion スタイル
  - `test_tool_command_mapper.py` の missing arg / invalid arg 回帰テスト
  - `test_available_tools_provider.py` / `test_sns_mode_wiring_e2e.py` の availability 契約テスト
- Integration points and known risks
  - `available_trades` は current state と predictive memory にも使われており、mutation 導線だけを消すのか、表示自体も縮退するのかを見極める必要がある
  - `TradeToolRuntimeTargetDto` を完全に不要化できるか、読み取り用途として残すかで UI context の修正量が変わる
  - `trade_executor` は内部的に `trade_id` を扱うため、外部契約を `trade_ref` に絞ってもアプリケーション層内部の責務分担は維持する必要がある

# Risks And Unknowns

- `available_trades` の `T*` 表示を残したまま mutation 契約だけ変えると、LLM が誤って古いラベルを使う恐れがある。
- description 文言だけを変えても、availability や error message が追従しないと一貫性が崩れる。
- `trade_label` 経路を消した結果、想定外の非ページテストや downstream fixture が壊れる可能性がある。
- predictive memory や current state サマリに trade 情報をどこまで残すかで実装範囲が増減する。

# Phases

## Phase 1: Public Contract を `trade_ref` に固定する

- Goal:
  - LLM から見える取引 mutation 契約を `trade_ref` のみに揃え、`trade_label` と `T*` の混在をなくす。
- Scope:
  - `tool_catalog/trade.py` から `trade_label` を外し、`trade_ref` の説明を page-local ref 前提で書き直す
  - `trade_page_refresh` と関連 description を SNS 仮想ページに揃えた文面へ寄せる
  - `availability_resolvers.py` の fallback 条件を見直し、仮想ページ前提の露出と矛盾しないようにする
  - `ui_context_builder.py` / current state 側の `T*` trade label を mutation 導線から外すか、誤誘導しない表示へ縮退する
- Dependencies:
  - `trade-page-tool-gating` の完了済み基盤
- Parallelizable:
  - 中程度
- Success definition:
  - definition / prompt / availability のどこを見ても、取引 mutation の対象指定は `trade_ref` だと読み取れる。
- Checkpoint:
  - `test_tool_definitions.py` と availability 系テストで `trade_label` 非露出が確認できる。
- Reopen alignment if:
  - `available_trades` を読み取り用途でも残すことが、かえって混乱を増やすと判明した場合
- Notes:
  - `inventory_item_label` や `target_player_label` は仮想ページ行 ref とは別の層なので、この phase では触らない。

## Phase 2: 内部解決経路と回帰テストを一本化する

- Goal:
  - `trade_label` 前提の内部配線を取り除き、`trade_ref` 契約をテストと実装の両方で固定する。
- Scope:
  - `guild_shop_trade_resolver.py` の `_resolve_trade_label` を mutation 用として廃止または `trade_ref` 専用に整理する
  - `trade_executor.py` の missing arg / invalid arg 文言を `trade_ref` 前提へ更新し、label fallback を除去する
  - `test_tool_command_mapper.py` の失敗系期待値を `trade_ref` のみに更新する
  - 必要に応じて `test_available_tools_provider.py`、`test_sns_mode_wiring_e2e.py`、`test_llm_wiring_integration.py`、prompt/current-state 系テストを更新する
  - 不要になった `TradeToolRuntimeTargetDto` 利用箇所やコメントを縮退する
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - mutation の対象解決で `trade_label` がコードパス上に残らず、関連テストが `trade_ref` 契約だけを検証する。
- Checkpoint:
  - LLM 層の関連テスト群が通り、`trade_label` を要求・許容する assertion が消えている。
- Reopen alignment if:
  - world current state 側の trade summary をこの feature で残すべきか削るべきか、実装中に影響範囲が大きく変わった場合
- Notes:
  - アプリケーション層内部で `trade_id` に変換して service を呼ぶ構造自体は維持してよい。外部契約だけを `trade_ref` に揃えるのが主目的。

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- No hidden `trade_label` fallback remains in LLM-facing mutation flow
- Current state / prompt wording does not advertise unsupported trade identifiers

# Execution Deltas

- Change trigger:
  - `available_trades` や predictive memory の扱いが想定より大きく、取引情報の表示戦略まで変える必要が出たとき
- Scope delta:
  - current state から `available_trades` 自体を外す
  - `TradeToolRuntimeTargetDto` を他用途からも除去する
  - `r_trade_*` の命名規則変更を含める
- User re-confirmation needed:
  - `trade_ref` とは別の短縮識別子を新設するとき
  - `available_trades` の表示そのものを削除するとき
  - predictive memory での trade 表示方針まで変えるとき

# Plan Revision Gate

- Revise future phases when:
  - `available_trades` / current state 側の扱いが単なる表示調整を超えて、独立 phase が必要な規模に広がるとき
  - `trade_ref` 契約だけでは不十分で、新たな識別子や detail page を導入する必要が出たとき
- Keep future phases unchanged when:
  - service 名や helper 分割だけが変わり、公開契約と checkpoint が同じままのとき
- Ask user before editing future phases or adding a new phase:
  - `trade_ref` 一本化をやめる
  - 取引 summary の表示戦略を大きく変える
  - 他機能の label/ref 整理へスコープを広げる
- Plan-change commit needed when:
  - phase 数を増減させるとき
  - `available_trades` の扱いを scope contract から外す / 追加するとき
  - `trade_ref` 以外の識別子を正式契約に採用するとき

# Change Log

- 2026-03-22: Initial plan created
- 2026-03-22: Promoted idea into 2-phase plan focused on `trade_ref` unification, wording alignment, and cleanup of dangling `T*` mutation cues
