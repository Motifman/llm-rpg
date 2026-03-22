---
id: feature-player-current-state-dto-refactoring
title: PlayerCurrentStateDto の段階分割と互換維持リファクタリング
slug: player-current-state-dto-refactoring
status: idea
created_at: 2026-03-23
updated_at: 2026-03-23
source: flow-idea
branch: null
related_idea_file: null
---

# Goal

- `PlayerCurrentStateDto` の肥大化を抑え、**責務ごとの小さな read model** に分割できる形へ寄せる。
- ただし一気に置き換えるのではなく、**LLM 向け既存契約を壊さず**に段階移行できるリファクタリング方針を定める。
- 将来 SNS / Trade / 他アプリ状態が増えても、`PlayerCurrentStateDto` に属性を足し続けなくてよい構造を目指す。

# Success Signals

- `availability_resolvers`、`ui_context_builder`、formatter 群の既存利用を大きく壊さず、**内側の責務分割**を始められる。
- `PlayerCurrentStateBuilder` の組み立て責務が、**world state / runtime context / app session state** などの単位に分けて説明できる。
- SNS / Trade のような追加コンテキストを、`PlayerCurrentStateDto` のトップレベル属性を増やす代わりに、**専用サブ DTO または専用コンテキスト**として扱う方針が定義される。
- plan 時に、**互換レイヤをどこに置くか**と**段階的削除の順序**が決められる。

# Non-Goals

- `PlayerCurrentStateDto` をこの段階で即廃止すること。
- `availability_resolvers`、prompt formatter、各種テストを**一括で全面書き換え**ること。
- SNS / Trade のモード仕様そのものを再設計すること。

# Problem

1. `PlayerCurrentStateDto` が、位置・天候・地形・視界・移動候補・所持品・会話・クエスト・ギルド・ショップ・取引・SNS/Trade 画面状態まで持っており、**単一 DTO の責務が広すぎる**。
2. `PlayerCurrentStateBuilder` もそれに引きずられ、**world state の組み立て**と**runtime UI/LLM 用コンテキストの組み立て**と**アプリ画面セッションの吸い上げ**を 1 つの返却 DTO に集約している。
3. `availability_resolvers` と `ui_context_builder` が `PlayerCurrentStateDto` のトップレベル属性へ直接依存しており、DTO の肥大化が**利用側の結合**も強めている。
4. 最近の SNS / Trade 追加でも `active_game_app`、`sns_virtual_page_kind`、`trade_current_page_snapshot_json` などが同 DTO に積み増されており、今後も同じ増え方をすると**DTO がモード管理の受け皿**になり続ける。

# Constraints

- **互換優先**: ユーザー合意として、まず重視するのは **LLM 向け互換維持**。既存 formatter / resolver 契約を急に壊さない。
- **既存コードの依存先が多い**: `availability_resolvers.py`、`ui_context_builder.py`、`current_state_formatter` 系、`world_query_service` テスト群などで直接参照が多い。
- **builder は既に部分分離の芽がある**: `PlayerRuntimeContextBuilder` があり、inventory / quest / guild / trade / skill などは別 facade へ一部退避されている。全面再設計より、**この延長で分割を進める**のが自然。
- **モード状態は増えやすい**: SNS / Trade の page snapshot 類は今後も派生しやすいため、トップレベル属性のままでは拡張コストが高い。

# Code Context

| 領域 | モジュール・観測 |
|------|------------------|
| 肥大化した DTO 本体 | `src/ai_rpg_world/application/world/contracts/dtos.py` の `PlayerCurrentStateDto` |
| DTO 組み立て | `src/ai_rpg_world/application/world/services/player_current_state_builder.py` |
| runtime context の部分分離 | `src/ai_rpg_world/application/world/services/player_runtime_context_builder.py` |
| 利用可否判定の直接依存 | `src/ai_rpg_world/application/llm/services/availability_resolvers.py` |
| UI ラベル・ref 文脈の直接依存 | `src/ai_rpg_world/application/llm/services/ui_context_builder.py` |
| 既存テストの依存 | `tests/application/world/services/test_world_query_service.py`、`tests/application/llm/test_availability_resolvers.py`、`tests/application/llm/test_ui_context_builder.py` ほか |

**調査メモ**:

- `PlayerCurrentStateDto` は現在、少なくとも以下の塊を同居させている。
  - **World state**: current spot, coordinates, weather, terrain, visible objects, moves
  - **Runtime context**: inventory, chest, conversation, harvest, skills, quests, guild, shop, trade summaries
  - **App session state**: `active_game_app`, SNS page 状態、Trade page 状態
- `PlayerRuntimeContextBuilder` は既に supplemental builder への facade であり、**runtime context の外出し先として使える足場**になっている。
- 一方で `availability_resolvers` は `context.inventory_items` や `context.available_trades`、`context.sns_virtual_page_kind` を直接見るため、**分割するなら adapter/compat property が必要**になる。

# Options Considered

- **A. 互換ファサードを残しつつ内側を分割する**
  - 例: `PlayerCurrentStateDto` 自体は入口として残し、内部に `world_state`, `runtime_context`, `app_session_state` のようなサブ DTO を持たせる。
  - 既存のトップレベル属性は、当面は property や委譲で互換維持する。

- **B. 用途別 DTO に完全分離する**
  - 例: `ToolAvailabilityContextDto`, `PromptCurrentStateDto`, `UiContextDto` に分け、利用側も全面移行する。
  - 設計としてはきれいだが、今回の成功条件である「互換維持」と相性が弱い。

