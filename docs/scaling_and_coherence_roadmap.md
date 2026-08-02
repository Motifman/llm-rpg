# スケーリングと整合性のロードマップ

エージェント数や世界の規模を増やしていく前提で「いま壁になっていること」「どの順で解いていくか」をまとめた作業ノート。会話内で議論した内容を散逸させないために永続化する。実装はまだ着手していない (このドキュメントは設計段階)。

> **上位アーキテクチャ（MMO サーバ・外部エージェント・マルチワールド）**: [agent_continuity_roadmap/mmo_world_server_architecture.md](./agent_continuity_roadmap/mmo_world_server_architecture.md)

## 文脈

- 4 人のエージェントが survival_island_v2 を最大 14 日 (140-336 tick) 走る前提のシナリオを評価中
- 第24回実験 (`#343`) OFF run の wall time: **349 tick で 4614s (約 77 分)**
- ボトルネックの本命は **LLM 呼び出しがエージェント単位で完全シリアル** な点
- N が増えるほど O(N) で線形に遅くなる → 10 人にすると 2 時間級、20 人で 4 時間級
- 会話・整合性については「現実世界の会話に存在しない要素 (reply\_to / topic スレッド分岐) は入れたくない」という制約あり

## 現状の整理

### 同時実行性

`DefaultLlmTurnTrigger.run_scheduled_turns()` (`application/llm/llm_turn_trigger.py:40-71`) が `for pid in pending: self._turn_runner.run_turn(pid)` の単純ループで完全シリアル。

各 turn 内では:
- `litellm.completion()` (`infrastructure/llm/litellm_client.py:174`) が同期 HTTP コール
- tool 実行 (`agent_orchestrator.py:454`) も同期呼び出し

