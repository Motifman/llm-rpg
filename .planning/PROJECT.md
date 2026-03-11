# AI RPG World

## What This Is

LLMエージェントがプレイヤーとして行動するテキストRPGワールド管理システムです。v1.0 では、既存の移動・観測・イベント駆動基盤を保ったまま、動いている主体を対象にした pursuit 機能をプレイヤー/モンスター両方で扱えるようにしました。

## Core Value

LLMエージェントが、静的な目的地指定だけでなく、動的に移動する主体に対しても一貫した状態遷移とイベント駆動で行動を継続できること。

## Current State

- **Shipped milestone:** v1.0 (`2026-03-12`)
- **Delivered scope:** pursuit domain vocabulary, player pursuit commands, continuation loop, observation/LLM delivery, monster pursuit alignment, live runtime assembly, audit evidence closure
- **Planning state:** v1.0 archived, next milestone not started
- **Audit state:** `.planning/v1.0-MILESTONE-AUDIT.md` updated and ready for milestone closeout
- **Known follow-up debt:** Phase 1 Nyquist validation artifact is still missing; busy-state timing and async event failure visibility remain future hardening topics

## Next Milestone Goals

- `ADVP-01`: `follow` / `chase` の振る舞い差分を詳細化する
- `ADVP-02`: pursuit pause/resume や自動再開ポリシーを扱えるようにする
- `ADVP-03`: last-known 以降の探索・再捕捉ロジックを拡張する
- `GRUP-01`: 複数主体の隊列追従や間隔制御に広げる
- `GRUP-02`: 味方追従と敵追跡の切替条件を整理する

## Constraints

- **Tech stack**: 既存の Python レイヤード/DDD 風構成を維持する
- **Architecture**: ドメインイベント駆動を維持する
- **Scope**: 次マイルストーンは v1 pursuit を壊さず拡張する
- **Behavior**: 新機能も構造化イベントと LLM 再駆動の整合を守る
- **Quality**: 新しい追跡拡張は live runtime path と verification artifact まで含めて閉じる

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 追跡状態は静的移動状態から分離する | pursuit と destination/path を混同しないため | ✓ Good |
| `cancelled` は failure reason ではなく独立イベントとして扱う | LLM が中断と失敗を区別できるようにするため | ✓ Good |
| プレイヤー pursuit の live runtime は専用 composition entrypoint で閉じる | optional wiring のままでは監査を通らないため | ✓ Good |
| `OBSV-02` の最終受け入れは runtime closure まで待つ | observation wiring 単体では E2E が閉じないため | ✓ Good |
| v1 の完了条件は「追跡状態とイベントが正しく回ること」 | guaranteed capture は初期要件に向かないため | ✓ Good |

## Archived Context

<details>
<summary>Pre-v1.0 charter</summary>

既存コードベースは `src/ai_rpg_world` 以下で `domain`、`application`、`infrastructure` に分かれたレイヤード構成です。ユースケースはアプリケーションサービスとイベントハンドラで組まれ、永続化やイベント配送はインフラ層の in-memory 実装や LLM 関連アダプタで支えられています。LLM エージェントはドメインイベントに駆動される前提で動いているため、追跡機能も単なる移動コマンド追加ではなく、追跡状態、失敗理由、停止イベント、再起動入力まで含めたイベント駆動設計として整える必要があります。

現状は大雑把なスポット、ロケーション、オブジェクトへの移動はある一方で、移動する主体を継続的に追う専用機能はありません。視界内での扱いは既にあるため、v1 ではそれを足がかりに「見えている間は追う」「見失ったら最後の既知位置で止まる」「失敗理由を理由付きで通知する」という形を目標にします。

</details>

---
*Last updated: 2026-03-12 after v1.0 milestone archival prep*
