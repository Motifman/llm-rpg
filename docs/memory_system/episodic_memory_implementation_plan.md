# Episodic Memory — MVP 再実装計画

この文書は [episodic_memory_system_spec.md](./episodic_memory_system_spec.md) を、削除後の空き地から再実装するための計画である。

旧 `EpisodeMemoryEntry`、旧 `SubjectiveEpisode`、旧 trace / chunker / encoder / recall / SQLite store / reflection 実装は **使わない**。名前・インターフェース・永続化 schema も、必要性を再確認しない限り戻さない。git 履歴には残っているが、本計画の設計入力にはしない。

歴史的なフェーズ表・査読メモの長文は本ファイルには載せない。[episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md) に譲り、ここでは MVP の共有契約と PR 分割だけを単一ソースとする。

作業手続き、PR、サブエージェントレビュー、ブロッキング確認は [memory_feature_workflow.md](./memory_feature_workflow.md) に従う。レビュー用サブエージェントは **必ず Composer 2** で起動する。

## 0. 現在の前提

2026-05-03 時点で、プロンプトに入る過去文脈は `SlidingWindowMemory` の直近観測と `IActionResultStore` の直近行動結果だけである。

削除済みのもの:

- レガシー `EpisodeMemoryEntry` / `PredictiveMemoryRetriever`
- `memory_query` / `memory_recall_subjective` / `subagent` / `working_memory_append`
- 長期 facts / laws / reflection runner
- 旧 v2 `SubjectiveEpisode` store / SQLite schema / passive recall / context pack
- 旧 `ActionExperienceTrace` / `ObservationExperienceTrace` / episode encoding / cue extraction

## 1. MVP の目的

MVP の目的は「過去ログ検索」ではなく、ゲーム内で起きた出来事を **自分視点の体験**として保存し、後で受動的想起に使える最小単位を作ることである。

最初のゴール:

- tool 実行や観測から、5W1H を持つ `SubjectiveEpisode` を作れる。
- 保存される情報が、イベント・tool result・runtime context・観測に実在する情報から来ていることを検証できる。
- LLM 生成は少数の主観フィールドだけに限定し、事実・索引・ID を生成させない。
- vLLM 実験で、LLM 生成部分が過剰生成・ハルシネーション・遅延を起こさないか確認できる。

MVP でまだやらないこと:

- 複雑な chunker。
- reflection / consolidation。
- semantic memory / identity memory / laws / facts。
- embedding 類似検索。
- graph DB。
- 旧 `memory_query` 形式の能動想起。
- LLM による cue key の自由生成。

## 2. 最初の問い

### 2.1 何を保存するか

`SubjectiveEpisode` は、最小でも次を持つ。

| フィールド | 意味 | 主な情報源 | MVP 方針 |
|---|---|---|---|
| `episode_id` | 保存単位の ID | store 採番 or UUID | ルール生成 |
| `player_id` | 体験した agent | `LlmAgentOrchestrator.run_turn(player_id)` / 観測 recipient | ルール生成 |
| `occurred_at` | 実時間 | `ActionResultEntry.occurred_at` / `ObservationEntry.occurred_at` | ルール生成 |
| `game_time_label` | ゲーム内時刻表示 | `ObservationEntry.game_time_label`、将来 runtime provider | 取れなければ `None` |
| `who` | 関係者 | tool args / `ToolRuntimeContextDto.targets` / `ObservationOutput.structured` | stable id 優先、なければ表示名 |
| `where` | 場所 | `ToolRuntimeContextDto.current_spot_id`, `current_area_ids`, `current_sub_location_id`, `current_x/y/z` | ID 優先 |
| `what` | 何が起きたか | tool name + result message / observation prose | 事実ベース |
| `why` | なぜそうしたか | tool args の `intention` | LLM 生成しない |
| `how` | どう行動したか | tool name / canonical args | ルール生成 |
| `observed` | 実際に知覚・確認したこと | result message / observation prose | 不変、LLM で盛らない |
| `expected` | 事前予測 | tool args の `expected_result` | なければ `None` |
| `outcome` | 結果 | `LlmCommandResultDto.success`, `error_code`, result summary | ルール生成 |
| `prediction_error` | 予測との差 | `expected_result` と result の差 | MVP は単純テンプレート |
| `felt` | 感情 | tool args の `emotion_hint` | enum 値のみ |
| `interpreted` | 当時の意味づけ | LLM 生成候補 | 入力事実から 1 文だけ |
| `cues` | 想起 key | runtime / tool / observation structured | ルール生成のみ |
| `recall_text` | prompt に入れる短文 | template or LLM 生成 | MVP は template、LLM 版は実験 |
| `source_event_ids` | 元材料参照 | action event / observation event ID | MVP では内部 ID |

