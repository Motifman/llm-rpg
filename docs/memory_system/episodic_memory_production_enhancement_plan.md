# Episodic Memory — 本番強化・LLM エンコード計画（ドラフト）

この文書は [episodic_memory_system_spec.md](./episodic_memory_system_spec.md) と現状の `main` 実装を前提に、**MVP（決定論ドラフト + 受動想起配線）の次**に進める作業を整理する。  
Git・レビュー・worktree は [memory_feature_workflow.md](./memory_feature_workflow.md)。既存の MVP 分割は [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)。

## 0. 現状の事実（認識合わせ）

### 0.1 チャンク経路（第 1 版）でエピソードが保存される

- **現状**: **チャンクが閉じられ**、かつ `ChunkEncodingInput` が `chunk_encoding_episode_generation_allowed` を満たす（第 1 版: 区間内に少なくとも 1 件の `ActionResultEntry`）ときだけ、`ChunkEpisodeDraftBuilder` → 任意で `EpisodicChunkSubjectiveFieldsService`（**`interpreted` / `recall_text` のみ**）→ `IEpisodicEpisodeStore.put`。**複数ターンにまたがる材料の束ね**と **観測ヒントによる閉鎖**（`decide_chunk_boundary`）は実装済み。協調は `EpisodicChunkCoordinator`。
- **仕様上の本流**（複数 `ExperienceTrace` から 1 エピソード）は、[episodic_memory_system_spec.md](./episodic_memory_system_spec.md) §2.1–2.2。チャンク入力は trace 一覧への将来差し替えを意識した `ChunkEncodingInput`。

### 0.2 エピソード作成のきっかけは「チャンク閉鎖＋行動あり」が主

- **`LlmAgentOrchestrator`**: tool 実行が成功し `IActionResultStore` に記録された直後、`EpisodicChunkCoordinator.after_action_recorded(..., explicit_segment_close=True)` を呼ぶ（**即 `put` はしない**）。境界アルゴリズムが HOLD なら同一区間内で行動が蓄積され、閉鎖までは store に載らない。
- **観測**: `drain` → `SlidingWindowMemory.append_all` で **プロンプト build が使うのと同じ手順**に揃えたうえで、区間内観測は **材料・境界ヒント**（`summarize_observation_boundary_hints`）。1 ターン内では `build` が先・tool 後に `after_action_recorded` となるが、いずれも同一バッファ／ウィンドウに対し同順の drain→追記を行う。**観測だけの区間では第 1 版はエピソード生成を起動しない**（`chunk_encoding_episode_generation_allowed` が偽）。

### 0.3 「観測のみ episode」が指すもの

- **意味**: 必ずしも「観測 1 件 = エピソード 1 件」ではない。  
  **「自発的な world tool が無いターンでも、知覚した出来事を体験として保存する」**ための、観測パイプラインからの **エピソード化導線**（どのイベントで・どの粒度で `SubjectiveEpisode` を `put` するか）が未整備、という意味で計画に載っている。

### 0.4 デモスクリプト（観測・デモ）について

- **`scripts/demo_llm_prompt_inspection.py` / `demo_llm_multiturn_prompt_inspection.py`** は、`create_llm_agent_wiring` と **別構成**で `DefaultPromptBuilder` 等を組むことがある。
- **リスク**: 本番ゲーム経路では **`create_llm_agent_wiring` が共有 `InMemorySubjectiveEpisodeStore` と受動想起を渡す**が、デモだけ **ストア未共有・受動想起未注入**のままだと、「プロンプトを見るデモ」では **関連する記憶が常に空**に見える。
- **対応案**: デモを wiring 経由に寄せる、またはファイル先頭に「エピソード記憶は本クラインと非同等」と短く注記する（既に一部追記あり）。

---

## 1. 方針（ユーザー合意に沿ったもの）

- **`recall_text`**: 当面は **やや長め**でよい（上限は後で最適化）。**保存用とプロンプト用に分けない**（問題が出てから検討）。
- **LLM によるエピソード化**: **チャンク閉鎖後**に限り `interpreted` / `recall_text` をマージ（`EpisodicChunkSubjectiveFieldsService`・`IEpisodicChunkSubjectiveCompletionPort`）。事実・cue・`observed`・who/where/outcome 等はルール側。**コンテキスト整備・プロンプト・バリデーション・実験経路**を先に固め、オーケストレータ配線は `create_llm_agent_wiring` で共有ストア＋協調が既定。
- **想起後の再解釈**: 受動想起時には LLM を呼ばず、想起 episode と現在状況 snapshot をキャラクター別 buffer に蓄積する。既定では **10 LLM ターンごと**に最大 **8 episode** をまとめて `EpisodicReinterpretationCoordinator` が LLM JSON で再解釈する。結果は `EpisodicReinterpretationEntry` として journal に追記し、通常 prompt 参照では最新 `active` の `current_recall_text` だけを使う。旧 entry は `superseded` として監査用に残すが、通常の関連記憶 prompt へ混ぜない。
- **主観回想の長さ・声**: 初期 `recall_text` と再解釈後 `current_recall_text` は、短い事実要約ではなく、キャラクター本人の一人称による TRPG リプレイ風の主観回想（目安 250〜450 字、検証上限は 700 字）に寄せる。