- **C. DTO は維持し、builder だけ整理する**
  - まず builder 内だけを段階分割し、DTO 自体の属性構造は変えない。
  - リスクは低いが、属性肥大化そのものへの効きが弱い。

# Decision Snapshot

- **Proposal**:
  - 第一候補は **A を主軸にしつつ、初手は C に近い段階導入**。
  - 具体的には、`PlayerCurrentStateBuilder` が返す内容を概念的に
    - `PlayerWorldStateDto`
    - `PlayerRuntimeContextDto`
    - `PlayerAppSessionStateDto`
    に分ける。
  - そのうえで `PlayerCurrentStateDto` は当面 **compat facade / aggregate DTO** として残し、既存利用箇所にはトップレベル property を提供する。
  - 新規追加項目、とくに SNS / Trade / 将来の app 状態は、原則トップレベル追加ではなく **`app_session_state` 側へ閉じ込める**。

- **Selected option**: **A**

- **Why this option now**:
  - ユーザー合意として、まずは **段階分割**と**LLM 向け互換維持**が重要。
  - 既に `PlayerRuntimeContextBuilder` という分離の足場があり、ゼロからの全面再設計より安全。
  - 最近の app mode 拡張が DTO 膨張の主要因になっており、**今止めておく価値が高い**。

# Proposed Refactoring Shape

## 1. 責務境界の固定

- `PlayerWorldStateDto`
  - 位置、スポット、天候、地形、視界、移動候補、注意レベル、busy/path など
- `PlayerRuntimeContextDto`
  - inventory, chest, conversation, harvest, skill, quest, guild, shop, trade summary など
- `PlayerAppSessionStateDto`
  - `active_game_app`、SNS page state、Trade page state、将来の app-local snapshot

## 2. 互換レイヤ

- `PlayerCurrentStateDto` はしばらく残す。
- 内部に上記 3 つの sub DTO を保持し、既存呼び出しで必要な属性は property 経由で露出する。
- 既存テスト資産が多いため、最初の phase では **呼び出し側の import/型をほぼ変えない**。

## 3. builder 分割

- `PlayerCurrentStateBuilder` から、少なくとも以下の private builder か専用 service を切り出す。
  - world state builder
  - app session state builder
  - compat aggregator
- `PlayerRuntimeContextBuilder` は現行のまま活かし、runtime 側の代表入口として利用する。

## 4. 利用側の寄せ先を決める

- `availability_resolvers` は最終的に `ToolAvailabilityContextDto` 相当へ寄せる余地があるが、初手は `PlayerCurrentStateDto` の compat property を使う。
- `ui_context_builder` は runtime context 依存が濃いので、将来的な第一分離先候補。
- formatter は world state と app session を読む箇所を分けやすい。

# Open Questions

1. `PlayerCurrentStateDto` の互換レイヤを **dataclass の property** で持つか、**明示的な adapter class** を別で置くか。
2. `available_trades` のような「runtime context だが LLM availability にも使う項目」を、runtime 側へ寄せた上でどこまで shortcut property を残すか。
3. `visible_tile_map` や `sns_current_page_snapshot_json` のような重い payload を、compat DTO に常駐させるか、オプション取得にさらに分けるか。
4. `PlayerCurrentStateDto` を今後も world query の公開契約として残すのか、それとも最終的には用途別 DTO 群へ置換するのか。

# Alignment Notes

- **Initial interpretation**:
  - ユーザー意図は「属性数が多い DTO を今後も膨らませないための安全な分割案を考えたい」。
  - コード上は DTO 単体より、builder と availability/UI 側の直接依存が重く、**単純な dataclass 分割だけでは不十分**。

- **User-confirmed intent**:
  - 重視したい方向は **段階分割**。
  - 成功は **LLM 向け互換維持**を保ちながら見通しを良くすること。
  - 今回の非目標は **大規模呼び出し変更**。

- **Assumptions**:
  - 直近では SNS / Trade まわりの追加が続くため、`app_session_state` の切り出し価値が高い。
  - `PlayerRuntimeContextBuilder` の存在を活かす方が、別 DTO 完全新設より repo の流れに合う。

- **Reopen alignment if**:
  - ユーザーが「互換は不要なので一気に用途別 DTO に分解したい」と判断したとき。
  - `PlayerCurrentStateDto` が LLM 以外の外部公開契約として固定されており、property ベース互換では扱いにくいと分かったとき。
  - app session ではなく、runtime context 側の方が主要な痛みだと plan 調査で判明したとき。

# Promotion Criteria

- [ ] `PlayerCurrentStateDto` の属性を **world / runtime / app session** のどこへ属させるか一覧化できている
- [ ] 互換維持の方法を **property 委譲**か **adapter**かで決めている
- [ ] `PlayerCurrentStateBuilder` の分割単位と、初手で触るファイル範囲が決まっている
- [ ] `availability_resolvers` / `ui_context_builder` / formatter のうち、どこを phase 1 の対象にするか決まっている
- [ ] 重い payload を常時 DTO に載せるかどうかの方針が決まっている

# Promotion

- Next step: `flow-plan` で feature 化し、`PlayerCurrentStateDto` の全属性棚卸し、sub DTO 案、compat 方針、phase 分割（builder 抽出 → compat 導入 → 利用側整理）を `PLAN.md` に落とす。