`observed` と `source_event_ids` は不変にする。後で再解釈する場合も、元事実を書き換えない。

### 2.2 LLM に生成させてよいもの

LLM に任せてよいのは、事実ではなく **短い主観化**だけである。

MVP の LLM 生成候補:

- `interpreted`: 「この出来事を当時どう意味づけたか」1 文。
- `recall_text`: 想起時に prompt へ入れる短い文。最大 2 文。

**`intended_next` は MVP の DTO に含めない**（`intention` / `attention` / 受動想起と役割が重なり、並列実装で境界が曖昧になりやすいため）。必要なら想起パイプラインや次ターン入力とあわせて後段で別名・別工程として検討する。

LLM に生成させないもの:

- `who`, `where`, `when`。
- stable id。
- cue。
- success / failure。
- error code。
- tool result の事実。
- 存在しない人物・場所・物体。
- 長い内省文、教訓、世界法則。

LLM 生成は、1 episode あたり最大 **2** フィールド（上記候補のうち埋めるもの）に抑える。10 個以上の自由生成フィールドは作らない。JSON schema を使い、文字数上限と「入力にない事実を足さない」検証を入れる。

### 2.3 どこから情報を取るか

コード上の一次情報源は次に固定する。

| 情報 | 取得元 |
|---|---|
| LLM が選んだ tool 名 | `LlmAgentOrchestrator._run_turn_core` の `name` |
| LLM が出した tool args | 同 `arguments` / `canonical_arguments` |
| 主観入力 | subjective action schema の `inner_thought`, `intention`, `expected_result`, `attention`, `emotion_hint` |
| tool 実行結果 | `LlmCommandResultDto` |
| action summary / result summary | `_format_action_summary` / `build_result_summary` |
| 場所・対象 label 解決 | `ToolRuntimeContextDto` |
| 直近観測 | `ObservationEntry` |
| 観測の構造化情報 | `ObservationOutput.structured` |
| 観測カテゴリ | `ObservationOutput.observation_category` |

prompt 文字列から cue や事実を抽出しない。prompt は表示物であり、索引や episode の source of truth にしない。

### 2.4 どこで区切るか

MVP では `1 LLM turn / 1 tool result = 1 chunk` とする。

理由:

- `LlmAgentOrchestrator` に tool 名、args、runtime context、result が同時に揃う。
- 行動前予測と結果の対応が取りやすい。
- 複数出来事 chunker を先に作ると、保存単位・source trace・LLM 入力が曖昧になる。

観測だけで episode を作る経路は後段に回す。ただし `ObservationEntry` は action episode の周辺文脈として参照できるようにする。

### 2.5 いつ保存するか

MVP では tool 実行結果が確定し、`IActionResultStore.append` へ記録されるのと同じタイミングの直後に episode 材料を作る。

保存順:

1. LLM が tool call を返す。
2. args を解決する。
3. tool を実行する。
4. `LlmCommandResultDto` を得る。
5. `IActionResultStore` に直近行動結果を保存する。
6. 同じ材料から `SubjectiveEpisode` を作る。
7. episode store に保存する。

失敗した tool call も episode にできる。むしろ `expected_result` と失敗結果の差は記憶として重要である。

## 3. MVP のクラス設計

### 3.1 Value Objects / DTO

最初に作る型:

- `SubjectiveEpisode`
- `EpisodeLocation`
- `EpisodeAction`
- `EpisodicCue`
- `EpisodeSource`

