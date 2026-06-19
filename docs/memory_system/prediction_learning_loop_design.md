# 予測 → 学習ループ 設計メモ (Issue #526 不在 #3)

> Issue #526「構造的不在 #3: 予測 / 期待値の不在」への設計。
> claude (Claude Code) と codex の独立検討をマージした v0 設計。
> **ステータス: v0 設計確定 (claude × codex × ユーザー)。snapshot 互換=不要
> (bump+fixtures)、主観フィールド=5→4 (attention のみ削除、intention は残し PR2 で
> why 配線)。残るは PR0/PR1 実装着手の GO のみ。**

## なぜ書くか

Issue #526 は「人間は脳内の世界モデルで次に起きることを無意識に予測しており、
外れたら驚く。agent にはこの予測がないから期待値もない」と指摘した。

調査の結果分かったのは、**予測の「器」は既にあるのに、ループのどの継ぎ目も
繋がっていない** ということ。エージェントは行動のたびに必ず予測を出している
のに、本番経路がそれを捨てている。

このメモは「予測 → 観測 → 乖離 → 学習 → 次の予測」のループを、**新しい
モジュールを足さず、既存基盤の配線を繋ぎ直して閉じる** ための設計を残す。

## 検証した現状 (コード事実)

| 事実 | 場所 | 含意 |
|---|---|---|
| world-action tool は `expected_result` を **required 強制**。description は「願望や目的ではなく、行動前の予測を書く」 | `application/llm/services/tool_catalog/subjective_action.py:48-56, 93-99` | エージェントは**毎行動で予測を必ず出している** |
| 5 つの主観フィールド (`inner_thought` / `intention` / `expected_result` / `attention` / `emotion_hint`) が強制される。`inner_thought` だけが観測者表示 (`【心の声】`) / trace viewer の thought bubble になる | `subjective_action.py:17-68, 36-37`; `tool_executor_helpers.py:100-108`; `tests/scripts/test_build_trace_viewer.py:639-657` | `expected_result` は**構造化された予測として保存・照合・表示されない** |
| `_format_action_summary` が raw `arguments` を `json.dumps` して `action_summary` に入れ、`【直近の出来事】` に出す | `agent_orchestrator.py:82-89`; `chunk_encoding.py:32-49`; `recent_events_formatter.py:58-62` | `expected_result` は **raw JSON として紛れうるだけ**で、予測として名指され実際と並べられてはいない |
| 本番主経路 `ChunkEpisodeDraftBuilder` は `expected=None, prediction_error=None` を **ハードコード** | `application/llm/services/chunk_episode_draft_builder.py:259-261` | episode に予測が一切残らない |
| `ActionEpisodeDraftBuilder` (`expected` を埋める唯一の builder) はテスト以外で呼ばれていない | `application/llm/services/action_episode_draft_builder.py` (参照は自身とテストのみ) | `_prediction_error_template()` の文字列一致判定は死んでいる |
| `SemanticGistService` は `ep.interpreted or ep.recall_text or ep.what` だけ読む | `application/llm/services/semantic_gist_service.py:115` | **学びは予測誤差を一切見れない** |
| 再解釈 coordinator は `expected` と `prediction_error` を既に LLM へ渡す | `application/llm/services/episodic_reinterpretation_coordinator.py` | 受け皿は既にある |
| `L5LongSummary.world_view` は narrative voice。具体 baseline の置き場ではない | `domain/memory/short_term/value_object/l5_long_summary.py` | 「世界はこうあるはず」の構造化 store は無い (作らない) |

## 設計の背骨: 同じ情報が形を変えるだけ

