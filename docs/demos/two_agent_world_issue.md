# Issue: 2-Agent LLM 世界デモ — 実 LLM で多人数同時稼働を検証する

## 概要

Phase「自走 tick + heartbeat + intent キュー + ActionFailed 観測」が揃ったので、
**2 体の LLM エージェントが同じスポットグラフ世界で同時に動く**ことを実 LLM
(litellm 経由の OpenAI 等) で検証する。これまで複数 AI エージェントを動かす
土台が無かったため、本デモが成功すれば MMO 的な多人数 LLM 世界の最初の足場
になる。

ベースとなるアーキテクチャ実装は PR `feature/tick-loop-self-driven` (本ブランチ)
の 5 コミット (PR1-5)。

## 前提

- macOS / Linux のターミナル
- Python 3.10 以上 (`uv` 経由)
- OpenAI API キー (または litellm がサポートする他プロバイダ)
- 推奨: 別端末でブラウザを開けると WebSocket 経由でシーンを見られる

## セットアップ

1. ブランチ取得:
   ```bash
   git fetch origin feature/tick-loop-self-driven
   git checkout feature/tick-loop-self-driven
   uv sync
   ```

2. `.env` を準備 (リポジトリには `.env.example` あり、`.env` は git 管理外):
   ```bash
   cp .env.example .env
   # 以下を編集
   echo "OPENAI_API_KEY=sk-..." >> .env
   echo "LLM_CLIENT=litellm" >> .env
   echo "SPOT_GRAPH_TICK_INTERVAL_SEC=2.0" >> .env  # 余裕を持って 2 秒/tick
   echo "SPOT_GRAPH_TICK_LOOP_ENABLED=true" >> .env
   ```

3. キャラクター・シナリオの確認:
   - シナリオ: `data/scenarios/relay_puzzle_demo.json` (2 プレイヤー対応:
     `player_a` オペレーター、`player_b` 侵入者)
   - キャラクター登録: 初回はサーバ経由で 2 体作成する (下記「実行手順」参照)

## 実行手順

### A. サーバ起動

ターミナル 1 で FastAPI サーバを起動 (tick loop が自走で回る):

```bash
uv run python -m ai_rpg_world.presentation.spot_graph_game.server
```

起動ログに以下が出れば成功:
```
Spot graph tick loop enabled (interval=2.000s)
Spot graph tick loop started: interval=2.000s
```

### B. キャラクターを 2 体作成

ターミナル 2 で:

```bash
curl -X POST http://127.0.0.1:8080/api/characters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "アリス",
    "personality_tags": ["好奇心旺盛", "慎重"],
    "first_person": "私",
    "appearance": "焦茶のおさげ、白衣",
    "speech_samples": ["……これは何かしら？"],
    "fragmented_memory": "断片的に医療現場の記憶",
    "values": "真実を知りたい",
    "strengths": "観察眼",
    "weaknesses": "暗所恐怖",
    "interpersonal_tendency": "やや人見知り",
    "behavioral_rules": ["むやみに大声を出さない"]
  }'
```

返ってきた `id` (例: `"a1b2c3d4"`) をメモする。同じ要領で 2 人目「ボブ」も作る。

### C. セッション開始 (世界 ON)

```bash
curl -X POST http://127.0.0.1:8080/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "world_id": "relay_puzzle_demo",
    "character_ids": ["<アリスのid>", "<ボブのid>"]
  }'
```

返ってきた `session_id` をメモ。

この時点で:
- tick loop が自走で `runtime.advance_tick()` を 2 秒おきに呼ぶ
- 5 tick おきに heartbeat 観測が両者に届き LLM ターンが投入される
- LLM (gpt-5-mini など) が tool を呼び世界に介入する

### D. 観測

(D-1) サーバログを監視:
```bash
# ターミナル 1 の出力に
#   session=<id> tick advanced to N
#   <LLM のツール呼び出しログ>
# が継続的に流れる
```

(D-2) スポット情報を確認:
```bash
# セッション状態 (tick 数 / status / end_result)
curl http://127.0.0.1:8080/api/sessions/<session_id>

# 指定キャラクター視点のスポット表示
curl "http://127.0.0.1:8080/api/sessions/<session_id>/view?character_id=<アリスのid>"
```

(D-3) WebSocket (ブラウザ):
```
ws://127.0.0.1:8080/api/sessions/<session_id>/events
```
リアルタイムのシーン更新が見られる。

### E. 終了

ターミナル 1 で `Ctrl-C`。tick loop は lifespan の `finally` で `await
tick_loop.stop()` され graceful に落ちる。

## 確認事項 (Definition of Done)

以下を **全て満たせば成功**:

| # | 観点 | 確認方法 |
|---|------|----------|
| 1 | tick が自走で進む | ターミナル 1 のログに `tick advanced to N` が 2 秒間隔で増える |
| 2 | 両エージェントが少なくとも 1 回ずつ tool を呼ぶ | LLM 呼び出しログに 2 つの異なる `player_id` が現れる |
| 3 | heartbeat が idle 時に発火 | 観測ログに `{"type": "heartbeat"}` が両プレイヤー分現れる |
| 4 | 片方の行動が他方の観測に伝播する | 例: アリスが移動 → ボブの状態取得 API に「アリスが居なくなった」が反映される |
| 5 | 失敗が観測化される | 不正なラベルを LLM が指定したとき `{"type": "action_failed"}` が当該プレイヤーに届く (ログ確認)。**注意**: 本ブランチでは `failure_observer` を `spot_graph_wiring` から auto-wire していないため、サーバ経路では DoD #5 は常に Fail になる。アーキ自体は PR5 の単体テスト + smoke テストで検証済み。失敗観測の本デモ確認は次 PR で wiring を入れてから再走する想定。 |
| 6 | 60 tick (約 2 分) 走り切る | プロセスがクラッシュせず最後まで動く |