配置候補:

- `src/ai_rpg_world/application/llm/contracts/episodic_memory.py`

ドメイン層ではなく application/llm contracts に置く。理由は、現段階では LLM agent の体験記録であり、ゲーム世界そのもののルールではないため。

### 3.2 最小 `SubjectiveEpisode`

```python
@dataclass(frozen=True)
class SubjectiveEpisode:
    episode_id: str
    player_id: int
    occurred_at: datetime
    game_time_label: str | None
    source: EpisodeSource
    location: EpisodeLocation
    action: EpisodeAction | None
    who: tuple[str, ...]
    what: str
    why: str | None
    observed: str
    expected: str | None
    outcome: str
    prediction_error: str | None
    felt: str | None
    interpreted: str | None
    cues: tuple[EpisodicCue, ...]
    recall_text: str
```

削る候補:

- `importance`: MVP では後回し。全部 0.5 などにするくらいなら持たない。
- `salience_reasons`: 後回し。保存理由が必要になったら追加。
- `memory_reflection_journal`: 後回し。
- `cue_keys`: 旧実装の形なので戻さない。

### 3.3 必要十分性の検証

各フィールドについて、次のどちらかを満たさない場合は MVP から外す。

- イベント・tool・runtime・観測から決定的に取れる。
- LLM 生成する価値があり、入力事実だけを使った短文として検証できる。

曖昧なものは削る。特に `importance`, `belief_delta`, `identity_delta`, `lesson`, `semantic_candidate` は MVP には入れない。

## 4. LLM 生成検証

### 4.1 unittest

unit test では、LLM なしの deterministic encoder を先に固定する。

確認すること:

- tool result から `SubjectiveEpisode` が作れる。
- 5W1H のうち、情報源があるものだけが埋まる。
- `observed` に入力外の事実が混ざらない。
- cue は runtime / tool / observation structured からだけ作る。
- LLM 生成フィールドが `None` でも episode として成立する。

### 4.2 vLLM local experiment

`local_experiments/episode_encoding_vllm_gemma_experiment.py` は旧 DTO に依存しているため、そのまま復活させない。新しい MVP に合わせて、別スクリプトを作る。

候補:

- `local_experiments/subjective_episode_mvp_vllm_experiment.py`

実験の目的:

- LLM が `interpreted`, `recall_text` だけを生成できるか。
- 入力にない人物・場所・物体を足さないか。
- JSON schema と低温度で安定するか。
- 1 episode あたりの生成遅延が許容範囲か。
- 少数の自由生成フィールドで足りる設計か。

入力:

- deterministic encoder が作った episode draft。
- source event の facts。
- persona block は短く入れる。ただし persona で事実を上書きしない。

出力 schema:

```json
{
  "interpreted": "string <= 160 chars or null",
  "recall_text": "string <= 240 chars"
}
```

検証:

- JSON parse できる。
- 各フィールドが上限文字数以内。
- `observed`, `who`, `where`, `outcome`, `cues` を変更しない。
- 入力 source facts にない固有名詞を追加していないかを簡易チェックする。
- 代表 5 ケースを保存し、Markdown と JSON に出力する。

vLLM 実行例は既存実験に合わせる。

```bash
source venv/bin/activate
VLLM_BASE_URL=http://127.0.0.1:8001/v1 VLLM_MODEL=gemma-4-31b-it-nvfp4 \
  VLLM_TEMPERATURE=0.2 python local_experiments/subjective_episode_mvp_vllm_experiment.py
```

## 5. 作業分割

小さい PR に分ける。

### PR 1: `docs/episodic-memory-mvp-plan`

目的:

- 旧計画を使わないことを明文化する。
- MVP の保存フィールド、情報源、LLM 生成範囲、検証方針を決める。

成果物:

- この計画ファイル。

### PR 2: `feature/episodic-episode-model`

目的:

- `SubjectiveEpisode` と周辺 value object だけを作る。

成果物:

- dataclass。
- `__post_init__` validation。
- フィールドごとの情報源テスト。