例外は `InMemorySubjectiveEpisodeStore` (`threading.RLock` 保持) で、`ThreadPoolEpisodicSubjectiveScheduler` (#309) が裏で走るが、これは記憶エンコーディングだけで turn 実行は serialize されたまま。

### トリガ方式

- ハートビート: `heartbeat_observation_emitter.py:81-147` が `interval_ticks` (default 5) ごとに**全員一斉**起床
- イベント駆動: `ObservationTurnScheduler.maybe_schedule()` が「動きがあった」エージェントを `_pending` に追加
- どちらも同じ `_pending` セットに合流して serialize 実行

idle なエージェントもハートビートで毎回 LLM を叩く → 「世界が静かなとき」のコストが落とせていない。

### 状態同期

- 1 tick 内の世界更新は `UnitOfWork` (`spot_graph_simulation_application_service.py:86`) で囲って commit
- post-tick hook の中で LLM turn を回す (commit 後の状態を読む)
- ロックなし。完全シリアル前提で衝突を回避している

## ロードマップ (4 段階)

### Step 1. LLM 呼び出しフェーズだけ並列化 (最優先・推奨)

各 turn を概念的に 2 段階に分ける:

| Phase | 内容 | 並列化可能か |
|---|---|---|
| **A** | snapshot 構築 → LLM 呼び出し → tool\_call 列を得る | **YES** (read-only) |
| **B** | tool\_call を世界へ適用 (repository.save) | **NO** (mutate、衝突可能性) |

Phase A は全エージェントが tick T の commit 済み状態を読むだけなので相互干渉なし。`litellm.acompletion` + `asyncio.gather(*[run_phase_a(pid) for pid in pending])` で並列化できる。Phase B は今のまま pid 順に serial 適用する。

**期待効果**: 4 人 × 2s → max(2s) ≈ 2s/tick。**~4 倍速**。N が増えるほど効く。
**整合性**: 全員同じ tick T を読むので「思考の同時刻性」が自然に保たれる (人間の同時思考と同等)。
**実装規模**: ~300 行。

### Step 2. tool 適用の衝突を「意図失敗 → 次 tick」で吸収

Phase A で A が「B にアイテムを渡す」、B が「A から離れる」を同 tick で決めた場合、Phase B 適用順によって片方が失敗する。

現状は失敗 = 例外で死ぬので、これを **「intent failed because state changed」を観測として返して次 tick で再考させる** 形にする。

- MMO の lockstep simulation で使われる古典パターン
- 失敗観測自体が物語の素材になる (「渡そうとしたら相手がもう居なかった」)

**期待効果**: Step 1 を有効化したときの衝突をクラッシュなしで吸収。
**実装規模**: ~200 行。

### Step 3. heartbeat を撤廃、エージェントごとの idle timer に置き換え

今: 5 tick ごとに全員起床 → idle でも LLM 4 呼び出し。

案:

- 通常起床トリガ
  - 観測 (`schedules_turn=True`) が届いたとき
  - 自分の予約行動が完了したとき (移動到着 / cooking finish)
- **個別の最長無起床時間を超えたとき** (例: 1 日 = 24 tick 何も起きなければ 1 回起きる)

**期待効果**: tick 進行は O(1)、エージェント起床は**アクティビティ量に比例**。世界が静かなら ほぼ無料。
**リスク**: 「LLM が気づくべきだが観測トリガが鳴らなかった」変化を見落とす。観測ハンドラの網羅性を一度 audit する必要あり。
**実装規模**: ~400 行。

### Step 4. spot-level lock + aggregate shard commit (将来)

N がさらに増えたら:

- Phase B 適用順を「同 spot のエージェントは順序保証、別 spot は並列 commit」にする
- ただし **SQLite が SERIALIZABLE で書き込みを直列化する** ので、現バックエンドではこれは効かない
- Postgres / 別 DB に移すか、aggregate 単位の in-memory lock を引いてからやる話

**今は不要**。10-20 人に増やすときに考える。

### 優先度サマリ

| 段階 | 規模 | 得られるもの | 推奨タイミング |
|---|---|---|---|
| **Step 1** | ~300 行 | ~4 倍速、N に強くなる | **次回の機能 PR 群の前** |
| **Step 2** | ~200 行 | クラッシュなしで並列継続 | Step 1 直後 |
| **Step 3** | ~400 行 | アクティビティ比例コスト | 実験 #24 で wait spam 問題が解消しない場合に着手 |
| **Step 4** | ~600 行 | DB を Postgres にしてから本気で N=20+ 対応 | 当面不要 |

## 会話整合性の議論メモ (実装は先送り)

### 問題

並列化 (Step 1) を入れると顕在化する典型: A と B が同 tick で会話を始める → お互いに相手の応答を待たずに発話 → 二つの独立した内容が並行進行する。

LLM レイテンシ自体が「人間より長い思考時間」を生むので、本物の人間会話より噛み合わなさが目立つ可能性がある。

### 制約

> **現実世界の会話に存在し得ない要素 (reply\_to / topic スレッド分岐タグ) は入れたくない。**

人間の会話は線形で、割り込みや譲り合いはあるが「会話スレッド」が分岐するわけではない。

### 議論候補 (どれもまだ未採用)

**(A) Conversation Floor (発言権) アグリゲート** — 物理寄り

- spot に「発言権 (floor)」を 1 つだけ持たせる
- Phase A でエージェントは「speak intent」を発行 (まだ実発話ではない)
- Phase B 序盤に floor 所有者を決定 (pid 最小 / 優先度 / ランダム)
- floor 取得者だけ実発話、他は「相手が話している、自分は譲った」を観測として受け取る
- 翌 tick で他の人が応答

**メリット**: 強い決定論、人間的な「割り込み・譲り合い」をモデル化
**デメリット**: 重い (500 行+)、シナリオ JSON の発話設計が複雑化

**(B) 並列発話の即時 broadcast** — 現状維持

- 並列発話を許す (現状の `PlayerSpokeEvent` のまま)
- 観測順序は serial Phase B で決定論的に確定
- 噛み合わない会話は「会話の自然な揺らぎ」として受容
- LLM の発話タイミング遅延 + 観測順序による「自然な噛み合わなさ」を物語の一部として扱う

**メリット**: 軽量 (~0 行)、現状の event broadcast を活かせる
**デメリット**: 噛み合わなさが「不自然」と感じる場面があるかも

**(C) topic\_hint だけ追加 (構造化なし)**

- `speech_speak` tool に `topic_hint: str | None` を追加
- 同じ topic\_hint への発話は LLM 側で「同じ話題」と認識する材料になる
- ただしシステムは何も保証しない (LLM が話題継続するかは LLM の判断)
- スレッド構造は作らない (作らないのが重要)

**メリット**: 軽量 (~50 行)、LLM に補助情報を渡す程度
**デメリット**: LLM の判断頼みなので効果は不透明

### 議論で確認したい点

- 並列化を入れた後、本当に「噛み合わない会話」が問題になるか? それとも実は OK か?
- LLM のレイテンシが人間より長いことが問題なのか、それとも同時実行そのものが問題なのか?
- ユーザーが求める「会話の人間らしさ」は具体的にどこまで?

**現状のおすすめ**: Step 1 並列化を入れて実走してから、本当に噛み合わなさが問題になるかを観察して、(B) のまま行くか (C) を足すかを決める。

## 開発の運用フロー

このロードマップを実装するときの推奨手順:

1. **Step 1 を別ブランチで実装** (`feat/llm-phase-a-parallel`)
2. **既存テスト + 専用 async テストで動作確認**
3. **survival\_island\_v2 を OFF run で計測** (wall time が 1/4 になるか)
4. **問題があれば Step 2 を追加**
5. **実走で噛み合わなさを観察してから会話整合性議論に戻る**
6. (必要なら) Step 3 sparse heartbeat に進む

各ステップで実験 issue を立てて trace を比較する。

## 関連

- 第24回実験 OFF run: #343
- 実験 #24 詳細 trace 分析コメント: #343 のコメント
- 実験 runtime の wiring 漏れ: #344
- 長走前提条件 fix: #345
- 隠れた地雷 (event publisher / scene broker メモリリーク等): #345 マージ済み
