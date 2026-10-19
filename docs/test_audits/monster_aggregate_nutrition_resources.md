# モンスター集約の栄養・資源21宣言の監査

## 範囲と基準

基準は #1728 の `codex/test-audit-monster-core-behavior-20261014`、固定先端 `d444c7616f9f0b272bb21b32de396755051ad2b0`。元108台帳のID36〜48と64〜71、計21宣言だけを対象にした。行動・追跡の既監査32と状態効果3を維持する。兄弟 #1715 の固定先端 `6309e6aeab1e5f1274f0b347471a2a2cc46776d2` は別作業木で併用確認し、その4宣言の差分を本変更へ含めない。

判断はR14/F5/C2/D0。元入力を残し、停止条件の混同、製品定数に追従した期待値、空値だけの無操作、同じ増分しかない回復入力を修理する。削除件数を目標にはしない。

## 所有層

- 集約の生存判定・設定の受渡し・状態の代入・未配信通知生成は、この集約の公開入口で検査する
- `MonsterLifecycleState` と `MonsterHp` / `MonsterMp` は純粋な状態計算と値域を所有する。値オブジェクトの成功だけでは集約の更新漏れを検出できない
- `FeedMemory` は最大3件・古い順・同一対象更新の計算を所有する。集約の保存・死亡時の要求拒否・復活時初期化には別の失敗点がある
- `MonsterFedHandler`、`MonsterDeathHungerHandler`、`MonsterFeedQueryService`、`SpotMonsterBehaviorTickService`、`MonsterSkillExecutionDomainService` は呼出元の対象選択や実行連携を所有し、今回変更しない
- `get_events()` は集約内の未配信イベント列のコピーを返す。今回の通知検査は配信や観測の到達を証明しない

主な製品入口は `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py` の `tick_hunger` / `record_prey_kill` / `record_feed` / `remember_feed` / `heal_hp` / `recover_mp` / `use_mp` / `on_tick`。餌記憶はSQL保存の `memory_index` と再構成にも使われる。Being・エピソード記憶・SNSとは別の所有境界である。

`on_tick` は今回の製品ソース検索では集約外の直接呼出しを確認できなかった。しかし値渡しの公開契約と導入履歴があり、未使用という理由だけでは削除しない。試験専用の製品入口・準備コード・ファイルの削除はない。

## 全21宣言の判断

以下のテストはすべて `tests/domain/monster/aggregate/test_monster_aggregate.py::TestMonsterAggregate` 内にある。Fは契約を残した検査修理、Cは保持先へ元入力を移してからの統合。R42は未出現行の保持先になるため表へ変更し、他のR13は原文と構文木を維持した。

