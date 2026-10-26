# スキル定義の旧当たり判定を削除する検証

Issue #1893 担当B。比較元は `f86d9fcde0ba4ada9d1e3124c13452dfa3b3aae2`。
専用worktree `/Users/kei-minagawa/.codex/worktrees/0f7a/llm-rpg` と専用 `.venv` を使う。

## テストリスト

- [x] 旧形・速度・効果・命中の型、enum、専用例外、再公開が存在しない（Red → Green）。
- [x] SkillSpecは当たり判定のフィールドを持たず、消費・前提スキル・特効・射程を保持する。
- [x] 新規SQLiteへの定義と装備の保存・復元が通る。
- [x] 旧SQLiteの形・速度・効果を含む定義から、現役の値と装備を復元できる。
- [x] 旧定義の置換・削除で旧子行を残さず、共有トランザクションの制約を維持する。
- [x] 現行スキルの装備・デッキ・進行・消費、モンスター生成・戦闘の既存試験を維持する。
- [x] 変更前のsnapshotを変更後に読み、既存の復元・fail-fastを維持する。
- [x] smoke_stubと2シナリオ×seed 0–2×40tickのfuzzを前後比較する。
- [x] 変更Pythonのruff、mypy、空白検査。
- [x] 独立レビュー。CI全7項目はPRのChecksとIssue #1893の完了コメントに結果を残す。

## 削除前の参照調査

`src/**/*.py` をASTで解析し、import・Name・Attribute・文字列を検索した。
旧型への参照は定義、再公開、SkillSpec、SQLiteのcodecに限られた。
`SkillSpec.hit_pattern` / `hit_effects` の値を読むのはSQLite writerだけ。
`rg`でもsrc/tests/scripts/docsとpyprojectを確認する。
モンスター生成はworld_runtimeが空のSkillLoadoutAggregateを作っており、SkillSpecを作っていない。
そのためworld_runtimeは変更不要。装備と状態異常、モンスターの座標・追跡は維持する。

SQLiteの `game_skill_specs.pattern_type` はNOT NULLでdefaultなし。
既存migrationと子表は変更せず、保存層でのみ必須列を満たす。
Being/world snapshotには今回削除する型・フィールド・保存キーがなく、codecの削除や読み捨て件数の追加は不要。
変更前smokeで保存した実際のsnapshotを変更後に読み込んで確認する。

## 検証結果

不在保証3件とSQLiteの新しい契約4件が変更前に失敗することを確認し、変更後に成功した。
旧型だけを検証していた3ファイルを退役した。現行SkillSpecを使う試験は旧引数だけを外して残した。
以前の不在保証 `test_unused_combat_exceptions_removed.py` は、対象モジュール自体が消えても同じ3例外の不在を検査できる形にした。

手元の関連試験322件が成功した。スキル・状態異常・SQLite定義/装備/モンスター・migration・本番モンスター生成/戦闘・snapshot復元とfail-fastを対象とし、並列数は4。
`uv run --no-sync mypy` は1,256ファイルで成功。触ったPythonだけruffを適用し、空白検査を行った。

### 前後の実験

`/tmp/llm-rpg-1893-b/{before,after}` に結果を保存した。`PYTHONPATH` の先頭に一時的な `sitecustomize.py` を置き、`dotenv.load_dotenv` と `dotenv.main.load_dotenv` を常にFalseを返す関数へ差し替えた。次に専用worktreeのsrcを指定し、専用 `.venv` の `uv run --no-sync` を使用した。実LLM・`.env`は使用していない。

- `make experiment EXPERIMENT_PROFILE=smoke_stub OUT=...` は前後とも成功。resolved設定は同じprofile・scenario・2tick・seed 42・stubを示した。全13記録種別/98件が一致した。smokeは行動・観測とも0件なので、振る舞い比較は以下のfuzzで補った。
- `make fuzz-scenario SCENARIO=data/scenarios/<scenario>.json SEEDS=0-2 FUZZ_TICKS=40` は前後とも全条件成功、findingsなし。
- 同じ `run_random_agents` をNullTraceRecorderの一時的な記録フック付きで再実行し、`kind` と `observation.payload.structured.type` ごとのCounter、`actions` 件数を比較した。各Counterの全キー・全値が一致した（合計だけの比較ではない）。

| scenario | seed | 行動件数 | 観測件数/種類 | 全記録件数/種類 |
|---|---:|---:|---:|---:|
| mine_village_v1 | 0 | 142 | 92 / 11 | 4,065 / 22 |
| mine_village_v1 | 1 | 139 | 127 / 14 | 4,055 / 22 |
| mine_village_v1 | 2 | 145 | 84 / 15 | 4,068 / 22 |
| station_drill | 0 | 301 | 531 / 17 | 3,512 / 25 |
| station_drill | 1 | 199 | 497 / 14 | 2,585 / 24 |
| station_drill | 2 | 279 | 659 / 19 | 3,436 / 25 |

変更前smokeの `snapshots/` を `SNAPSHOT_LOAD_DIR` に渡して変更後の `make experiment` を実行し、4 Beingとworldの31 subsystemを復元した。`snapshot_load.restored_count=4`、`removed_memory_keys=[]`、`world_snapshot_load.world_tick=2`を確認した。今回の削除対象にsnapshotキーがないため、件数を捏造せず既存のtraceを維持する。現在のキー欠落や不正値を拒否する既存試験も残している。

### grepの例外

削除型の識別子・専用モジュール名はsrcから消えた。AST不在保証はimport、宣言、参照、再公開、動的import用文字列を検査し、pyprojectの旧指定も検査する。
`rg`の対象はsrc/tests/scripts/docs/pyproject、検索語は `HitBoxShape|RelativeCoordinate|HitBoxVelocity|HitEffect|SkillHitPattern|SkillHitTimelineSegment|hit_pattern|hit_effects|SkillRotationAngleUnsupportedException|combat_exceptions`。
残るヒットを次に分類した。本番の旧型の読者や呼出は残っていない。

| 残る場所 | 理由 |
|---|---|
| `game_write_sqlite_schema.py`、`test_sqlite_migration.py` | 変更しない過去migrationとその保証 |
| `sqlite_skill_spec_repository.py` | 旧子表のDELETEのみ。旧値の読込・生成はない |
| `test_sqlite_skill_repositories.py` | 旧DBのSQL fixtureと互換試験 |
| 新しい構造試験、既存の未使用例外不在試験 | 削除対象を再導入させないための文字列 |
| `D1862-9.md`、`D1862-13.md`、`D1862-23.md` | 当時の保持判断。#1893が削除を上書きしたが履歴は残す |
| `tile_hit_box_removal.md`、`tile_map_harvest_skill_removal.md`、`unused_combat_exceptions_cleanup.md` | 過去PRの検証記録 |
| `docs/test_audits/combat_calculation_contracts.md`、`hitbox_lifetime_contracts.md` | 過去のテスト監査記録 |
| 本文と `D1893-3.md` | 今回の削除対象と保存互換の説明 |

質感については、同じseedの観測・記録・行動件数が一致し、変更を認めなかった。実LLMによる主観的な質感比較はこの削除PRでは行わない。

## PR作成前の独立レビュー

code-reviewerはApprove。CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0で、指摘対応・不採用ともになし。保存互換・削除範囲・再公開と動的参照・試験と本文の整合性を確認し、別途関連97件を実行して成功した。レビュー時点の残ブロッキングはCI全7項目の結果確認のみ。
