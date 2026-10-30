# 未使用の小さな型と旧天候イベントの削除検証

Issue #1893、担当C。基準は `f86d9fcde0ba4ada9d1e3124c13452dfa3b3aae2`、専用worktreeの `codex/1893-unused-types-weather` と比較した。判断は [D1893-4](../design_decisions/D1893-4.md)。共有の構成説明は後続の文書PRで更新する。

## テストリストと結果

- [x] 旧型・旧天候モジュール・専用formatterの不在保証5件。変更前は5件失敗、変更後は5件成功。
- [x] 観測関連と不在保証862件成功。注意レベルの環境入力は現行の昼夜イベントへ、配信先取得の例外は現行の移動イベントへ替えて保証を維持。
- [x] 現行天候、所持金、シナリオ属性、SQLite/snapshotなどの関連218件成功（上記と合わせて1,080件）。
- [x] 現行天候の屋内/屋外×通知有効/無効4件は、基準commitの独立展開と変更後の両方で成功。天候stageの更新から、確定後の観測文・構造化値・バッファ・trace・手番予約まで確認。
- [x] 触ったPythonのみruff check/format、`uv run mypy`（1,259ファイル）、`git diff --check`。
- [x] smoke_stubと山村・避難訓練の各seed 0〜2、40tickを変更前後に実行。例外・検出事項0件。

手元のpytestは関連範囲だけで並列4以下。全体はCIで確認する。実LLM、`.env`、手動quality/live_api試験は使っていない。

## 本番参照と保存の点検

変更前にsrc/tests/scriptsのASTを走査し、import（型注釈用も含む）、識別子、属性、定義、文字列を調べ、`rg`も併用した。

| 削除対象 | 変更前の読者・生成元 | 維持する本番経路 |
| --- | --- | --- |
| common側 `Gold` | 定義内の演算だけ。外部からのimport・呼出・再公開なし | player側 `Gold`。所持金イベント・取引・SQLite・snapshotはこの型を使う |
| `PlayerState` | enum定義だけ。外部参照なし | シナリオ属性の `state`、`PlayerStateDictSubsystemCodec` |
| `SpotWeatherChangedEvent` | 観測registry、default配信規則、専用formatterが読むが、本番の生成・発火なし。生成するのは人工試験だけ | `SpotGraphEnvironmentStageService.run` → `SpotGraphWeatherChangedEvent` → 確定後の `_append_weather_observation` → `_emit_observation_directly` |

`WorldObservationFormatter`は旧イベントだけを処理していたので、定義と構築・再公開も削除した。`SpotGraphRecipientStrategy`、現行の天候イベント、world_runtime、追跡の登録行は変更していない。動的参照に使う旧名の文字列もsrcに残っていない。

保存の読者は `sqlite_player_state_codec.py` と `player_vitals_codec.py` が現行 `Gold`、`player_state_dict_codec.py` が辞書、`weather_codec.py` が現行 `WeatherState`。SQLiteの `gold_value INTEGER NOT NULL`、天候列などの必須制約を確認し、書込側も維持した。削除する型の保存キーはないため、古いsnapshotを捨てる処理や `snapshot_load` の削除件数追加は不要。

既存の `test_world_subsystems_phase9_4b.py` でschema v1の天候snapshot読込、v2の乱数位置復元と欠落拒否を確認した。`test_world_subsystems.py` と `test_world_subsystems_phase9_2b.py` は所持金・属性の往復、SQLiteのplayer state/JSON codec/weather zone試験は読込と新規保存を確認する。保存キーの改名やfail-fastの緩和はない。

## 前後の振る舞い

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| 天候通知あり、屋内/屋外にいる | 全員に「外の天候が変わった: RAIN（強度 0.5）」が届き、traceと手番予約に残る | 同じ。実際の発火経路の試験を追加 |
| 天候通知なし | 天候は更新されるが観測・予約なし | 同じ |
| 旧天候イベントを人工的に作る | 専用登録・屋内抑制・旧文面が動く | 型と専用経路を削除 |
| 所持金・シナリオ属性・天候の保存と再開 | 現行型・辞書を保存して復元する | 同じ |

## 同じ条件のrun比較

各worktree専用の `.venv` を使い、`PYTHONPATH`でソースを固定した。一時ディレクトリの `sitecustomize.py` で `dotenv.load_dotenv` と `dotenv.main.load_dotenv` を無効化してから実行した。

```text
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-1893-c/<before|after>-smoke
make fuzz-scenario SCENARIO=data/scenarios/mine_village_v1.json SEEDS=0-2 FUZZ_TICKS=40
make fuzz-scenario SCENARIO=data/scenarios/station_drill.json SEEDS=0-2 FUZZ_TICKS=40
```

smokeのresolved configでprofile、scenario hash、2tick、stub provider、基準commitと変更後の差分を確認。両方TIMEOUTで正常終了し、全記録種別別件数が一致した。smokeでは観測は0件なので、天候の配信保証は上記の現行経路の4件で補った。

fuzzのtraceは同じ `run_random_agents` を `NullTraceRecorder.record` の採取だけ追加して再実行し、全記録種別・観測種別ごとの件数を比較した。全6試行で一致し、観測1,990件・行動1,205件。結果は実LLMでの質感評価には一般化しない。

## 残る文字列と退役する試験

- src/scriptsの旧型・旧モジュール参照は0件。testsでは専用不在保証と `test_tile_events_are_not_observed.py` の不在期待値だけ。
- `Gold` の名前自体は現行型が使うので全消ししない。`PlayerStateDictSubsystemCodec` なども今回のenumとは別物。
- 履歴として残す文書: `domain_events_observation_spec.md`、`observation_implementation_plans.md`、`refactoring/observation-formatter-refactoring-plan.md`、`ground_item_pickup_implementation_plan.md`、`quality_checks/tile_map_observation_removal.md`、`design_decisions/D1862-15.md`。
- `docs/game/world_architecture.md` の「旧天候イベントを維持」は調整役の最終文書PRで更新する。今回のD1893-4と本書を引き継ぎ先とする。
- 専用試験 `test_world_formatter.py`、`test_indoor_weather_observation.py` と旧イベントのformat/recipient例2件は削除。現行の注意レベル・配信先例外の試験は保持。迷ったまま退役させた試験はない。

生データとログは `/tmp/llm-rpg-1893-c/`（`ast-before.json`、`red.log`、`green.log`、`comparison.json`、各runとpytestログ）。PR作成前に独立レビューを受け、結果はPR本文へ記録する。
