# Phase 3 Consumer Dependency Plan

## Objective

Phase 4 で `formatter` / `availability` / `UI builder` を更新するときに、どこまで sub DTO 直参照へ寄せるかを先に固定する。

## Consumer Summary

| Consumer | Current dependency shape | Recommended landing | Reason |
|----------|---------------------------|---------------------|--------|
| `current_state_formatter.py` | `PlayerCurrentStateDto` の top-level を直接参照 | 関数冒頭で `world = dto.world_state`, `runtime = dto.runtime_context`, `app = dto.app_session_state` を束縛し、以後は原則その 3 つを参照 | 参照数が少なく、world 主体なので移行コストが低い |
| `availability_resolvers.py` | `PlayerCurrentStateDto` top-level へ大量直接依存 | 入力型は当面 `PlayerCurrentStateDto` のまま維持し、resolver family 単位で `world` / `runtime` / `app` ローカル参照へ段階置換 | `ToolAvailabilityContext = PlayerCurrentStateDto` 契約を壊さず、変更面を制御できる |
| `ui_context_builder.py` | `PlayerCurrentStateDto` top-level へ runtime 中心の強依存 | 関数冒頭で `world` / `runtime` / `app` を束縛し、内部 helper ごとに順次置換 | runtime 依存が最も強いが、入力型変更なしで内部だけ寄せられる |

## Recommended Phase 4 Order

1. `current_state_formatter.py`
2. `ui_context_builder.py`
3. `availability_resolvers.py`

理由:

- formatter は参照点が少なく、world 主体で安全に着手できる
- UI builder は runtime 依存が強いが、helper 境界があり段階置換しやすい
- availability resolvers は件数が多く、tool gating 契約へ直結するため最後に回す方が安全

## Detailed Decisions

### 1. `current_state_formatter.py`

- Phase 4 でやること:
  - `dto.world_state` を主参照にする
  - `active_harvest`、`notable_objects`、`actionable_objects` は `dto.runtime_context` を使う
  - SNS / Trade snapshot は `dto.app_session_state` を使う
- top-level compat を残す対象:
  - なし。formatter 内は原則すべて local alias 経由へ寄せる
- Residual risk:
  - 少ない。出力文言自体は変えない前提

### 2. `ui_context_builder.py`

- Phase 4 でやること:
  - `current_state.world_state` / `current_state.runtime_context` / `current_state.app_session_state` を冒頭で束縛
  - inventory / chest / conversation / skills / quests / guild / shops / trades は `runtime`
  - `x` / `y` / `z` / `current_spot_id` / `area_ids` / `visible_objects` / `available_moves` / `available_location_areas` は `world`
  - Trade page gating は `app`
- top-level compat を残す対象:
  - helper 呼び出しシグネチャ上、`current_state` 本体を受ける private method は残してもよい
  - ただし helper の中でも順次 `world` / `runtime` / `app` へ束縛して使う
- Residual risk:
  - runtime target label の生成に相対座標や spot id が混じるため、world/runtime 境界の取り違えに注意

### 3. `availability_resolvers.py`

- Phase 4 でやること:
  - 入力型は `Optional[PlayerCurrentStateDto]` のまま維持
  - resolver family ごとに local alias を束縛する
  - world 系:
    - movement / inspect / harvest start-stop / location gating
  - runtime 系:
    - inventory / chest / skills / quests / guild / shops / trades
  - app 系:
    - SNS / Trade mode and page gating
- top-level compat を残す対象:
  - contract とテスト fixture の単純さのため、resolver public API は維持
  - 個別 resolver 内で top-level property を完全排除できない場合は、compat 利用を許容
- Residual risk:
  - resolver 数が多いため、機械的置換ではなく family 単位で進める

## Resolver Family Map

| Family | Primary owner |
|--------|---------------|
| movement / pursuit / inspect target | `world` |
| harvest / conversation / attention | `runtime` + 一部 `world` |
| inventory / chest / placeable | `runtime` |
| skills / awakened / proposals | `runtime` |
| quests / guild / shops / trades | `runtime` + 一部 `world.area_ids/current_spot_id` |
| sns / trade mode gating | `app_session` |

## What Stays On Compat For Now

- `ToolAvailabilityContext = PlayerCurrentStateDto` の型契約
- `PlayerCurrentStateDto(...)` を直接組む既存 fixture / test helper
- LLM wiring など `PlayerCurrentStateDto` を受け渡す public API

## Phase 4 Concrete Change List

### `current_state_formatter.py`

- `dto.` 直参照を local alias 化する
- 参照分類:
  - `world`: spot, area, coords, player count, connections, time, weather, terrain, tile map, moves, attention, busy/path
  - `runtime`: harvest, notable/actionable count
  - `app`: sns/trade snapshot JSON

### `ui_context_builder.py`

- `build()` 冒頭に `world`, `runtime`, `app` を束縛
- private helper 呼び出し引数を必要に応じて分割する
- Trade mode 分岐は `app.is_trade_mode_active` / `app.trade_virtual_page_kind` を使う

### `availability_resolvers.py`

- resolver family ごとに:
  - `world = context.world_state`
  - `runtime = context.runtime_context`
  - `app = context.app_session_state`
  を導入する
- 一気に全 resolver を書き換えず、family 単位で変更する

## Plan Revision Check

- 不要
- 理由:
  - consumer 3 系統とも、入力型を維持したまま内部参照だけを新境界へ寄せられる
  - phase 順序の前提も壊れていない
  - 追加の必須 phase は発生していない