| 元ID | 判断 | 元の試験と保持先 | 守る契約・判断理由 |
| --- | --- | --- | --- |
| 36 | F | `TestTickHunger::test_tick_hunger_returns_false_when_disabled` | 既定の飢餓無効時はFalse・hunger0。既定行を保持し、starvation_ticks=0/増加率0.5とstarvation_ticks=2/増加率0の独立行を追加。両無効入力だけでは、片方の設定を読み違える回帰を見逃す |
| 37 | R | `TestTickHunger::test_tick_hunger_increases_hunger_and_returns_true_when_starving` | 0→0.5→1.0の保存と持続後True、公開starve後DEADを保持。値オブジェクトが正しくても集約の更新代入・返却が壊れる。STARVATION原因通知自体は別の既存starve所有試験に委ねる |
| 38 | F | `TestTickHunger::test_tick_hunger_returns_false_when_not_spawned` | 元の既定未出現行と、starvation_ticks=2/増加率0.5の有効設定未出現行を保持。Falseとhunger0を検査。元入力では、生存ガードを除去しても無効設定が飢餓更新を止めるため、ALIVE判定欠落を検出できない |
| 39 | R | `TestRecordPreyKill::test_record_prey_kill_reduces_hunger` | 獲物撃破0.3で飢餓0.8→0.5を集約に保存。値オブジェクトだけではrecord_prey_killの適用漏れを検出できない |
| 40 | R | `TestRecordPreyKill::test_record_prey_kill_when_dead_raises` | 出現後damage999で死亡した個体はrecord_prey_kill(0.2)を専用例外で拒否。死亡ガード削除なら例外が消える。全状態の原子性を新契約として追加しない |
| 41 | R | `TestRecordFeed::test_record_feed_success` | 採食0.3で飢餓0.8→0.5を集約に保存。record_feed独自の適用漏れは獲物撃破側の試験では検出できない |
| 42 | R | `TestRecordFeed::test_record_feed_when_dead_raises` | 死亡後の採食0.2はMonsterAlreadyDeadException。ID43の未出現入力を同じ拒否表へ移す。死亡と未出現は正HP/最終死亡時刻等が異なる公開入力なので両方維持 |
| 43 | C | `TestRecordFeed::test_record_feed_when_not_spawned_raises` → `TestRecordFeed::test_record_feed_when_dead_raises` | 未出現の採食0.2をID42の未出現行へ移し、同じ例外型を維持。同じ公開入口の同じ拒否契約を別の長いテンプレート準備で繰り返している |
| 44 | R | `TestRememberFeed::test_remember_feed_adds_entry` | 空の記憶へobject100/coordinate(1,2,0)を保存・公開。値オブジェクト成功だけでは集約の代入忘れを検出できない |
| 45 | F | `TestRememberFeed::test_remember_feed_lru_evicts_oldest` | 元の4入力100..103/(0,0)..(3,3)を維持。公開契約の最大3件と古い順101,102,103を座標込みの独立な列で検査。製品定数の追従で最大数変更を見逃し、所属だけでは完全な順序と座標を守れない |
| 46 | R | `TestRememberFeed::test_remember_feed_same_object_id_moves_to_end` | 同一object100を更新すると101→100へ移り新座標(1,1,0)を公開。削除重複・新座標・末尾順の独立な公開接続を保持する |
| 47 | F | `TestRememberFeed::test_remember_feed_when_dead_does_nothing` | 元の空記憶死亡行を保持し、生存中に1件覚えてから死亡した行も追加。要求直前の具体的な記憶と要求後の記憶を比較。死亡個体へのremember_feed要求で既存記憶を消す実装でも空入力だけでは通る。状態全体や未配信通知の原子性は追加しない |
| 48 | R | `TestRememberFeed::test_behavior_last_known_feed_cleared_on_spawn` | 生存中に1件記憶し死亡→待機時間後の復活で空へ戻る。FeedMemory.clearedが正しくても復活の接続漏れを検出する |
| 64 | R | `TestRecoveryAndRegeneration::test_heal_hp_success` | HP50へ30回復してHP80、未配信MonsterHealedEvent1件のamount30/current_hp80。状態だけでも通知型だけでも代替できない集約公開契約 |
| 65 | R | `TestRecoveryAndRegeneration::test_recover_mp_success` | MP10へ20回復してMP30、未配信MonsterMpRecoveredEvent1件のamount20/current_mp30。HP回復と別の資源更新・通知を保護する |
| 66 | F | `TestRecoveryAndRegeneration::test_on_tick_regeneration` | 元のHP50/MP10・入力最大100/50・率0.01で51/11を維持。値渡し最大300/700・率0.01で53/17を追加し、ID67のHP50/MP50・率0.1→60/50を受け入れる。通知の件数・型・実増分・現在値・識別子を検査。元は渡した値と基礎値が同じ、HP/MPとも増分1。値無視・軸の取り違え・通知重複を見逃す。期待値は固定値であり同じ計算関数から作らない |
| 67 | C | `TestRecoveryAndRegeneration::test_on_tick_custom_regen_rate` → `TestRecoveryAndRegeneration::test_on_tick_regeneration` | 元のHP50/MP満タン50・入力最大100/50・率0.1→HP60をID66へそのまま移す。率違いの同じ公開回復入口と準備を共有できる。MPを40消費する別入力へ勝手に変更しない |
| 68 | R | `TestRecoveryAndRegeneration::test_on_tick_no_regen_when_rate_none` | 明示的regen_rate=NoneでHP50/MP10と回復通知なし。率を既定1%へ戻す回帰を検出する。省略引数まで証明したとは言わない |
| 69 | R | `TestMpUsage::test_use_mp_success` | use_mp20でMP50→30を集約に保存。短いが公開APIの正常消費と値オブジェクトの更新接続を守る |
| 70 | R | `TestMpUsage::test_use_mp_insufficient_raises_error` | ALIVE/MP50のuse_mp60はMonsterInsufficientMpException。入力が別ガードに阻まれておらず、不足判定破損・例外伝播消失を検出。全状態比較は追加しない |
| 71 | R | `TestMpUsage::test_use_mp_not_alive_raises_error` | 未出現DEAD/正HP100/MP50のuse_mp1はMonsterAlreadyDeadException。HPだけの判定への置換も検出できる既存の有効な拒否入力。全状態比較は不要 |