---

## 2. ワークストリームと依存（並列の目安）

依存が弱いものから並列しやすい。太文字はオーケストレータが **別 worktree / 別ブランチ**に割りやすい単位。

| ID | 内容 | 依存・注意 |
|----|------|------------|
| **W1** | **ドキュメント**: `recall_text` の長文化方針、LLM 生成範囲、観測エピソードの定義を spec / implementation_plan に反映 | 先に書いてもよい（実装と矛盾しないよう随時更新） |
| **W2** | **`recall_text` 長文化**: `SubjectiveEpisode` バリデーション・実験スクリプトの上限・プロンプト指示の更新 | W1 と並列可 |
| **W3** | **LLM 本番配線（主観フィールドのみ）**: チャンク閉鎖後にエンコーダ／`EpisodicChunkSubjectiveFieldsService` 呼び出し、`interpreted` / `recall_text` をマージして store。失敗時フォールバック | `ChunkEpisodeDraftBuilder`・store・チャンク協調が安定していることが前提 |
| **W4** | **§0.2 situation_cues 補強**: 直近 `IActionResultStore` 等から `action:` 等 | 受動想起と独立気味で並列しやすい |
| **W5** | **永続化**: `IEpisodicEpisodeStore` の SQLite（既存）・**リンク／セマンティック**は別計画 [episodic_memory_link_semantic_sqlite_plan.md](./episodic_memory_link_semantic_sqlite_plan.md) | W3 より後でも可。リンク・セマンティックは **メモリグラフ専用ブランチ**で進める |
| **W5b** | **セマンティック昇格の増分処理**: [episodic_semantic_promotion_incremental_plan.md](./episodic_semantic_promotion_incremental_plan.md)。推奨で W5 より後 | `list_all_links` スキャン回避。永続化 PR とポート追加の順序に注意 |
| **W6** | **観測由来エピソード導線**: 観測イベント→草案ビルダ相当→`put`（粒度・重複防止は設計課題） | orchestrator とは別ハンドラになりやすい |
| **W7** | **デモ整合**: `demo_llm_*` が wiring と同等の記憶挙動になるよう最小修正または注記強化 | W1 と一緒でも可 |
| **W8** | **テスト**: LLM モックのエンコーダ結合、長文 recall のバリデーション、 sqlite store | W3・W5 に追随 |
| **W9** | **想起後再解釈**: recall buffer / reinterpretation journal / 10 ターン flush / active recall 優先 prompt / SQLite 永続化 | W3・W5 後。episode 事実・cue は変更しない |

### 2.1 推奨マージ順（コンフリクト回避）

1. W1（doc）＋ W7（デモ注記）は早期マージ可能。  
2. W2（長さ・バリデーション）は単体でマージしやすい。  
3. W4 は `episodic_cue_rules` / `prompt_builder` 触りやすい → **W3 と同ファイルを触る場合は直列 or 小 PR で順番**。  
4. W3 → W8 の一部。  
5. W5 はストア実装が独立なら並列、**W6 はタッチポイントが広いので最後でもよい**。

---

## 3. LLM エンコード（チャンク閉鎖後に揃えておくもの）

- **入力パッケージ（DTO）**: `ChunkEncodingInput`（決定論ドラフトの材料：統一タイムライン・区間内行動・観測）+ ペルソナ断片 + source facts（検証用）。将来は trace のリストに差し替え可能な形。
- **出力**: 当面 `interpreted` + `recall_text`（長めの語り OK）。事実・cue・`observed` は LLM で変更しない。
- **経路**: `local_experiments` または `EpisodicChunkSubjectiveFieldsService` で検証 → `create_llm_agent_wiring` の既定注入（LiteLLM 等が使える環境）へ。

---

## 4. 参照

- [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)
- [memory_feature_workflow.md](./memory_feature_workflow.md)
