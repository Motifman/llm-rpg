# MemoryLink / セマンティック記憶の SQLite 永続化 — 実装計画

この文書は [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md) §0.1 の「次工程」と [memory_feature_workflow.md](./memory_feature_workflow.md) に従い、**インメモリのみ**の `IMemoryLinkStore` / `ISemanticMemoryStore` を **プロセス外でも再利用できる形で永続化する**ための実装手順を定める。

**推奨ブランチ名の例**: `feature/episodic-memory-link-semantic-sqlite`

**前提**: PR（リンク・昇格・配線）マージ済みの `main`。エピソード本体は既に `SUBJECTIVE_EPISODE_DB_PATH` で SQLite に載せられる。

---

## 1. 目的と完了条件

### 1.1 目的

- 再起動後も **連想グラフ（リンク）** と **昇格済みセマンティック記憶** が失われない。
- エピソード SQLite と **同一ファイルに同居させるか／別ファイルにするか**を明示し、運用で誤接続しない。

### 1.2 完了条件

- `IMemoryLinkStore` の SQLite 実装があり、`MemoryLink` の roundtrip とプレイヤー境界がテストで検証される。
- `ISemanticMemoryStore` の SQLite 実装があり、`SemanticMemoryEntry` の roundtripと `register_cluster_signature_if_new` の競合がテストで検証される。
- `create_llm_agent_wiring` / `create_spot_graph_wiring` が環境変数または明示ファクトリで **インメモリではなく SQLite** を選べる（既定は現状維持でもよいが、本番推奨パスはドキュメント化する）。
- `.env.example` に新規変数が載り、単一 DB にまとめる場合は **マイグレーション／バージョン**の方針が一文ある。

---

## 2. 設計方針

### 2.1 DB の境界

| 方針 | メリット | デメリット |
|------|----------|------------|
| **A. エピソード DB と同一 SQLite ファイル**（推奨をデフォルト検討） | バックアップ・デプロイが 1 ファイル、トランザクションで整合しやすい | マイグレーションを共用する必要がある |
| **B. 別ファイル**（例: `MEMORY_GRAPH_DB_PATH`） | エピソードと独立にクリア可能 | 運用で「片方だけリストア」による不整合リスク |

**推奨**: まず **A**。既存の主観エピソード SQLite に **リンクテーブル・セマンティックテーブル**を追加する形が、運用負荷が低い。

### 2.2 スキーマ（案）

実際の列は契約（`MemoryLink`, `SemanticMemoryEntry`）に合わせて確定する。

- **memory_links**: `player_id`, `episode_id_a`, `episode_id_b`, `link_type`, `strength`, `created_at`, `last_reinforced_at`, …（既存値オブジェクトのフィールドに一致）
- **semantic_entries**: `entry_id`, `player_id`, `text`, `evidence_episode_ids`（JSON または関連テーブル）, `confidence`, `created_at`
- **schema_meta**: `version INTEGER`（既存 episodic DB に無ければ追加）

既存 `SqliteSubjectiveEpisodeStore` と **同一接続**でマイグレーションするか、`SqliteEpisodicBundleStore` のような薄いファサードで episode + link + semantic をまとめるかは実装時に決める。

### 2.3 ドメイン境界

- **ポート**はドメイン／アプリケーション契約のまま。**実装はインフラ層**（`infrastructure/repository/`）。
- リポジトリがドメインサービスを呼ばない（DDD ルールどおり）。

---

## 3. 実装タスク（順序）

1. **契約の確認**: `IMemoryLinkStore` / `ISemanticMemoryStore` の必須メソッド一覧と、`InMemory*` との振る舞い差（なければよい）。
2. **スキーマ定義とマイグレーション v1**: CREATE TABLE、インデックス（`player_id`、エンデポイント列）。
3. **`SqliteMemoryLinkStore`**: `list_all_links_for_player`, `upsert`, 減衰・強化で更新する列の整合。
4. **`SqliteSemanticMemoryStore`**: `add`, `register_cluster_signature_if_new` の一意制約（`player_id` + signature ハッシュ等）。
5. **ワイヤリング**: `build_episodic_memory_link_bundle` または `create_llm_agent_wiring` 内で、環境変数により SQLite 実装を注入。
6. **結合テスト**: メモリ実装と SQLite 実装で同一シナリオを走らせ、件数・内容が一致すること。
7. **ドキュメント**: `episodic_memory_implementation_plan.md` §0.1 の該当行を「完了」に更新。

---

## 4. テストコマンド（合流条件の目安）

```bash
source venv/bin/activate
python -m pytest tests/infrastructure/repository/test_sqlite_* -q  # 既存に追加
python -m pytest tests/application/llm/wiring/test_episodic_memory_wiring_integration.py -q
python -m pytest tests/application/llm/services/test_episodic_memory_link_and_promotion.py -q
```

---

## 5. 依存と順序

- **先行**: なし（`main` にリンク／昇格のマージ後に着手）。
- **後続**: [episodic_semantic_promotion_incremental_plan.md](./episodic_semantic_promotion_incremental_plan.md) は、SQLite 化と同一ブランチに含めない。**永続化 PR を先にマージ**し、昇格のイベント駆動は別ブランチがコンフリクトしにくい。

---

## 6. 参照

- [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- [memory_feature_workflow.md](./memory_feature_workflow.md)
