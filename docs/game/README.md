# 脱出ゲーム／仮想世界プレイ体験 — ドキュメント索引

プレイ体験の設計（画面・世界観・ストーリー・キャラクター）と、それに紐づく実装計画の**実体**を本ディレクトリに集約する。DDD やインフラの詳細は従来どおり `docs/` 直下や [system_implementations/](../system_implementations/) を参照。

## デザイン

| 文書 | 内容 |
|------|------|
| [DESIGN.md](./DESIGN.md) | Creative North Star「The Fractured Aristocrat」、色・タイポ・コンポーネント方針（**角丸 6px 等の実装標準を反映**） |
| フロント実装 | `frontend/src/title/TitleScreen.css`（タイトル）、`frontend/src/prologue/PrologueScreen.css`（プロローグ）、`frontend/src/worldSelect/WorldSelectScreen.css`（実験選択） |

## 世界観・画面・ロードマップ

| 文書 | 内容 |
|------|------|
| [virtual_world_game_design_plan.md](./virtual_world_game_design_plan.md) | 仮想世界 AI キャラクターゲームの設計計画（画面一覧、Phase、バックエンド／フロント方針）。**プレイヤー向け画面遷移の正本は §3.2** |
| [spot_graph_world_implementation_plan.md](./spot_graph_world_implementation_plan.md) | スポットグラフ世界の実装計画 |
| [frontend_game_visualization_plan.md](./frontend_game_visualization_plan.md) | ゲーム可視化フロントの計画 |
| [worlds.md](./worlds.md) | **脱出ワールド（実験）草案集** — 5ワールドの舞台・テーマ・エピローグ変化、メタテーマ「プレイヤー＝器」 |

## ストーリー

| 文書 | 内容 |
|------|------|
| [story_concept.md](./story_concept.md) | ストーリー概念（脱出ワールド総論は §2、個別ワールドは [worlds.md](./worlds.md)） |
| [story_concept_consultation_brief.md](./story_concept_consultation_brief.md) | 外部相談用ブリーフ |

## キャラクター（物語用シート）

| 文書 | 内容 |
|------|------|
| [characters/CHARACTER_SHEET_TEMPLATE.md](./characters/CHARACTER_SHEET_TEMPLATE.md) | キャラクター設定のテンプレート |
| [characters/gate_girl.md](./characters/gate_girl.md) | 門前の少女（仮）— 儀式・視点・天の声・外見指針 |

## キャラクター・設定の参照先

キャラクター設計や荘園・脱出ワールドの設定は、主に [virtual_world_game_design_plan.md](./virtual_world_game_design_plan.md) の「世界観とストーリー」「キャラクター設計」にまとまっている。物語上の個別人物は [characters/](./characters/) のシートで追補する。脱出ワールド単位の草案は [worlds.md](./worlds.md)。

## プロローグ（実装）

シナリオデータ: `frontend/src/prologue/prologueData.ts`  
画面: `frontend/src/prologue/PrologueScreen.tsx`

## 実験選択（実装）

データ: `frontend/src/worldSelect/worldSelectData.ts`  
画面: `frontend/src/worldSelect/WorldSelectScreen.tsx`  
草案: [worlds.md](./worlds.md)
