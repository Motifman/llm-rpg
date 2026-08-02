# frontend 通常削除対象台帳

## 目的

現在の研究・実験の目的から外れたブラウザ向けゲーム表示実装を、通常の削除変更として
現在のツリーから取り除く。Git 履歴は書き換えず、他の作業環境が通常の `git pull` で
変更を取得できる状態を維持する。

調査基準は 2026-08-02 時点の `main`、コミット `a104e26f` とする。

## 削除対象

| パス | ファイル数 | 理由 |
|---|---:|---|
| `frontend/**` | 120 | Vite、React、Phaser、画面、試験、画像、地図を含む実装本体 |
| `src/ai_rpg_world/application/ui/**` | 17 | 旧表示専用のシーン投影・手動操作・表示差分配信 |
| `src/ai_rpg_world/infrastructure/ui/**` | 7 | 上記の SQLite・実行時制御・配信実装 |
| `src/ai_rpg_world/presentation/web/**` | 5 | 旧表示専用の FastAPI 構成、デモ DB、起動入口 |
| `tests/application/ui/**` | 9 | 削除するアプリケーション層の試験 |
| `tests/infrastructure/ui/**` | 1 | 削除する基盤層の試験 |
| `tests/presentation/web/**` | 5 | 削除する Web 表示層の試験 |
| `tools/asset_pipeline/**` | 11 | `frontend/public/assets` 専用の画像加工道具 |
| フロント専用の単独ファイル | 9 | 表示 API、イベント登録、対応試験、実装計画、画面設計 |

フロント専用の単独ファイルは次のとおり。

- `src/ai_rpg_world/presentation/game_scene_api.py`
- `src/ai_rpg_world/presentation/game_control_api.py`
- `src/ai_rpg_world/infrastructure/events/ui_event_handler_registry.py`
- `tests/infrastructure/events/test_ui_event_handler_registry.py`
- `tests/presentation/test_game_scene_api.py`
- `tests/presentation/test_game_control_api.py`
- `docs/frontend_game_visualization_plan.md`
- `docs/game/frontend_game_visualization_plan.md`
- `docs/game/DESIGN.md`

削除対象は合計 184 ファイルである。

## 共有ファイルの整理

- `Makefile` から旧表示、フロント、画像加工用の変数・入口・ヘルプを除去する
- `.gitignore` から `frontend/` 専用の項目を除去する
- ホスト名検査から削除済みディレクトリの除外規則を除去する
- `EventHandlerComposition` から利用者のなくなる `ui_registry` 配線を除去する
- `spot_graph_game` の CORS は既定で許可せず、環境変数による明示指定だけを許可する
- 旧 DB 再生成入口への例外メッセージを一般的な案内へ置換する
- 共有文書から削除済みファイルへのリンクと実装手順を除去する

## 保持対象

- `src/ai_rpg_world/presentation/spot_graph_game/**`
- `tests/presentation/spot_graph_game/**`
- `src/ai_rpg_world/application/llm/services/ui_context_builder.py`
- 実験結果の追跡表示と `docs/trace_viewer_spec.md`
- 端末 UI
- `fastapi`、`httpx`、`uvicorn[standard]`
- 実 LLM 実験用シナリオ、物語、LLM 配線、脱出ゲーム実験

## シナリオ入力の整理

フロント削除後の実験入力を明確にするため、実 LLM 実験で使わない機構実証用の
シナリオ 11 件と `darkened_station.json` を `tests/fixtures/scenarios/` へ移す。
初期版 `survival_island.json` は v2 以降で代替済みのため削除する。

旧人物選択用の `data/characters.json` も削除し、実行時に作成する人物データは
`var/characters.json`、ローカル実験の人物入力は明示指定とする。

## 検証

- 削除したモジュールへの import と削除済みパスへのリンクが現在のツリーにない
- CORS は既定で空、明示設定時だけ指定元を許可する
- `tests/presentation/spot_graph_game` を含む全試験が成功する
- `smoke_stub` の低コスト実験が成功する
- 実験結果の追跡表示を生成できる
