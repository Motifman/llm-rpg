# セマンティック昇格のイベント駆動・増分処理 — 実装計画

この文書は [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md) と [memory_feature_workflow.md](./memory_feature_workflow.md) に従い、`EpisodicSemanticClusterPromotionService` が **毎回 `list_all_links_for_player` で全リンクを走査する**現状を改善する。

**推奨ブランチ名の例**: `feature/episodic-semantic-promotion-incremental`

**前提**: `EpisodicSemanticClusterPromotionService` が `on_after_tool_turn` で全グラフから強リンク隣接表を構築している（現行コード参照）。

---

## 1. 問題の整理（現状）

- `_build_strong_adjacency` が **`link_store.list_all_links_for_player(player_id)` を毎回フルスキャン**する。
- ツール成功のたびに走るため、リンク数 \(L\) に対し **O(L)** が累積しやすい。
- クラスタ検出は強リンクのみの無向グラフの連結成分だが、**入力が毎回全域**である必要はない。

---

## 2. 目標

- **そのターンで更新されたリンク**および **触れたエピソードの近傍**からだけ候補部分グラフを構築し、昇格判定に十分な範囲に限定する。
- 振る舞い（昇格の条件: `MIN_CLUSTER_SIZE`, `MIN_RECALL_COUNT`, `MIN_EFFECTIVE_STRENGTH`）は **フルスキャン版と同一になるか**、差分がある場合は **テストと一文の仕様**で明示する。

---

## 3. 設計案

### 3.1 「フロンティア」集合

ターン中に以下を **ユニークな episode_id の集合**（プレイヤー単位）として蓄積する。

| ソース | いつ増えるか |
|--------|----------------|
| **リンクの作成・更新・強化** | `EpisodicMemoryLinkApplicationService`（またはリンクストアの write 経路）で、変更に関与した `episode_id_a` / `episode_id_b` |
| **受動想起** | `on_passive_recall_candidates` で候補になった `episode_id` |
| **能動探索ツール** | `memory_explore_related` で辿ったエピソード |
| **チャンク確定でエピソード put** | 新規または更新された `episode_id`（リンク処理と重複可） |

実装は **`PromotionFrontier`**（名前は任意）のようなミュータブルバッファでも、`link_store` に「dirty player_id を記録」でもよい。**単一ターンの境界でクリア**する（`on_after_tool_turn` の先頭でフロンティアを読み、処理後にクリア）。

### 3.2 部分グラフの取り方

フロンティア集合 \(F\) から:

1. 各 `episode_id ∈ F` について、`link_store` から **そのエピソードに接続するリンクだけ**を取得できる API が必要（現状は `list_all` のみなら **インデックス付きクエリを追加**: `list_links_incident(player_id, episode_id)`）。
2. 実効強度が閾値以上の辺だけで隣接表を **限局展開**。展開は **BFS で最大ホップ数 `K`**（例: 2〜3）または **辺数上限**で打ち切り。
3. 得られた部分グラフ上で既存の `_connected_components` とクラスタ条件チェックを流用。

### 3.3 フルスキャンとの一致

- **理想的には**: 部分グラフが「強リンクでつながったクラスタ全体」を常に含めば、フルスキャンと同じ昇格結果になる。
- **クラスタがフロンティアから遠い内部だけで閉じている**場合、当該ターンでは検出されない。**対策（いずれか）**:
  - **定期フルスキャン**: 例えば N ターンに 1 回、またはリンク総数が閾値以下のときのみ現行の全域スキャン。
  - **フロンティア拡張**: BFS の `K` を大きくする、または「前ターンの未処理クラスタ候補」をキューに残す。

最初の実装では **「フロンティア + インシデントリンク API + BFS 上限」** と **「稀なフルスキャン」** の併用が現実的。

### 3.4 パフォーマンス観測

- リンク更新経路に軽いカウンタ（本番はログレベルで可）: 部分グラフ構築で見たリンク数、昇格呼び出し時間。
- 任意: 簡易ベンチ（合成データで L を変化）。

---

## 4. 実装タスク（順序）

1. **`IMemoryLinkStore` 拡張**: `list_all_incident_links(player_id, episode_id, *, now)`（全インシデントリンク）。SQLite は既存 `(player_id, episode_id_a)` / `(player_id, episode_id_b)` インデックスでカバー。
2. **`EpisodicPromotionFrontier`**: リンクサービス・受動想起・能動 `memory_explore_related`（`note_promotion_frontier_episodes`）から蓄積。`on_after_tool_turn` 先頭で `drain`。
3. **`EpisodicSemanticClusterPromotionService`**: シードあり時は強リンクのみで最大 `expansion_hops`（既定 4）ホップ展開した頂点集合上で隣接表を構築。シード無し時は従来どおり `list_all_links_for_player`。`EPISODIC_PROMOTION_FORCE_FULL_SCAN=1` で常時全域。
4. **結合テスト**: `tests/application/llm/services/test_episodic_semantic_promotion_incremental.py`（三角グラフの一致・ホップ 0 で見逃し・空フロンティア時のフォールバック）。
5. **ドキュメント**: 本節および [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md) §0.1 を更新済み。

**差分の注意**: シードがグラフの一部にしか載らないターンでは、展開ホップ内にクラスタ全体が入らない場合に昇格が**そのターンは**検出されない（全域スキャンに比べ遅延しうる）。シード無し時のフォールバックと `EPISODIC_PROMOTION_EXPANSION_HOPS` の調整で緩和する。

---

## 5. ブランチ順序の推奨

- [episodic_memory_link_semantic_sqlite_plan.md](./episodic_memory_link_semantic_sqlite_plan.md) を **先にマージ**すると、`list_links_incident` の SQLite インデックスと一緒に設計できる。
- 増分昇格だけを先にマインメモリで実装し、SQLite は後からでもよいが、**インシデントクエリは両方のストア実装に必要**になるため、タスク分割時はポート追加のタイミングを揃える。

---

## 6. テストコマンド（合流条件の目安）

```bash
source venv/bin/activate
python -m pytest tests/application/llm/services/test_episodic_memory_link_and_promotion.py -q
python -m pytest tests/application/llm/test_episodic_reinterpretation.py -q
# 新增: tests/application/llm/services/test_episodic_semantic_promotion_incremental.py 等
```

---

## 7. 参照

- `src/ai_rpg_world/application/llm/services/episodic_semantic_cluster_promotion.py`（現行アルゴリズム）
- [episodic_memory_link_semantic_sqlite_plan.md](./episodic_memory_link_semantic_sqlite_plan.md)
