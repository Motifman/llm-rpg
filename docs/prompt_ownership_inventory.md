# プロンプトの棚卸し: 環境の材料と Being の持ち物

#1520 (プロンプトを Being が組み立て、環境は材料を渡す形にする) の材料。いまのプロンプトを部分ごとに、環境の材料か、Being の持ち物か、混ざっているか、組み立ての決まりか、に分けた。

確かめたもの: 保存済みの run `var/runs/memory_jev_e2e_v4_002` の `prompt_dataset` (206 呼び出し、system prompt 4 種) と、HEAD 23c6daa2 のコード。推測で書いた箇所は「推測」と付けた。この一覧はその時点の記録で、移した部分は書き換えていない。S7【同じ局面にいる者】は #1520 段 1 で毎ターンのメッセージの【知っている人】に移った (design_decisions D1520)。

決まったこと (#1520 のコメント):
- 環境は、世界がどう見えるかを部品として描いて渡す。Being の知識で描き方が変わるところだけ構造で渡す。Being が並べて組み立てる
- 知っている人の一覧は system prompt に置かず、毎ターンのメッセージの変わりにくい側に【知っている人】として出す

## 0. 組み立ての流れ

パスは `src/ai_rpg_world/application/` からの相対。行番号は HEAD 23c6daa2 のもの (プロンプトに関わるファイルは b97ebc0f でも同じ)。

1 回の LLM 呼び出しは、system prompt 1 通、user メッセージ 1 通、tool の定義の一覧でできている。この 3 つは別々の場所で組まれ、`run_phase_a` (`llm/services/world_llm_turn/phase_a.py:194`) で 1 つの呼び出しにまとまる。

### system prompt (run の開始時に 1 回)

1. `create_world_runtime` (`world_runtime/world_runtime.py`) が、シナリオを読んだ直後に player ごとの system prompt を組む
   - `safe_world_intro_text` (`llm/services/world_llm_prompt.py:50`) が `metadata.llm_public_intro` を返す (4877 行)
   - `build_world_briefing` (`llm/services/world_briefing.py:438`) が見取り図・陣営の内訳・点検の割り当て・会議の決まりを組み、概要の後ろにつなぐ (4888 行)
   - player ごとのループ (4948〜4997 行) で、ペルソナ (`spawn.persona_prompt` があればそれ) と `scenario.role_personas[役職]` をつなぎ、自分以外の名前の一覧 (`mutually_known_roles` の役職なら「(あなたと同じ側)」を付ける) を作る
   - `build_world_system_prompt` (`llm/services/world_llm_prompt.py:235`) が、これらから本文を組む (profile の値 `escape_llm_ssot_enabled` で SSoT を足す分岐は #1631 で消した)
2. できた文字列は `_world_llm_system_prompts_by_player_id` に入れ、run 中は変えない
3. 毎ターン、`DefaultPromptBuilder.build` が `WorldSystemPromptBuilder.build` (`world_runtime/default_prompt_builder_adapters.py:103`) を呼び、名前から player を引いて `WorldRuntime.build_system_prompt` (1196 行) で保持済みの文字列を返す

### 毎ターンの user メッセージ

`run_phase_a` → `WorldRuntime.build_full_prompt` (`world_runtime/world_runtime.py:2994`) → `DefaultPromptBuilder.build` (`llm/services/prompt_builder.py:583`) の順に呼ぶ。

1. `build_full_prompt` が、指示の前に置く知らせ (`_public_sns_screen_text`、`_format_ongoing_conditions`、`_format_time_since_last_gathering`) を行動指示の文の前につなぐ (3033〜3046 行)
2. `DefaultPromptBuilder.build` が部分を集める
   - 観測バッファから取り出して短期記憶に積む (613 行)
   - 現在地と周囲: `WorldRuntimeQueryAdapter` → `_build_minimal_player_state_dto` → `SpotGraphCurrentStateFormatter.format` (`llm/services/spot_graph_current_state_formatter.py:21`) で現在地の塊を作り、`SpotGraphUiContextBuilder.build` (`llm/services/spot_graph_ui_context_builder.py:513`) が `prompt_section_layout.sections_for` の順に接続先・オブジェクト・その場の人などの節を足す
   - 直近の出来事: `UnifiedRecentEventStore.get_active_timeline` を `RecentEventsFormatter.format_unified_entries` (`llm/services/recent_events_formatter.py:47`) で行にする
   - 保留中の予測と、前回の予測と実際は #1631 で消した
   - 関連する記憶、見出し、関連する学びは #1631 で消した。過去の出来事は目次つきのエピソードの【思い出せる出来事】が出す
   - 進行中のメモ (`_build_active_memos_text`、705 行)、現在の目的 (`objective_text_provider`、713 行)、ここまでのいきさつ (短期記憶の `get_mid_summary_text`。自己像と世界観は #1824 で消した)
3. `SectionBasedContextFormatStrategy.format` (`llm/services/context_format_strategy.py`) が見出しを付けて並べる (747 行)。run の設定は `stable_to_volatile` で、`_format_stable_to_volatile` (300 行) の順になる
4. 繰り返しの警告 (`_build_loop_warning_prefix`、780 行) を指示の前に付け、本文の後ろに置く (783 行)
5. `run_phase_a` に戻り、`inject_dynamic_argument_candidate_table` (`llm/services/dynamic_argument_candidates.py:363`) が【現在選べる対象引数】を指示の直前に差し込む (`phase_a.py:231`)

reason_first の起動判定 (`resolve_reason_first_gate`) が通ったターンは `run_reason_first_phase_a` に分かれ、2 段目の指示が `_REASON_FIRST_ACTION_INSTRUCTION` に替わる。保存済みの run は 206 呼び出しすべてが `one_step` だった。

### tool の定義

`build_tools_payload` (`phase_a.py:168`) → `WorldRuntime.get_tool_definitions` (`world_runtime/world_runtime.py:1599`)。

1. `_build_spot_tool_definitions` が、環境のツール (`get_spot_graph_specs`、`get_public_sns_definitions`) に profile で決まる引数を足し (`goal_update` / `goal_outcome`、`expected_result`、`expectations` は #1631 で消した)、`ToolExposure.is_exposed` で世界に無いツールを落とす
2. `split_for_phase` で共通の塊とフェーズ固有の塊に分ける
3. `_build_memory_tool_definitions` (1727 行) が記憶のツールを足す。出すかは profile の値と実行部の有無で決まり、`ToolExposure` を通らない
4. `ToolExposure.order_for_payload` (`llm/tool_exposure.py:228`) で並べ直す。reason_first なら末尾に `assess_situation`
5. `filter_definitions_for_escape_llm` (`llm/services/world_llm_turn/escape_tools.py:33`) で `set_sub_location` を落とし、OpenAI の tools の形にする

`DefaultPromptBuilder.build` も `tools` を返すが、`WorldAvailableToolsProvider` は空の一覧を返すので使われない。

### 並び

```
system: S1 冒頭 → S2 ペルソナ → S3 役職の知識 → 【世界の前提】S4 タイトルと概要 → S5 見取り図など → S6 行動の制限
        → S7【同じ局面にいる者】 → S8【渡される文面の内訳】 → S9【行動ルール】 → S10【独白と一言の書き方】
        → S11【文脈と履歴の限界】 (S12 SSoT は #1631 で消した)
user:   U1【現在の目的】 → U3【ここまでのいきさつ】 (U2【自己像と世界観】は #1824 で消した) → 【直近の出来事】(U4〜U7 の行が時刻順に混ざる)
        → (U10【関連する学び】、U11【関連する記憶】、U12 見出しは #1631 で消した)
        → (U13【進行中のメモ】は #1631 で消した) → 【現在地と周囲】(U14〜U18。並びは U19) → U20【現在選べる対象引数】
        → 繰り返しの警告 (U7) → U21 指示の前の知らせ → U22 行動指示
tools:  ALWAYS_PRESENT_TOOL_ORDER → _CONDITIONAL_TOOL_ORDER の順。run では wait, speak, (memo_* の 3 つは #1631 で消した)
        listen, travel_to, interact, drop_item, pickup_item, give_item, tend_to_player, explore, use_item, attack,
        memory_recall_episodes, memory_recall_by_handle の 17 個
```

## 1. 部分ごとの表

「作る場所」のパスは 0 章と同じく `src/ai_rpg_world/application/` からの相対。「profile」と書いたものは run の設定で有無が変わる。保存済みの run に出ていない部分は、そう書いた。

### 1-1. system prompt

| 部分 | 中身 | 作る場所 | 材料の出どころ | 分類 | Being がいま持つか |
|---|---|---|---|---|---|
| S1 冒頭 | 「あなたは次のペルソナとして行動するキャラクターである。」 | `build_world_system_prompt` 本文 (`llm/services/world_llm_prompt.py:320`) | 固定文 | 組み立ての決まり | 無 |
| S2 ペルソナ | 「あなたはエイダ、40代の医師。…秘密 (他者には開示していない): …一度きりの heal_hp 50…話し方: 落ち着いた敬体。」 | `create_world_runtime` の player ごとのループ (`world_runtime/world_runtime.py:4969-4977`)。無ければ `build_persona_block_from_character` (`world_llm_prompt.py:83`) | シナリオの `players[].persona_prompt`。無ければ `world_character`、それも無ければ名前から作る既定の人物像 | 混ざっている (Being の人格・口調と、環境での立場・秘密・ゲームの効果名) | 無 |
| S3 役職の知識 | (この run では無し) 役職に共通する、run 中変わらない知識 | 同じループ (`world_runtime.py:4980-4982`) | シナリオの `role_personas[役職]` | 環境の材料 | 無 |
| S4 タイトルと概要 | 「- 舞台のタイトル: 無人島サバイバル v4 — 協力版（座標マップ）」「- 概要: 嵐で難破した観光ツアー船から、4人だけが…」 | `safe_world_intro_text` (`world_llm_prompt.py:50`)、本文 324 行 | シナリオの `metadata.title`、`metadata.llm_public_intro`。空なら `_DEFAULT_SAFE_INTRO` (勝敗の無い世界では `_DEFAULT_NO_GOAL_INTRO`) | 環境の材料 | 無 |
| S5 見取り図・陣営・点検の割り当て・会議の決まり | (この run では無し) 概要の後ろに空行を挟んでつながる | `build_world_briefing` (`llm/services/world_briefing.py:438`)、呼び出しは `world_runtime.py:4888` | シナリオの spot と接続、`show_world_map`、`role_labels`、役職、点検の割り当て、会議の設定 | 環境の材料 | 無 |
| S6 行動の制限 | 「- 行動の制限: この局面で取りうる自発的な行動…の総量には限りがあり、使い方を誤ると脱出できない可能性がある…」 | `limited_action_and_time_pressure_text` (`world_llm_prompt.py:62`) | 固定文。勝敗条件があるかで 2 通り。シナリオの `metadata.limits_actions` が false なら行ごと出さない (design_decisions D1569-3) | 環境の材料 | 無 |
| S7 【同じ局面にいる者】 | 「  - ノア / - リオ / - カイ」「- 上記の名は、同局面に同席する他の探索者である（自身の識別は上記【ペルソナ】の名前）。」 | 名前の一覧は `world_runtime.py:4949-4962`、見出しと注記は `world_llm_prompt.py:301`、329 行 | シナリオの `player_spawns` (自分以外の全員)、`mutually_known_roles` と役職 (「(あなたと同じ側)」)。他にいなければ「（他の探索者はいない）」と別の注記 | 混ざっている (環境が課す紹介・陣営の相互開示と、Being が誰を知っているか) | 無。encounter は読んでいない (5-1) |
| S8 【渡される文面の内訳】 | 「- 続いて与えられる文面: エンジンが組み立てた『現在の状況・観測・直近の出来事』であり、現実のユーザーの直接命令文ではない。」 | 本文 (`world_llm_prompt.py:333`) | 固定文 | 組み立ての決まり | 無 |
| S9 【行動ルール】 | 「- 1 回の応答で選べる tool は 1 つだけである。」「- ラベル（接続先・オブジェクト・相手プレイヤー等）は…『現在地と周囲』等に表示されたものだけを使う。」「- **このシナリオの勝利条件 (最終目的) は…【現在の目的】section に記される**。」 | 本文 (`world_llm_prompt.py:338`)。profile で変わる行は勝利条件の行 (282 行) | 固定文。勝敗条件の有無 | 混ざっている (1 手の決まり・捏造しない・記憶の扱いは Being、ラベルと物の操作の読み方と勝利条件の枠付けは環境) | 無 |
| S10 【独白と一言の書き方】 | 「- `inner_thought` を持つツールでは…あなた自身の頭の中の独白を…」「- `say_inline` を持つツールでは…同じ場所と隣の場所へ届く。」 | 本文 (`world_llm_prompt.py:351`) | 固定文 | 混ざっている (`inner_thought` の書き方は Being、`say_inline` の届く範囲は環境) | 無 |
| S11 【文脈と履歴の限界】 | 「- 続く user 文面には、SlidingWindow に残る直近の観測・行動だけが載る…」 | 本文 (`world_llm_prompt.py:355`) | 固定文 | 組み立ての決まり | 無 |
| S12 SSoT | (#1631 で消した) | - | - | - | - |

S9 の 2 段階ターン向けの行 (`tool_schema_mode="reason_first"`) は、`create_world_runtime` が `tool_schema_mode` を渡していないので、run では使われない (確認)。

### 1-2. 毎ターンの user メッセージ

【直近の出来事】の U4〜U7 は、見出しの下で時刻順に混ざって並ぶ。

| 部分 | 中身 | 作る場所 | 材料の出どころ | 分類 | Being がいま持つか |
|---|---|---|---|---|---|
| U1 【現在の目的】 | 「- 最終目標は『救助されること』。…」「- 4 人は初対面だ。…」 | `objective_text_provider` → `_resolve_player_objective_text` (`world_runtime/world_runtime.py`) | シナリオの `players[].objective` か `metadata.llm_objective_text` を、そのまま描く | 環境の材料 (goal journal を #1631 で消すまでは混ざっていた) | 無 |
| U2 【自己像と世界観】 | (#1824 で消した。長い期間の流れはエピソードの目次が受け持つ) | - | - | - | - |
| U3 【ここまでのいきさつ】 (#1824 で【最近の流れ】から改名) | 「[最新] 難破船の浜で遺体確認と漂着物の回収を続け、…」「  気分: …」 (片付いていないことは #1824 で外した) | `get_mid_summary_text` (`llm/services/summarizing_short_term_memory.py`)、行の形は `format_mid_summary_block` | 短期記憶の L4 要約 | Being の持ち物 | 無 (整数の player 鍵) |
| U4 観測の行 | 「- [Day 1 深夜 5:30] カイが言った: 「…」」「- [Day 1 6:00] 朝になった。」「- [Day 1 6:00] 〈森の小道〉の向こうから、カイの遠くの声が聞こえる: 「…」」 | `format_observation_line_for_recent_events` (`llm/contracts/chunk_encoding.py:80`)。遠くの声の文は `player_formatter.py:474` (`observation/services/formatters/`) | 環境のイベントを観測パイプラインが本文にしたもの。`UnifiedRecentEventStore` に積まれる | 混ざっている (環境の観測と、遠くの声で話者の名前を出すかという誰を知っているかの判断) | 無 (`PlayerId` 鍵) |
| U5 自分の行動の行 | 「- [Day 1 8:30] [行動] 「釣り場」に fish_stream した → [失敗] \| error_code=INTERACTION_PRECONDITION_FAILED \| tool=interact \| 行動が拒否された: 釣竿が必要だ。」「  心の声: …」「（3 名に届いた。ぼんやり=1）」、失敗の観測「interact を試みたが失敗した: … 修正のヒント: …」 | `format_action_result_line_for_recent_events` (`chunk_encoding.py:96`)、失敗の観測は `intent/action_failed_observation_emitter.py:128`、届いた人数は `speech/services/audience_feedback.py:119` | action_result_store (tool 名・引数・`inner_thought`・結果・`error_code`) と、環境が返す結果の文・届いた人数・修正のヒント | 混ざっている (環境の結果の文と、Being の行動と内心の記録) | 無 (`PlayerId` 鍵) |
| U6 内省の観測行 | (#1631 で消した) | - | - | - | - |
| U7 繰り返しの警告 | 指示の前の「⚠ 直前のあなたは `wait` を同じ引数で 2 ターン連続実行しました。…」(run では 1 呼び出し)。直近の出来事に入る「⚠ … を 3 回続けて同じ引数で実行している。…」(run には出ていない) | `_build_loop_warning_prefix` (`llm/services/prompt_builder.py:559`)、直近の出来事の行は `llm/services/loop_guard_warning.py` | `ToolCallLoopGuardService` の連続記録 | Being の持ち物 | 無 (整数の player 鍵) |
| U8 【前回の予測と実際】 | (#1631 で消した) | - | - | - | - |
| U9 【保留中の予測】 | (#1631 で消した) | - | - | - | - |
| U10 【関連する学び】 | (#1631 で消した) | - | - | - | - |
| U11 【関連する記憶】 | (#1631 で消した。目次つきのエピソードの【思い出せる出来事】が代わる) | - | - | - | - |
| U12 さっき思い出した記憶の見出し | (#1631 で消した) | - | - | - | - |
| U13 【進行中のメモ】 | (#1631 で消した。メモ帳の【メモ】が代わる) | - | - | - | - |
| U14 現在地の塊 | 「現在地: 高地の泉 (初めて訪れた)」「  山の中腹に湧く泉。…」「雰囲気: …」「天候: 弱い晴れ（屋外）」「現在時刻: Day 1 12:00」「時刻帯: 昼」 | `SpotGraphCurrentStateFormatter.format` (`llm/services/spot_graph_current_state_formatter.py:21`)、注記は `_annotate_current_spot_familiarity` (`llm/services/spot_graph_ui_context_builder.py:628`)。死亡後の【いまの存在状態】は同 529 行 | 世界の snapshot (spot の名前と説明、眺望、天候、時刻、会議の状況、点検の進み具合、残り行動量、自分の状態)。「(初めて訪れた)」は encounter | 混ざっている (環境の描写と、行った場所の記録) | 無 (encounter はシナリオの spot ID と `PlayerId` の鍵) |
| U15 この場で働きかけられるもの | 「接続先:」「  - "山麓への道" → "山麓"（通行可）」「オブジェクト:」「  - "湧水の口" (今は汲めない・時間を置けば戻る) — …」「      いまできない: 湧水を汲む → "drink_water"（…）」「同じ場所に居るモンスター: (このスポットにモンスターはいない)」 | `SpotGraphUiContextBuilder` の `_build_connection_section` (720 行)、`_build_object_section` (801 行)、`_build_monster_section` (1078 行)、地面のアイテム・商人・市場・所持金・取引の節 | 世界の snapshot とシナリオの物と操作。商人などはシナリオで宣言したときだけ | 環境の材料 | 無 |
| U16 同じ場所にいるプレイヤー | 「同じ場所にいるプレイヤー: (倒れていない相手には give_item で所持品を直接渡せる)」「  - "エイダ" (初めて会った)」 | `_build_entity_section` (`spot_graph_ui_context_builder.py:927`)、注記は `_player_familiarity_annotation` (687 行) | 世界の snapshot (その場の人、倒れているか、倒れた人の持ち物、人に使える操作)、encounter (「(初めて会った)」) | 混ざっている (環境の在室と、Being が誰を知っているか) | 無 (encounter は `PlayerId` と名前の鍵) |
| U17 所持アイテム | 「所持アイテム:」「  - "火打ち石" — 枯れ葉に火を移すための火打ち石。 (火を起こす道具。…)」 | `_build_inventory_section` (`spot_graph_ui_context_builder.py:1346`) | 世界の所持品とシナリオのアイテム定義 | 環境の材料 | 無 |
| U18 身体の状態 | 「身体の状態:」「  HP: 良好（100/100）」「  空腹: 少し（24/100）、前回 +1」 | `_build_needs_section` (`spot_graph_ui_context_builder.py:1134`)、状態効果の節 (1170 行) | 世界の HP・空腹・疲労と前回からの差 | 環境の材料 | 無 |
| U19 【現在地と周囲】の中の節の順とフェーズ別の出し分け | 自由時間は接続先 → オブジェクト → その場の人 → モンスター → … → 所持アイテム → 身体の状態。会議中は人・所持品・身体だけ | `prompt_section_layout.py` の `FREE_ROAM_SECTIONS` / `MEETING_SECTIONS` / `sections_for` (157 行) | 固定の並び | 組み立ての決まり | 無 |
| U20 【現在選べる対象引数】 | 「- travel_to.destination_label: "川の上流", "山麓", "墜落機の残骸"」「※ 一覧にあることは操作の成功を保証しない。…」 | `render_dynamic_argument_candidate_table` (`llm/services/dynamic_argument_candidates.py:342`)、差し込みは `inject_dynamic_argument_candidate_table` (363 行) | U14〜U18 を作るときに集めた対象 (`tool_runtime_context`) と、いま出しているツールの名前 | 環境の材料 | 無 |
| U21 指示の前の知らせ | (この run では無し) 【公開 SNS】の画面、【進行中の異常】、【時間の経過】 | `build_full_prompt` (`world_runtime.py:3033-3046`) が `_public_sns_screen_text` (3085 行)、`_format_ongoing_conditions` (3093 行)、`_format_time_since_last_gathering` (3107 行) を行動指示の前につなぐ | 公開 SNS の画面、シナリオの `ongoing_conditions` と世界のフラグ、会議の区間 | 環境の材料 | 無 |
| U22 行動指示 | 「利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。」 | `_ESCAPE_GAME_ACTION_INSTRUCTION` (`world_runtime.py:2341`)。`tool_choice=auto` では `escape_game_action_instruction` (2346 行) がいま呼べるツール名を足す。2 段目は `_REASON_FIRST_ACTION_INSTRUCTION` (`phase_a.py:691`) | 固定文と、いま出しているツールの名前 | 組み立ての決まり | 無 |
| U23 節の骨組み | 見出しの名前、並び、「観測（世界から届いた事象）と、あなた自身の行動の結果が時系列に並びます。」、空のときの「（情報なし）」、【関連する記憶】の添え書き | `SectionBasedContextFormatStrategy` と `_format_stable_to_volatile` (`llm/services/context_format_strategy.py:300`)、置き文は 193〜195 行 | 固定の並び (`prompt_section_order` で `legacy` を選ぶ口は #1631 で消した) | 組み立ての決まり | 無 |

「（直近の出来事はありません）」は `format_unified_timeline_as_recent_events_bullets` が行の無いときに返す置き文 (`llm/contracts/chunk_encoding.py:30`、215 行)。本文が空にならないので、`_PLACEHOLDER_RECENT_EVENTS`「（なし）」はこの経路では出ない (確認)。

### 1-3. tool の定義と説明

| 部分 | 中身 | 作る場所 | 材料の出どころ | 分類 | Being がいま持つか |
|---|---|---|---|---|---|
| T1 環境の行動ツールと固有の引数 | `travel_to`「スポットグラフ上で、指定した接続先へ移動を開始する…」、`interact` の説明「利用可能な action_name と現在の object 状態は『現在の状況』section の各オブジェクト行に出ている…」、引数 `destination_label`、`target_label`、`action_name` など | `get_spot_graph_specs` (`llm/services/tool_catalog/spot_graph.py:1005`)、`get_public_sns_definitions` (`tool_catalog/public_sns.py:41`)、絞り込みは `_build_spot_tool_definitions` (`world_runtime/world_runtime.py:1701`) | ツールカタログの固定の定義。出すかは `ToolExposure.is_exposed` (同時行動、会議、商人・市場の宣言、シナリオの `disabled_tools`) | 環境の材料 (説明がプロンプトの節名を参照している。4 章で消す) | 無 |
| T2 主観の引数 `inner_thought` | 「この行動を選ぶ直前の、あなた自身の頭の中の独白を一文で。書き方は【独白と一言の書き方】。」。reason_first では行動ツールから外し、`assess_situation` に集める | `inner_thought_property` (`tool_catalog/inner_thought.py:31`)、各ツールの定義に直接入っている。reason_first は `assess_situation_definition` (`tool_catalog/subjective_action.py:231`)、`strip_reason_first_action_subjective_schema` (283 行) | 固定の定義。解決済み設定の `reason_first_two_step_enabled` | Being の持ち物 | 無 (書いた値は action_result_store、`PlayerId` 鍵) |
| T3 発話の引数 `say_inline` | 「この行動をしながら発する一言 (任意、200 字以内)。書き方は【独白と一言の書き方】。」 | `say_inline_property` (`tool_catalog/say_inline.py:47`)、各ツールの定義に直接入っている | 固定の定義 | 環境の材料 (説明が Being 側の節名を参照している。5-3) | 無 |
| T4 予期の引数 `expectations` | (#1631 で消した) | - | - | - | - |
| T5 目的の引数 `goal_update` / `goal_outcome` | (#1631 で消した) | - | - | - | - |
| T6 記憶のツール | `episode_recall`、`episode_revise_index` (能動想起の 4 つの道具と memo_* の 3 つの道具は #1631 で消した) | `get_memory_specs` (`tool_catalog/memory.py`)、呼び出しは `_build_memory_tool_definitions` (`world_runtime.py`) | 固定の定義。目次つきのエピソードの設定、実行部の有無。`ToolExposure` を通らない | Being の持ち物 | Being のエピソード。実行部はゲームのパッケージにある (#1469) |
| T7 tool の並びと出し分け | 共通の塊が先、フェーズ固有の塊が後。run では 17 個 (0 章) | `ToolExposure.order_for_payload` と `_PAYLOAD_TOOL_ORDER` (`llm/tool_exposure.py:147`、228 行)、`split_for_phase`、`filter_definitions_for_escape_llm` (`llm/services/world_llm_turn/escape_tools.py:33`) | 固定の並び。会議中か、投票済みか、死亡後か | 組み立ての決まり | 無 |

### 1-4. 分類の集計

全 42 部分 (system prompt 12、毎ターンのメッセージ 23、tool 7)。

| 分類 | 件数 |
|---|---|
| 環境の材料 | 10 |
| Being の持ち物 | 14 (うち 5 件は、材料がまだ Being の store になく、`PlayerId` か整数の player を鍵にした store にある。U2、U3、U6、U7、U8) |
| 混ざっている | 10 |
| 組み立ての決まり | 8 |

1 章を作り直して数え直した。部分の数と分類の件数は元のままで、Being の持ち物のうち `PlayerId` か整数の player を鍵にした store にある件数を 7 から 5 に直した。

#1631 で消した部分 (U6、U8、U13、T4、T5) と、goal journal を消して環境の材料になった U1 は、この集計に反映していない。

## 2. 環境が公開する情報の型の案

### 2-1. 既存の契約の型で足りるもの

| 型 (being/contract) | 足りる部分 | 足りない点 |
|---|---|---|
| `Observation` (observation.py) | 観測の行 (本文・時刻の表示・経路)。在室の変化 (誰が入った・出た) を会った人の記録に流す材料。`subject_name` で「誰の発言か」を名前で受け取れる | 本文に話者の名前が焼き込まれている。Being が「知らない人」と判断しても本文から名前を外せない (遠くの声)。後述の `body_if_subject_unknown` |
| `AgentMove` (agent_move.py) | 行動の行の前半 (tool 名・引数・内心・予期・目的の更新) | 予期の型が文字列 1 本。いまの `expectations` は what / when / likelihood の配列。`intention` / `emotion_hint` / `goal_outcome` は引数に残す扱い (#1472) |
| `OwnActionResult` 経路の `Observation` | 行動の結果の文と成否 | `error_code` を運ぶ欄が無い。いま短期記憶に出している `error_code=… \| tool=…` は再現できない (意図して落としてよいと考える) |
| `EnvironmentEntry` (environment_entry.py) | 環境の名前、本人の名前、課す目的 | system prompt の環境側の文面と、入った時点で知っている人を運ぶ欄が無い |
| `ObservedTime` | 観測と行動の時刻の表示 | — |

### 2-2. 足りないもの (新しい型の案)

型の細部は、#1520 の段 3 に入るときに実物を見ながら決める。ここに書くのは、いまのプロンプトを再現するのに要るものの見積もり。

| 型の名前 (案) | 主な欄 | いつ渡すか | 再現する部分 |
|---|---|---|---|
| `EnvironmentEntry` の拡張 (または `EnvironmentBriefing`) | `title`、`public_intro` (概要と見取り図)、`rules` (行動の制限、勝利条件の枠付け)、`assigned_role` (その環境での立場・背景・秘密・役職の共通知識)、`interface_notes` (この環境の画面の読み方)、`introductions` | 環境に入るとき 1 回。run 中は不変 | system prompt の環境の部分 |
| `Introduction` | `name`、`note` (「あなたと同じ側」のような、環境が課す関係の知識) | `EnvironmentEntry` の欄として | 最初から知っている人。陣営の相互開示 |
| `EnvironmentView` | `place` (現在地の名前)、`time`、`surroundings` (【現在地と周囲】の本文をそのまま)、`present_others`、`argument_candidates` (【現在選べる対象引数】の表)、`notices`、`own_condition` (身体の状態) | 毎ターン。#1520 のコメントの原則では「毎ターン置き換わる部品」として届く | 毎ターンのメッセージの、いまの画面 |
| `PresentOther` | `name` (その場で見える名前)、`condition` (「倒れて動かない」など)、`actions` (人に使える操作の表示) | `EnvironmentView` の欄として | その場にいる人。Being が会った人の記録を引いて「初めて会った」を足せるよう、名前と状態を本文から分ける |
| `Notice` | `heading`、`body`、`position` (現在地の後ろ / 指示の前) | `EnvironmentView` の欄として | 現在地の後ろと、指示の前に出る知らせ |
| `ToolSpec` | `name`、`description`、`parameters` (JSON Schema)、`always_present` | 環境に入るときに全集合。毎ターン「いま出す名前の集合」 | tool の定義 |
| `Observation.body_if_subject_unknown` (欄の追加) | 主体を知らない受け手向けの本文 (「〈道〉の向こうから、誰かの遠くの声が聞こえる」) | 観測として | 遠くの声。Being が「知らない」と判断したときに使う |

## 3. Being が持つものの案

### 3-1. 既存の store で足りるもの

| 部分 | store | 注意 |
|---|---|---|
| 現在の目的 | (goal journal は #1631 で消した) | いまはシナリオの目的の文をそのまま描く。Being が目的を持つ store は無い |
| 関連する学び | (#1631 で消した) | - |
| 関連する記憶 | (#1631 で消した) | - |
| 進行中のメモ | memo | 表示の `tick=…, 経過 … tick` を Being のターン数に替える |
| 記憶ツールと主観の引数 | 引数と記憶ツール | ツールの実行部はゲームのパッケージにある (#1469) |

### 3-2. 足りないもの

| 必要なもの | いまの置き場所 | 案 |
|---|---|---|
| **誰を知っているか** (【同じ局面にいる者】、遠くの声、「初めて会った」) | encounter (`InMemoryEncounterMemory`、`PlayerId` 鍵、世界の snapshot)。初期配置の同席者は記録されない | `AcquaintanceRecord` を Being の store に置く。鍵は (環境の名前, 名前の文)。欄は初めて会ったターン、最後に見たターン、回数、どう知ったか (紹介された / 会った / 声を聞いた)、注記。時計は Being のターン数。#1465 の会った人の記録と同じ作業 |
| 行った場所 (「初めて訪れた」) | encounter (シナリオの spot の文字列 ID が鍵) | 同じ store に場所の種類で持つ。鍵は場所の名前の文 |
| 短期記憶 (直近の出来事、要約) | `UnifiedRecentEventStore`、`SummarizingShortTermMemory`、action_result_store、観測バッファ。いずれも `PlayerId` 鍵 | #1465 のとおり Being の snapshot へ |
| 繰り返しの見張り | `ToolCallLoopGuardService` (整数の player 鍵) | Being の store へ。snapshot に入っていなければ再開で消えている (推測) |
| 人格 | シナリオの `persona_prompt` に、環境での立場と一体で書かれている | Being の人格と、環境が渡す `assigned_role` に分ける。分けるかは #1469 で決める。最初は `persona_prompt` を丸ごと `assigned_role` として受け取れば再現できる |
| 自分の名前 | `EnvironmentEntry.self_name` (型はあるが run に配線されていない) | 入るときに受け取り、短期記憶や記憶の文の中の自分を見分けるのに使う |

### 3-3. encounter を Being に移す前に分けるもの

encounter はいま、環境の判定にも使われている (確認)。

- 初めて見たモンスターを観測として届ける一度きりの判定 (`world_runtime.py` 5822 行付近)
- 倒れている人を初めて見つけた観測の一度きりの判定と、加害者に発見の観測を出さない処理 (5870 行付近、6747 行付近)
- シナリオの出来事の既読 (`encounter_observation_collector.py`)

これらは「環境が観測をもう出したか」の記録で、Being の記憶ではない。encounter をそのまま Being に移すと、環境が Being の store を読んで観測を出すかを決める形になり、向きが逆になる。先に環境側の記録 (世界の snapshot) へ分ける。鍵にゲームの整数 ID が入っている点も、Being に移すと「ゲームの ID を Being に入れない」に反する。

## 4. 組み立ての決まりの置き場所

| 決まり | 置き場所 | 理由 |
|---|---|---|
| system prompt の骨組み、見出しの名前、節の並び、空のときの置き文、行動指示、Being の節の文面 | Being (`being/application` に組み立て役を置く) | Being が環境を替えても同じ書式で自分の記憶を読む |
| 1 手の決まり (tool call は 1 回 1 つ、内心、予期、記憶の扱い、捏造しない) | Being | 環境によらない |
| 環境の画面の読み方 (ラベル、物の操作、`say_inline` の届く範囲) と勝利条件の枠付け | 環境が `interface_notes` / `rules` として文で渡し、Being は決まった位置に並べる | 画面の語彙と発話の届く範囲は環境の決まり。SNS の環境では別の文になる |
| 【現在地と周囲】の中の節の順と、フェーズ別の出し分け | 環境 | 環境の画面の内部の決まり |
| 【現在選べる対象引数】の書式 | 環境 (描いた文を渡す)。Being は行動指示の直前に置く | 候補は環境のツールの引数で、意味を知っているのは環境 |
| tool の並び | Being | Being のツールと環境のツールの両方を並べるのは Being。いまの並びとは変わる (意図した差分) |
| ツールの説明が参照するプロンプトの節名 | 環境のツールの説明からは消す。Being のツールと Being が足す引数の説明だけが Being の節名を参照する | 環境が Being の画面構成を知らないようにする |

## 5. 制約上の問題点

### 5-1. 「誰を知っているか」のいまの記録は不完全 (確認)

- encounter の人の記録は「他人が同じ場所に入ってきた」観測からしか作られない。初期配置で同じ場所にいた相手は記録されない
- 実例: tick 1〜3 は 4 人とも同じ浜にいて注記なし。tick 5 でリオから見たノアに「(初めて会った)」が付き、tick 6〜8 も付き続ける。一方、system prompt は tick 1 から 3 人の名前を挙げている

### 5-2. プレフィックスキャッシュ (`stable_to_volatile`)

- 知っている人の一覧を会うたびに system prompt に描くと、以後のキャッシュがすべて切れる。このため、一覧は毎ターンのメッセージの変わりにくい側に出すと決めた (#1520 のコメント)
- 遠くの声を知らない人として描く判断は、短期記憶に積む時点で確定させる。描く時点で判断すると、あとで相手を知ったときに過去の行が書き換わり、直近の出来事の安定した先頭が崩れる
- tool の並びを Being が決め直すと、移行した run で 1 回だけ並びが変わる。決めたあとは run 中に変えないことを試験で固定する
- system prompt を Being が組み立てても、移行の PR では、いまの system prompt の hash を試験で固定して、バイト同一を保てる

### 5-3. tool 名を書くときの露出判断

- 記憶ツールの露出は `ToolExposure` の外 (profile と実行部の有無) で決まる。Being が組み立てるなら、Being のツールの露出を 1 か所で決め、Being の節の本文もそれを通す
- system prompt とツールの説明が、環境の `say_inline` 引数の名前を Being 側の固定文に書いている。`say_inline` を出さない環境では、無い引数を宣伝する。環境の `interface_notes` に移す
- `tests/demos/test_disabled_tools_vanish_from_the_prompt.py` は環境のツールを 1 つずつ無効にする検査で、Being のツールは対象外 (推測)。同じ総当たりを Being 側にも持つ

### 5-4. ゲームの ID・語が Being の側に入る箇所

| 箇所 | 入っているもの |
|---|---|
| メモ | `tick=11, 経過 1 tick` |
| encounter の鍵 | シナリオの spot 文字列 ID、`monster_{整数}`、`player_{整数}`、event_id |
| 短期記憶の行動の行 | `error_code=INTERACTION_PRECONDITION_FAILED`、`tool=interact` |
| 目的 | (goal journal と一緒に #1631 で消した) |
| system prompt | 実装の語「SlidingWindow」 |
| 人格 | ゲームの効果名「heal_hp 50」(シナリオの文。直すのはシナリオ側) |

環境側の不具合として見つけた 4 件は #1521 にした (話しかける相手の候補が内部ラベル、実在しない【ペルソナ】の参照、`goal_update` の説明の `intention`、`destination_label` の説明の節名)。

## 6. 移す順番の案

各段で、移す前後のプロンプトを保存済みの run の `prompt_dataset` と突き合わせ、意図した差分以外が無いことを確かめる。実 LLM は呼ばない。

- **段 0: 再現の物差し**。system prompt の hash と、固定の状態から組んだ毎ターンのメッセージを試験で固定する
- **段 1: 誰を知っているか** (最初の一歩)
  1. 環境の一度きりの判定を encounter から分ける (3-3)。プロンプトは変わらない
  2. 知人の記録を Being に作る。初期配置の同席者を記録しない欠けもここで直す
  3. 入るときに紹介を受け取る (`EnvironmentEntry` に `introductions`)
  4. 知っている人の一覧を Being が描く。毎ターンのメッセージの変わりにくい側の【知っている人】に出す
  5. 遠くの声の名前。`Observation` に `body_if_subject_unknown` を足し、Being は短期記憶に積む時点で知人の記録を引く
  6. 紹介しない設定をシナリオでどう宣言するかを決める
- **段 2: 短期記憶と行動の記録を Being に** (#1465 の残り)。行動の行の `error_code` / `tool=` を残すかを決める
- **段 3: 毎ターンのメッセージを Being が組み立てる**。いまの画面の部品を受け取る。「初めて会った」「初めて訪れた」を、環境の文から Being の注記に移す。他人の停滞感を環境の画面から外す
- **段 4: system prompt を Being が組み立てる**。環境の部分を環境側に、骨組みを Being 側に分ける。文面を変えずに分ければバイト同一
- **段 5: tool を Being が組み立てる**。環境は `ToolSpec` を公開し、Being が主観の引数と自分のツールを足して並べる
- **段 6: Being の側に残るゲームの語を消す** (5-4)
- **段 7: 人格を分ける** (#1469 で決める)

段 3〜5 は新しく作るコードなので、#1469 の方針どおり最初から `being/` に置く。段 2 と既存の store の移し替えは、#1469 の移し替えの PR (挙動を変えない) と混ぜない。
