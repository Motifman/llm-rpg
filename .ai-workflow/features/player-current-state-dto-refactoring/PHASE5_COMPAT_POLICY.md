# Phase 5 Compat Policy

## Objective

`PlayerCurrentStateDto` の compat facade をどこまで残すかを固定し、今後の属性追加が再び top-level へ流れ込まないようにする。

## Canonical Ownership

- `world_state`
  - プレイヤー位置、現在 spot / area、visible world facts、移動候補、地形・天候・時刻、tile map、occupancy などの world facts
- `runtime_context`
  - harvest、conversation、skills、inventory、chest、guild、quest、shop、trade availability、tool-facing object list などの runtime / interaction context
- `app_session_state`
  - `active_game_app`、SNS / Trade mode state、virtual page kind、page snapshot JSON などの app-local session state

原則:

- world facts を app/session と混ぜない
- tool-facing に加工済みの実行文脈は `runtime_context` に置く
- 画面モードや仮想ページ状態は `app_session_state` に置く

## What Remains On Compat

当面は以下を維持する。

- `PlayerCurrentStateDto(...)` の既存 constructor 形
- `ToolAvailabilityContext = PlayerCurrentStateDto` の public 型契約
- LLM wiring や既存 fixture が受け渡す `PlayerCurrentStateDto` 本体
- 既存 top-level field / property access

理由:

- 既存テストには `PlayerCurrentStateDto(...)` を直接組み、top-level 属性を差し替えるものが残っている
- availability / UI / formatter は内部参照を sub DTO alias に寄せたが、public API まではまだ narrowing していない
- compat facade をすぐ剥がすより、「新規追加を sub DTO に閉じ込める」方が現在の価値が高い

## New Field Rules

新規項目追加時は以下を守る。

1. まず owner を `world_state` / `runtime_context` / `app_session_state` のどれかに決める
2. canonical な定義先は必ず sub DTO に置く
3. 新規 field を `PlayerCurrentStateDto` top-level に直接追加しない
4. top-level shortcut が必要なら、compat purpose を明記した property で露出する
5. shortcut を増やす前に、既存 consumer を sub DTO alias 参照へ寄せられないか確認する

補足:

- 新しい SNS / Trade / 他 app-local state は常に `app_session_state` に置く
- world 由来の生データから tool 用に加工した sibling list は `runtime_context` に置く
- heavy payload でも owner 判定は変えない。`visible_tile_map` や page snapshot JSON は optional でも canonical owner に属させる

## Shortcut Policy

shortcut の扱いは次のとおり。

- 既存 shortcut:
  - 互換維持のため残す
- 新規 shortcut:
  - 既存 public 契約を保つ必要がある場合のみ許容
- shortcut 廃止候補:
  - consumer がすべて `world_state` / `runtime_context` / `app_session_state` に移行した後に再評価

優先的な非推奨候補:

- SNS / Trade の page / snapshot 系 top-level access
- runtime list をそのまま露出している top-level access

ただし現時点では、deprecation warning や削除スケジュールまでは入れない。

## Consumer Guidance

新規実装・新規テストでは以下を優先する。

- formatter / resolver / builder 内部では `dto.world_state` / `dto.runtime_context` / `dto.app_session_state` を local alias 化して使う
- 新規テストの read side assertion では sub DTO access を優先する
- 既存 fixture が必要な場合のみ `PlayerCurrentStateDto(...)` の直接構築を使う

## Exit Criteria For Future Compat Reduction

compat 縮小を次に検討できる条件:

- main consumer が top-level shortcut に依存しなくなる
- constructor 直組み fixture が factory / helper に十分寄せられる
- `ToolAvailabilityContext` の public 契約変更可否が別 feature で整理される

この条件が揃うまでは、compat facade は「縮小対象」ではあっても「即削除対象」ではない。

## Outcome

Phase 5 時点の最終方針は次のとおり。

- canonical source of truth は sub DTO
- `PlayerCurrentStateDto` は当面 compat facade として維持
- 新規追加は sub DTO に閉じ込め、top-level の再膨張を防ぐ