並列性:

- ここは基礎なので単独で先に入れる。

### PR 3: `feature/episodic-action-draft-encoder`

目的:

- 1 tool result から episode draft を作る。
- LLM なしで episode として成立することを保証する。

成果物:

- `ActionEpisodeDraftBuilder` などの deterministic builder。
- `LlmAgentOrchestrator` にはまだ接続しないか、接続は feature flag / 明示注入にする。

並列性:

- PR 2 の型に依存。
- PR 4 の cue ルールと並行しやすい。

### PR 4: `feature/episodic-cue-rules`

目的:

- cue を runtime / tool / observation structured から決定論的に作る。

成果物:

- `EpisodicCue` 生成関数。
- `place`, `action`, `object`, `entity`, `outcome`, `emotion` の最小ルール。

並列性:

- PR 2 後、PR 3 と並行可能。

### PR 5: `feature/episodic-in-memory-store`

目的:

- episode を保存・取得できるようにする。

成果物:

- in-memory store（`IEpisodicEpisodeStore` / `InMemorySubjectiveEpisodeStore`。SQLite・Passive Recall・オーケストレータ配線なし）。
- player ごとの分離。
- recent（`occurred_at` 降順、同一時刻は `episode_id` 降順）/ cue canonical 逆引きの最小取得。同一 `(player_id, episode_id)` の再 `put` は upsert。

並列性:

- PR 2 後に実装可能。
- PR 3 / PR 4 と並行可能だが、統合は後。

### PR 6: `feature/episodic-action-capture`

目的:

- `LlmAgentOrchestrator` の tool result 後に episode を保存する。

成果物:

- action-centered episode capture。
- prompt にはまだ出さない。
- 代表 tool success / failure テスト。

依存:

- PR 2, PR 3, PR 4, PR 5。

### PR 7: `feature/episodic-vllm-generation-experiment`

目的:

- LLM 生成部分の妥当性を vLLM で検証する。

成果物:

- `local_experiments/subjective_episode_mvp_vllm_experiment.py`
- runs 出力のサンプル。
- hallucination / latency / JSON stability の観察メモ。

並列性:

- PR 2 と PR 3 が入れば開始可能。
- 本番配線とは独立。

### PR 8: `feature/episodic-passive-recall-mvp`

目的:

- 現在状況から cue を作り、episode store から候補を取り、`recall_text` を prompt に入れる。

成果物:

- 軸別候補の和集合。
- prompt 入口は 1 箇所。
- 件数・文字数上限。

依存:

- PR 5, PR 6。
- LLM 生成 `recall_text` は PR 7 の結果を見て採否判断。

## 6. MVP 完了条件

MVP 完了は次で判定する。

- 1 回の tool 実行から `SubjectiveEpisode` が保存される。
- 5W1H の情報源がコード上で説明できる。
- LLM なしでも episode が成立する。
- LLM を使う場合も生成対象は `interpreted` / `recall_text` のみ（最大 2 フィールド）。
- cue はゲーム由来構造から作られる。
- 受動的想起で、現在地・対象・行動・結果に関連する過去 episode の `recall_text` が prompt に入る。
- vLLM 実験で、代表ケースの JSON 安定性とハルシネーション傾向を確認済み。

## 7. 放置防止

MVP のまま放置しないため、各 PR の説明に必ず「省いたもの」を書く。

省いたものはこの計画の該当 PR に追記し、次に回すか捨てるかを明示する。

MVP 後に必ず再評価するもの:

- 観測だけの episode。
- 複数 event chunk。
- LLM `recall_text` の本番採用。
- SQLite 永続化。
- reflection / consolidation。
- semantic / identity 候補。

## 8. 参照

- 仕様: [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- 作業手続き: [memory_feature_workflow.md](./memory_feature_workflow.md)
- 詳細議事録・旧ロードマップ長文: [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)
- 旧 vLLM 実験例: `local_experiments/episode_encoding_vllm_gemma_experiment.py`（旧 DTO 依存のため設計は流用しない。vLLM 呼び出し方法のみ参考）
