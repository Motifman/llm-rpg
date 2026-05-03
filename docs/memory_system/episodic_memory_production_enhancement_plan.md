# Episodic Memory — 本番強化・LLM エンコード計画（ドラフト）

この文書は [episodic_memory_system_spec.md](./episodic_memory_system_spec.md) と現状の `main` 実装を前提に、**MVP（決定論ドラフト + 受動想起配線）の次**に進める作業を整理する。  
Git・レビュー・worktree は [memory_feature_workflow.md](./memory_feature_workflow.md)。既存の MVP 分割は [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)。

## 0. 現状の事実（認識合わせ）

### 0.1 複数出来事 → 1 エピソードの「基盤」はまだない

- **現状**: **1 回の tool 実行確定 = 1 `SubjectiveEpisode`**（`ActionEpisodeDraftBuilder` + orchestrator の保存経路）。ルールベースの **cue・ドラフト・ストア**はあるが、**複数ターン・複数材料を束ねるチャンク境界とマージ器は未実装**。
- **仕様上の本流**は、複数 `ExperienceTrace` から 1 エピソードを生成すること（`episodic_memory_system_spec.md` §2.1–2.2）。これは **別フェーズ（チャンカー + エンコーダ入力設計）**。

### 0.2 エピソード作成経路は「行動（tool）由来」が中心

- **`LlmAgentOrchestrator`**: tool 実行結果が確定した後に `_persist_subjective_episode_after_tool_command` で保存。  
- **観測**: プロンプト上の `build_situation_episodic_cues` やドラフトの周辺文脈としては使うが、**「観測だけのターン → 新規 `SubjectiveEpisode` を 1 件作る」専用経路は未実装**（計画でも MVP 後段）。

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
- **LLM によるエピソード化**: チャンク境界の実装は後回し。**コンテキスト整備・プロンプト・バリデーション・実験経路**を先に固め、本番配線は別タスク。

---

## 2. ワークストリームと依存（並列の目安）

依存が弱いものから並列しやすい。太文字はオーケストレータが **別 worktree / 別ブランチ**に割りやすい単位。

| ID | 内容 | 依存・注意 |
|----|------|------------|
| **W1** | **ドキュメント**: `recall_text` の長文化方針、LLM 生成範囲、観測エピソードの定義を spec / implementation_plan に反映 | 先に書いてもよい（実装と矛盾しないよう随時更新） |
| **W2** | **`recall_text` 長文化**: `SubjectiveEpisode` バリデーション・実験スクリプトの上限・プロンプト指示の更新 | W1 と並列可 |
| **W3** | **LLM 本番配線**: tool 後（または非同期）にエンコーダ呼び出し、`interpreted` / `recall_text` をマージして store。失敗時フォールバック | `ActionEpisodeDraftBuilder`・store 契約は安定していることが前提 |
| **W4** | **§0.2 situation_cues 補強**: 直近 `IActionResultStore` 等から `action:` 等 | 受動想起と独立気味で並列しやすい |
| **W5** | **永続化**: `IEpisodicEpisodeStore` の SQLite 実装・マイグレーション方針 | W3 より後でも可。単体で設計→実装 |
| **W6** | **観測由来エピソード導線**: 観測イベント→草案ビルダ相当→`put`（粒度・重複防止は設計課題） | orchestrator とは別ハンドラになりやすい |
| **W7** | **デモ整合**: `demo_llm_*` が wiring と同等の記憶挙動になるよう最小修正または注記強化 | W1 と一緒でも可 |
| **W8** | **テスト**: LLM モックのエンコーダ結合、長文 recall のバリデーション、 sqlite store | W3・W5 に追随 |

### 2.1 推奨マージ順（コンフリクト回避）

1. W1（doc）＋ W7（デモ注記）は早期マージ可能。  
2. W2（長さ・バリデーション）は単体でマージしやすい。  
3. W4 は `episodic_cue_rules` / `prompt_builder` 触りやすい → **W3 と同ファイルを触る場合は直列 or 小 PR で順番**。  
4. W3 → W8 の一部。  
5. W5 はストア実装が独立なら並列、**W6 はタッチポイントが広いので最後でもよい**。

---

## 3. LLM エンコード（チャンク後置きのときに揃えておくもの）

- **入力パッケージ（DTO）**: 決定論ドラフト + ペルソナ + 状況スナップショット + source facts（検証用）。将来は trace のリストに差し替え可能な形。
- **出力**: 当面 `interpreted` + `recall_text`（長めの語り OK）。事実・cue・`observed` は LLM で変更しない。
- **経路**: まず `local_experiments` または専用アプリケーションサービスで検証 → orchestrator へ。

---

## 4. 参照

- [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)
- [memory_feature_workflow.md](./memory_feature_workflow.md)
