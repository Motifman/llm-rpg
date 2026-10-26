# モンスター個体の旧座標と世界物体IDの削除 (#1893)

基準: 5fa0abd4ec541c906ae1ca7a3ec690b97ed7e183。

## テストリスト

- [x] 集約・配置定義・配置サービスから旧座標と世界物体IDが消える。
- [x] 旧SQLite行の読込・更新と複数個体の新規保存が成功し、旧必須列の値が衝突しない。
- [x] 保存失敗のrollback後も再保存できる。
- [x] スポット上の配置・出退場・被弾・CHASE・逃走・群れ・生存・装備を維持する。
- [x] 旧世界snapshotを読み込め、モンスター個体のcodecが無い既存の制限を変えない。
- [x] smoke_stubと山村・避難訓練のseed 0〜2・40tickの前後で全記録種別・観測種別・行動件数が一致する。

## 削除前の調査

個体の座標と世界物体IDはruntimeの静的配置・条件付き配置から渡され、保存層と旧タイルの専用操作が読む。現行の配置と追跡はMonsterId、SpotId、AttackerRefを使う。旧IDによる検索の唯一の使い手npc_nameにも本番呼出はない。update_map_placement、record_evasion、transition_to_passive_stateは本番呼出がない。捕食・モンスター間攻撃は旧IDを被弾/死亡イベントにも渡すが、本番の配信先・文面・戦闘規則には使わない（D1893-2）。

## 質感

現在の移動・戦闘・通知の表現を改善する変更ではない。スタブで観測と行動の前後一致を確認し、質感の改善は主張しない。

## 振る舞いの比較

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| 静的・条件付き配置 | スポットに加え仮座標・世界物体IDを渡す | MonsterIdとスポットで同じ個体を配置する |
| 被弾・捕食・反撃・追跡 | 相手をAttackerRefとMonsterIdで扱う | 同じ相手・HP・状態・観測を維持する |
| 古いSQLiteを読む | 個体の旧座標・IDも復元する | 旧列をドメインへ戻さず、現役の状態を復元する |
| SQLiteを更新・新規保存する | 個体から旧列の値を渡す | 既存の旧列は保持し、新規行の必須IDだけ保存層で補う |
| 世界snapshotを読む | モンスター個体はシナリオから初期配置する | 同じ。個体のcodecが無い既存の制限を維持する |

## 確認結果

専用venvと固定PYTHONPATHを使い、dotenv.load_dotenvを無効化した。実LLM・.env読込・手動quality/live_apiは実行していない。出力は `/tmp/llm-rpg-1893-a2/`。

- 構造検査のRed→Greenを確認。モンスター・配置・保存397件、保存互換13件、シナリオ・構造19件、モンスター動作・観測・シナリオ読込等1,967件が成功。範囲は重複する。
- 基準mainのコードで生成した実SQLiteの2個体を新コードで復元・HP更新・再保存でき、旧IDを保持した。
- 基準mainのworld.jsonから実験再開が成功。snapshot_loadとworld_snapshot_loadに成功を確認し、今回の削除に伴う世界キーの読み捨ては無い。
- smoke_stubは前後成功。profile、シナリオhash、2tick、基準commitを確認した。観測/行動0件なので起動・保存配線の確認に限定する。
- 山村・避難訓練の各3seed・40tickは前後とも検出0件。全記録種別・観測種別・行動件数が一致し、合計1,990観測・1,205行動。詳細はcomparison.json。
- 変更Pythonのruff check/format、mypy（1,242ファイル）、空白検査が成功。
- ASTで現役の被弾・CHASE・逃走・生存・成長操作22件の本体が同一と確認した。全シナリオにinitial_placements[].coordinateの指定は無い。

## 残す検索一致と試験

src/testsの旧API・イベントへのimport、実行時呼出、再公開は0件。旧表の列名、互換試験、不在検査の文字列は残す。Coordinate/WorldObjectId型と別用途の状態はD1893-2記載のとおり残す。

過去の記録として `docs/domain_events_observation_spec.md`、`docs/refactoring/observation-formatter-refactoring-plan.md`、`docs/pursuit/phase1_integration_strategy.md`、`docs/quality_checks/tile_map_observation_removal.md`、`docs/test_audits/monster_evasion_bridge_contracts.md`、D1862-11を保持する。当時の維持判断はD1893-2で更新する。共有CLAUDE.md/world_architecture.mdは親の文書PRが所有する。

回避・旧ID検索・地図移動の専用試験は削除した。出現/再出現の生存・群れ・成長試験は座標前提だけを外した。観測の場所検索はMonsterHealedEvent、汎用transactionのrollbackはnext_monster_idを使う形で保証を残した。