## 元入力と追加行

| 保持先 | 元から保持する入力 | 追加する入力・独立な期待値 |
| --- | --- | --- |
| F36 飢餓無効 | 既定の持続時間0・増加率0、出現後tick1でFalse/hunger0 | 持続時間0・増加率0.5、持続時間2・増加率0の各行でもFalse/hunger0 |
| F38 未出現 | 既定設定の未出現、tick1でFalse | 持続時間2・増加率0.5の未出現でもFalse/hunger0。生存ガード欠落を無効設定が隠す問題を区別する |
| R42/C43 採食拒否 | 持続時間10・採食設定0.3、出現後damage999/tick10で死亡して採食0.2を拒否 | 同じ表へ元の未出現・採食0.2拒否を移す。両行とも専用例外型を維持 |
| F45 餌記憶容量 | 100〜103の4対象、座標(0,0)〜(3,3) | 期待列は101/(1,1)、102/(2,2)、103/(3,3)の3件。最大数定数から期待値を生成しない |
| F47 死亡後の記憶要求 | 出現→damage999/tick10→餌100/(1,0)を要求し、空記憶のまま | 生存中に99/(4,5)を記憶する行を追加。死亡後・要求直前に具体的な記憶を確認し、要求がそれを消去しないことを検査 |

自然回復はHP最大100/MP最大50の個体を使い、HP50へダメージを与える。MP消費・入力最大値・回復率は下のとおり。結果は固定値で書き、製品の計算関数から作らない。

| 行 | 消費MP | 入力最大HP/MP | 率 | 結果HP/MP | 通知の実回復量HP/MP |
| --- | --- | --- | --- | --- | --- |
| 元F66の1%・最小1 | 40 | 100/50 | 0.01 | 51/11 | 1/1 |
| 元C67の任意率 | 0 | 100/50 | 0.1 | 60/50 | 10/0、MP通知なし |
| 値渡し区別用の追加行 | 40 | 300/700 | 0.01 | 53/17 | 3/7 |

通知は型ごとの件数・実増分・現在値・集約識別子を検査する。HP/MP通知の並び順は新たな契約にしない。明示的な `regen_rate=None` の元試験もそのまま残す。省略引数の検査まで済んだとは主張しない。

C2は移管元を原文のまま残す段階で28行を成功させ、その後に旧宣言を除去して26行を確認した。拒否時の全状態や通知列の原子性は追加しない。短いMP正常消費・専用例外の試験は独立した公開契約として保持する。

## 履歴