**観測の構造化ペイロード例** (確認事項 3, 5 用):

```json
{
  "type": "heartbeat",
  "tick": 13,
  "interval_ticks": 5
}
```

```json
{
  "type": "action_failed",
  "intent_id": 42,
  "tool_name": "spot_graph_travel_to",
  "error_code": "INVALID_DESTINATION_LABEL",
  "message": "移動先ラベルが見つかりません: 北の扉",
  "remediation": "現在の状況に表示された接続先ラベルを指定してください。"
}
```

## 欲しい結果

以下を Issue にコメントで貼り付け:

1. **ターミナル 1 のログ抜粋** (最初の 30 行 + 興味深い箇所): tick 進行 + LLM
   tool 呼び出しの跡が分かるもの
2. **LLM コール回数 と トータル所要時間**: `60 tick × 2 体` 想定で何回呼ばれた
   か、何分かかったか
3. **API キー消費量** (OpenAI ダッシュボードからのスクリーンショット可)
4. **DoD チェックリスト** (上表) の Pass/Fail
5. **驚いた挙動 / 期待外れ**: 「アリスとボブが互いを認識した瞬間」「予想外の
   ループに陥った」など定性的な観察
6. **追加で見たいシナリオの提案** (例: 「2 体が同じアイテムを取ろうとして衝突
   する」「協力プレイの兆候を見たい」)

## トラブルシュート

| 症状 | 推定原因 | 対処 |
|------|----------|------|
| `LLM_API_KEY_MISSING` | `.env` の `OPENAI_API_KEY` が空 | export または `.env` を再読み込み |
| tick が進まない | `SPOT_GRAPH_TICK_LOOP_ENABLED=false` | env を `true` に |
| LLM が tool を返さない | プロンプトのモード不一致 | `LLM_VIEW_DISTANCE=5` を設定、`relay_puzzle_demo` 以外のシナリオを試す |
| 同じ tool を繰り返す | LLM が文脈を読み切れていない | gpt-4o などに切り替え、`SPOT_GRAPH_TICK_INTERVAL_SEC=3.0` に伸ばす |
| `INTENT_RESOLVE_INTERNAL` が頻発 | 内部矛盾 (バグ) | ログを Issue に貼り付けて報告 |

## アーキテクチャ的な背景 (読み物)

このデモは PR1-5 (本ブランチの 5 コミット) で構築した以下の連携を実走させる:

- **PR1**: `SimulationTickLoop` が FastAPI の lifespan で背景 asyncio タスクと
  して走り、`SPOT_GRAPH_TICK_INTERVAL_SEC` ごとに各 session の
  `runtime.advance_tick()` を呼ぶ。
- **PR2**: `HeartbeatObservationEmitter` が post-tick hook で各 LLM プレイヤー
  に `interval_ticks` おきに `{type: heartbeat}` 観測を投入し、
  `ObservationTurnScheduler.maybe_schedule()` で LLM ターンを enqueue。
- **PR3**: `domain/intent/` BC が `Intent` VO + `IntentQueue` 集約を提供。同
  tick 内の解決順は `(phase, -priority, submitted_tick, intent_id)` の決定論的
  ソートで決まる。
- **PR4**: `IntentResolutionService` が既存ツールハンドラを intent VO 経由で
  実行する。`ToolCommandMapper` は opt-in で経路を切り替え可能 (本デモでは
  default 経路。intent 経路への切替は手動で `intent_resolution_service` を
  渡す)。
- **PR5**: 解決失敗時に `ActionFailedObservationEmitter.on_resolution_failure`
  が呼ばれ、`{type: action_failed, error_code, intent_id, ...}` の構造化観測を
  当該プレイヤーへ append。`dto.should_reschedule` に従って turn を投入。

これらの組み合わせを実走させ「2 体の LLM が同じ世界に共存しつつ独立に動く」
姿が確認できれば、本ブランチは目的を達成したと判断できる。

## 次のステップ (デモ結果に応じて)

- **DoD 全 pass**: PR をマージし、次の Phase に進む。候補:
  - PR6 (アクション持続時間): instant action ではなく N tick 跨ぐ予約解決
  - 同 tick batching: `IntentResolutionService._resolve_drained` を post-tick
    hook から呼び、複数 LLM ターンを batching する経路を本配線
  - late-binding intent: `target_descriptor` を活用した自然言語ターゲット指定
- **# 2 (両者が tool 呼ぶ) が満たせない**: プロンプト/ツール一覧の見直し
- **# 4 (相互観測) が満たせない**: ObservationPipeline の recipient 解決を
  確認、scenario 設計を見直し
- **# 5 (失敗観測) が出ない**: `IntentResolutionService` への
  `failure_observer` 注入を main wiring に追加 (本 PR は opt-in なので
  spot_graph_wiring からは未配線)