予測・驚き・学習を**別々の機能として足さない** (設計原則 #3)。一つの情報が
ループを巡りながら形を変える、として設計する。

```
行動の予測 (expected_result, 既に必須)
  → 直近フィードバック (【前回の予測と実際】を次プロンプトに並べる)
  → episodic evidence (expected / prediction_error を episode に保存)
  → semantic belief (予測誤差を根拠に「学び」へ昇格)
  → 次の行動の予測 (【関連する学び】で戻り、次の expected_result を変える)
```

- **驚きは計算しない。エージェントが文脈内で経験する。** プロンプトに「自分の
  直前の予測」と「実際の結果」が並ぶことで、gap は agent 自身の次ターン推論で
  surface する。乖離判定モジュールを作らない。
- **PR1 が実装するのは「表示されること」ではなく「予測として名指され、実際と
  並べられること」。** `expected_result` は現行でも raw JSON として `action_summary`
  に紛れうるが、それは予測ループではない。この区別を明示することで、将来レビューで
  「でも prompt に入っているのでは?」に答えられる。
- **予測誤差 = salience 信号。** 既存の記憶統合階層 (episodic → semantic → L5)
  が、これまで原理的な供給源を欠いていた「顕著さ」の信号を予測誤差から得る。
  期待を裏切った出来事ほど強く残る、という人間記憶の原理をそのまま使う。

## v0 の決定: 行動条件付き予測から始める

予測には 2 系統ある:

- **行動条件付き (action-conditioned)**: 「Xをすれば Yになるはず」。`expected_result`
  が既に必須で捨てられているだけ。シナリオ K / F 向け。**← v0 はこちら**
- **知覚的 (perceptual)**: 「この部屋は明るいはず」「ノアは陽気なはず」。Issue が
  #3 の動機に挙げた B / C。観測への予測で、新しい入口が要る。**← 非スコープ (後続)**

両者は下流 (episodic の `expected` / `prediction_error` → semantic) で合流する。
v0 を action-conditioned にする理由:

1. `expected_result` は既に必須＝入口が完成済み。PR1 はほぼ「None 削除 + 配線」
2. ループを端から端まで最安・確実に証明できる
3. 知覚的驚きは同じ episodic → semantic 機構に後から source を足して載せられる

## 乖離判定は誰がいつやるか

| 段階 | 担当 | 内容 |
|---|---|---|
| 構造化差分 | orchestrator / prompt builder (機械的) | success 予測なのに failure、error_code、duration 等。「驚きの候補」であって意味判断ではない |
| 質的乖離 | 既存 `EpisodicChunkSubjectiveFieldsService` の LLM 補完 | chunk 生成時に observed / outcome / expected / persona を同時に読める。**新規 LLM 呼び出しを増やさない** |
| 再解釈時 | 既存 reinterpretation LLM | source field は改変せず、`current_interpretation` / `current_recall_text` に学び直しを滲ませる |
| semantic 昇格時 | `SemanticGistService` | 複数 episode の反復誤差を一般化＝ここで初めて「予測の更新」が命題になる |

文字列一致 (`_prediction_error_template`) は廃止。単発誤差は episode subjective、
反復からの学習は semantic gist。

## 学習の宿る場所

- **episodic**: 一次資料。`expected` / `outcome` / `prediction_error` を「当時の
  予測と外れ方」として保存。**更新しない**。
- **reinterpretation**: その一次資料を今どう思い出すか。学習の手前の「意味の再配置」。
- **semantic memory**: 本命の予測更新先。短い命題 + `evidence_episode_ids` +
  `confidence` / `importance` / `tags`。次 prompt の【関連する学び】に戻る。
- **L5 world_view**: 具体法則の置き場ではない。反復誤差が主体の世界観を変える
  ほど大きいときだけ、抽象的に滲む程度。

## 3-PR ロードマップ

各 PR で「何ができるようになるか」:

### PR1 — 突き合わせる (捨てていた予測を短期フィードバックに戻す)

`ActionResultStore` を短期 prediction ledger として流用。新 store 不要。

- `ActionResultEntry` に `expected_result: Optional[str] = None` を追加
  (`SubjectiveEpisode.expected` へ流すのは PR2)
- orchestrator が `_validate_subjective_action_arguments()` 後の **raw**
  `arguments["expected_result"]` から抽出して append (canonical 化で落ちるのを回避)
- 新 prompt section **【前回の予測と実際】** を `【直近の出来事】` の直前に挿入
  (`IContextFormatStrategy.format()` に `prediction_feedback_text` を一級引数で追加)
- v0 は最新の `expected_result` 付き action 1 件のみ。actual は `result_summary` +
  `success` / `error_code` / `tool_name` + 後続 observation prose 最大 2 件
- **並べて見せるだけ。判定はしない** (agent の次ターン推論に amortize)
- snapshot codec (`short_term_memory_codec.py`) の capture/restore に `expected_result`
  追加、`_AR_SCHEMA_VERSION` bump

**できるようになること**: 自分の直近の予測と実際を並べて見て、次の一手で反応
できる。Before: 毎回予測を出すのに当たったか確認せず捨てている。After:「思って
たのと違う」を文脈内で経験。**ただし sliding window を過ぎると忘れる (まだ永続しない)。**

**触るファイル**: `contracts/dtos.py`, `contracts/interfaces.py`,
`services/action_result_store.py`, `services/agent_orchestrator.py`,
`services/context_format_strategy.py`, `application/being/world_subsystems/short_term_memory_codec.py`, tests

### PR2 — 覚える (予測を episode に永続化)

- `ChunkEpisodeDraftBuilder` / `EpisodicChunkSubjectiveFieldsService` が
  `expected` / `prediction_error` を episode に充填
- 兄弟フィールド `intention` → `episode.why`、`emotion_hint` → `episode.felt` /
  emotion cue も同時に配線 (現状いずれも本番未配線)
- 質的乖離判定は既存 LLM 補完に相乗り (新規呼び出し無し)
- LLM 補完が無い fallback は conservative に (構造化可能な差だけ)

**できるようになること**: 「予測を外した出来事」が長期 episode に残り、後日
思い出せる。Before: 何が起きたかは残るが何を期待してたかは残らない＝「驚いた
自分」を覚えていない。After: 自分の見込み違いも自伝に入る (設計原則 #4 継続性)。

### PR3 — 学ぶ (予測誤差を salience として学びに昇格)

- `SemanticGistService` の prompt を拡張し、`expected` / `outcome` /
  `prediction_error` を evidence として読む
- 予測誤差のある episode の `importance_score` を上げ、semantic 昇格を優先
  (salience: 既存の `importance_score` / `recall_count` ツマミに予測誤差を流す)
- 学びは既存の【関連する学び】で次ターンに戻り、次の `expected_result` を変える

**できるようになること**: 繰り返す/大きいミスが durable な「学び」に抽象化され、
次の予測を変える＝ループが閉じる。Before: 学び抽出は予測誤差を一切見ない。
After:「ノアは機嫌が悪いと無視する」型の学びがミスから生まれ、次の予測を変える。

> salience は PR3 の中核 (or PR3.5 に小さく切る余地あり)。今は存在しない。

## 設計原則との対応 (docs/agent_design_principles.md)

- **#3 質感は機能の総和ではない**: 予測/驚き/学習を別モジュールにせず、一つの
  情報がループで形を変える設計。各 PR で質感シナリオ (LLM を呼ばず prompt 構造を
  見る pytest) を 1 つ + 質感ドキュメント 1 段落を DoD に入れる
- **#4 自己の継続性・脆弱性**: 自分の予測ミスを覚えていることが「過去の自分が
  何を考えていたか」の継続性。PR2 が直接効く
- **#2 観測駆動**: 新規 LLM 呼び出しを増やさない (1 起動 1 ツールを守る)
- **#1 疎結合**: semantic/gist 出力は固有名詞、internal cue は index のまま。LLM
  露出経路に integer ID を出さない
- **#5 失敗の質感**: 予測が外れる経験そのものが failure mode の再現

## 質感シナリオ (各 PR の DoD)

- PR1: `expected_result` 付き action → 後続観測で外れたとき、次ターン prompt に
  【前回の予測と実際】が出ているか。エージェントの次の行動が gap を反映するか
- PR2: 外した予測が episode に残り、後日 recall で surface するか
- PR3: 反復した予測ミスが【関連する学び】に出て、次の `expected_result` を変えるか

## 周辺 cleanup: 主観フィールドの棚卸し (別 PR — PR0)

全 world-action tool に required 強制される 5 主観フィールドのうち、本番経路で
消費されないものがある。Issue #264 で loop_guard の fingerprint から narrative を
除外した名残で、当初 `ActionEpisodeDraftBuilder` 経由で episode の `why` / `expected`
/ `felt` を埋める供給源だったが、本番が `ChunkEpisodeDraftBuilder` に移って宙に浮いた。

| フィールド | 消費状況 | 決定 |
|---|---|---|
| `inner_thought` | LIVE + 可視 (`【心の声】` / trace viewer thought bubble) | **残す** |
| `emotion_hint` | enum 検証のみ live (`agent_orchestrator.py:148-158`)。recall cue / felt は**本番 chunk 経路では未配線** (`chunk_episode_draft_builder.py:173-180` が `canonical_arguments=None` で cue 生成を呼ぶ。`episodic_cue_rules.py:476` の入口は test 専用経路でしか通らない) | **残す** (保存先は設計済み・未配線。PR2 で felt/cue へ配線候補) |
| `expected_result` | dead (test 専用 builder のみ) + raw JSON 漏れ | **PR1-3 で復活** |
| `intention` | dead (test 専用 builder のみ → `episode.why`) + raw JSON 漏れ | **残す** (inner_thought と別 facet。PR2 で `episode.why` に配線) |
| `attention` | field として一切消費されない (`change_attention` tool / `attention_service` とは命名衝突の別物。`SubjectiveEpisode` に該当フィールド無し) | **削除** |

→ 主観フィールドは 5 → 4 (`inner_thought` / `intention` / `expected_result` / `emotion_hint`)。
`attention` のみ削除。

**フィールドの facet 整理** (schema description が元々 4 分割で設計していた):

| フィールド | facet | 問い |
|---|---|---|
| `inner_thought` | 声・表現 (観測者向け) | 今どうつぶやく / 感じるか |
| `intention` | 目的・道具的 | この行動は何のためか (予測でも感情でもない) |
| `expected_result` | 予測 | 何が起きると思うか (願望でも目的でもない) |
| `emotion_hint` | 感情 (enum) | どんな感情か |

`intention` と `inner_thought` は実用上重なりがちだが捉える facet が違う。
例: intention「毒沼を避け東回りで灯台へ」/ inner_thought「西の沼は嫌な予感がする」。
「その場の意図」を chunk 生成時に後から推論で復元するのは難しいため、行動時に
declared された `intention` を `episode.why` の供給源として残す。

**PR0 (cleanup, prediction loop とは別 PR / 1 PR=1目的)**:
- `subjective_action.py` の `SUBJECTIVE_ACTION_FIELDS` / `SUBJECTIVE_ACTION_TEXT_FIELDS`
  / `SUBJECTIVE_ACTION_FIELD_PROPERTIES` から `attention` を除去
- `llm_argument_fingerprint.py` の `NARRATIVE_ARG_FIELDS` から `attention` を除去
- `agent_orchestrator.py:142-143` の validation メッセージ修正 (`attention` を外す)
- 関連テスト更新
- codex 確認: 削除は store / snapshot codec / chunk episode 本体に触れない。影響は
  tool schema required 変更 (→ prefix cache は一度崩れる前提) と stub args テストの調整
- PR0 → PR1 → PR2 → PR3 の順を推奨 (cleanup を先に置いて土台を整える)

## 非スコープ

- 知覚的驚き (B / C): 観測への予測の入口を後で足す。同じ episodic → semantic 機構に載せる
- 観測頻度 count baseline: 不要 (フレーム問題)。baseline は episode cluster +
  semantic gist による言語的な世界モデルとして持つ
- surprise の別機能化: しない。`prediction_error` の有無/強さが importance と
  昇格優先度を上げる、で十分

## 詰めた論点 (claude × codex 合意)

### 1. feedback 文言: 願望と予測の混同を防ぐ

「外れたら見立てを更新せよ」だけだと LLM が「願いが叶わなかった」方向に寄る。
予測を “目的” ではなく “世界についての仮説” として扱う文言にする。「反省せよ」
ではなく「読み直し」で、失敗の質感は出しつつ説教臭さを避ける。

```text
【前回の予測と実際】
- 行動前の予測: 「...」
- 実際: ...
- 読み直し: 予測は願望や目的ではなく、世界がどう応答するかについての仮説です。
  実際と違う場合は、何を見落としていたか、次に同じ状況でどう予測し直すかを
  短く考え、次の行動に反映してください。
```

### 2. section 挿入位置: 確定

`【前回の予測と実際】` は `【直近の出来事】` の直前。order policy
(stable_to_volatile / legacy) に関係なく、recent events を出す直前で統一する
(`_emit_recent_events()` の直前)。recent events より抽象度が高い「読み方」で、
current_state よりは過去側、volatile なので stable prefix を壊しにくい。

### 3. snapshot schema version: bump (`_AR_SCHEMA_VERSION = 2`)

`expected_result` は snapshot restore 後の次 prompt に効く行動履歴なので保存対象。
schema に意味変更があるので bump が筋。
**ユーザー判断が要る点**: 古い snapshot 互換が必要か。
- 必要 → restore を v1/v2 両対応 (既存 `_check_version` は単一 version 前提なので改修要)
- 不要 → bump + fixtures 更新で済む (実装コスト小)

### 4. salience は PR3 内: 別名機能にしない

「salience evaluator」のような別モジュールにしない。PR3 内で:
- `prediction_error` ありの episode を semantic promotion の候補スコアで少し優先
- gist prompt に `prediction_error` を evidence として見せる
- `importance_score` の基準に「予測が大きく外れた / 反復した」を追加

これで「予測誤差 = salience」が同じループ内に残る。PR3.5 に切るのは PR3 が
大きくなった時だけ。

### 5. 複数 action chunk の expected: 箇条書き圧縮

最新だけだと chunk 前半 action の予測誤差が消える。代表選択は heuristics が増える。
箇条書き圧縮が最も安全。
- `SubjectiveEpisode.expected` (str) に chunk 内の expected を時系列順、最大 3 件
  まで箇条書き。超えたら「ほか N 件」
- `prediction_error` も LLM 補完で同じ単位を見て、目立つ乖離だけ 1-3 文に
- `EpisodeAction.tool_name` が既に複数 tool を comma join しているので、expected も
  複数対応の自然文にするのが整合する (構造化リストにはしない。LLM 露出 / 再解釈に
  向く自然文フィールドとして扱う)

```text
expected:
- speech_say: ノアが返事をして状況を教えてくれる
- spot_graph_travel_to: 灯台へ移動できる
```

## 出典

- Issue #526 — 構造的不在 #3
- PR #533 — `docs/agent_design_principles.md` (原則 #3 / #4)
- PR #521 — `docs/memory_system/perception_memory_join_design.md`
- `docs/memory_module_implementation_plan.md` — 予測誤差最小化 / 予測志向検索