- [220bc4b](https://github.com/Motifman/llm-rpg/commit/220bc4bd2fe2b06b45c2be1134ede7782474cec3): 飢餓の所有をComponentからMonster集約へ移した
- [3a4c8cb](https://github.com/Motifman/llm-rpg/commit/3a4c8cb404cc3568d9ca447bae98418659748e92): 採食の成功・死亡・未出現拒否を追加した
- [4110953](https://github.com/Motifman/llm-rpg/commit/4110953abd040ab4b52ffce60ef1138a96e7410e): 最大3件・古い順の餌記憶を導入した
- [67392cb](https://github.com/Motifman/llm-rpg/commit/67392cb89a7117a55a9859ad1aaa89e64f8b4a7f): 餌記憶の計算をFeedMemoryへ委譲した
- [b5ae027](https://github.com/Motifman/llm-rpg/commit/b5ae027e80d2c02fe851f1e7739ee21bd18aa0e8): 生命状態をMonsterLifecycleStateへ分離した
- [452aae9](https://github.com/Motifman/llm-rpg/commit/452aae918104b0b1041e0b280fd8410831eebf6d): 回復・MP消費の公開契約を導入した
- [40ef94a](https://github.com/Motifman/llm-rpg/commit/40ef94a05c43a805b054e26445e50b31593262c8): 自然回復率を設定サービスから値渡しへ変更した

## 検証

未編集の対象21＋関連15=36行、移管元を残した28行、除去後26行が成功した。関連15は餌記憶・生命値・採食/獲物撃破ハンドラ・餌検索・技能サービスの所有境界である。固定兄弟#1715と先行の状態効果を合わせた7宣言11行も基準で成功した。

変異は22組44実行。改善12組は旧21行成功から候補26行の予定した確認式で失敗し、保持8組は旧新双方の元契約の確認式または例外拒否で失敗した。意味保持2組は旧新双方で成功した。準備・収集エラーとスキップは0。複数行で失敗する変異も失敗位置を照合した。

| 種別 | 変異 | 実際の失敗点 |
| --- | --- | --- |
| 改善 | 飢餓死停止中も飢餓だけ進める／増加率0を既定率に置き換える | 片方だけ無効な各行のhunger0 |
| 改善 | 未出現の生存ガードを除く | 有効設定の未出現行のhunger0 |
| 改善 | 記憶容量3→4／識別子降順へ並べ替え／追放時に座標を最新のものへ上書き | 3件の具体的な記憶列 |
| 改善 | 死亡後のremember_feed要求で既存記憶を消す | 要求直前の記憶との一致 |
| 改善 | 渡された最大値を無視／MPにHP最大値を使用 | HP53／MP17 |
| 改善 | 自然回復通知を二重追加 | 未配信通知の総件数 |
| 改善 | HP／MP回復通知の集約識別子を取り違える | MonsterIdと世界オブジェクトIDの区別 |
| 保持 | 採食死亡ガードを除く／未出現だけ通す | 移管先の死亡・未出現両行の専用例外 |
| 保持 | 回復率を1%へ固定／MP最小1を除く | 元の任意率行HP60／元の1%行MP11 |
| 保持 | 死亡後の記憶要求を受け入れる／最新の記憶を追い出す／復活時の記憶クリアを除く | 元の空記憶・先頭追放・復活初期化 |
| 保持 | MP消費結果の集約への保存を外す | 元のMP50→30。関連する4〜5行でも失敗するが、この元確認式を主証拠とする |
| 意味保持 | 局所変数の改名／同等な一覧コピーへの書換え | 旧21・新26とも成功 |

追加の記憶順・座標変異後も製品を復元し、集約全体116行＋関連15行の計131行が成功した。兄弟#1715の元差分は最終候補へ無衝突で適用でき、併用11行も成功した。主作業木・原本・併用作業木の製品1601Pythonファイルは基準ハッシュと一致する。

対象外の現行79宣言と共有fixtureは原文・構文木を維持し、その中に含まれる既監査の元行動32を受け持つ24宣言も一致した。試験は2084→2100行（+99/-83）、製品・共有準備・支援コードの変更は0行。Ruff0.16.8と `git diff --check` は成功した。

ローカル検証はPython3.10.22/pytest8.4.1、安全実行器、各回専用キャッシュで直列実行した。全リポジトリ試験はローカルでは実施していない。CIは既存の全PR経路で、Python3.10・固定依存・pytest -n autoと別ジョブの静的検査を実行する。公開する正確な先端のCIは公開後に確認する。

## 完了範囲

今回の完了対象は元21のみ。元108のうち既監査39と合わせて60となり、元48宣言は引き続き未完として別の所有境界で調査する。製品修理・課題票作成・マージは含めない。
