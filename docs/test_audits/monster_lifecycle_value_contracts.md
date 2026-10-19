# モンスターの生命状態と資源値の試験監査

## なぜ

再出現と採食の試験は、飢餓時間が最初から0の状態に対して結果も0だと確かめていました。
古い飢餓時間をそのまま残す誤りでも通ります。また、変更操作が別の実体を返すだけでは、
元の状態を同時に書き換える誤りや、結果から生存状態を失う誤りを検出できませんでした。

## 範囲と判断

固定基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f` です。

| 対象 | 元の宣言 | 保持 R | 補強 F | 統合 C | 削除 D |
|---|---:|---:|---:|---:|---:|
| `test_monster_hp.py` | 9 | 9 | 0 | 0 | 0 |
| `test_monster_mp.py` | 5 | 5 | 0 | 0 | 0 |
| `test_monster_lifecycle_state.py` | 35 | 32 | 3 | 0 | 0 |
| 合計 | 49 | 46 | 3 | 0 | 0 |

宣言数は49のままです。不変性の1宣言にあった7操作を独立した表の行に分け、
実行件数は49から55へ変わります。試験を速くする変更ではありません。
製品コード、HP/MPの試験、集約と行動の試験は変更していません。

## 補強した3契約

1. 再出現では、MP消費と公開の飢餓進行で正の飢餓時間を作ってから死亡させます。
   操作前の状態を固定した期待値で確認し、従来の120 HP・60 MP・時刻150・飢餓0.2を
   保持して、現在値と最大値、タイマー0、旧状態が変わらないことを検査します。
2. 採食では、この試験だけで飢餓時間1へ到達させます。飢餓0.8から0.3減らして0.5に
   する元の操作を残し、古い時間1が新しい状態では0へ戻ることを確かめます。
   丸めと0・負量を扱う隣接試験の準備は変えません。
3. 不変性では、被害1、回復0、MP回復0、MP消費0、死亡時刻1、飢餓減少0.1、
   飢餓進行 `(0.1, 1.0, 5)` の7入力を残します。各行で別実体であること、操作後の
   全公開値、元の全公開値を固定した期待値で検査します。値を取り出す補助は計算しません。

この表が示すのは、HP100・MP50・生存・時刻0・飢餓0・飢餓時間0の初期状態に対する
7操作の検査です。任意の生死・時刻・資源値の組合せや、全種類の不変性を網羅するとは
主張しません。再出現と採食の正の飢餓時間は、それぞれの専用試験が所有します。

## 保持する責務

- HP/MPの値、上下限、負量拒否、MP不足、HPの1/0境界は直接の値オブジェクトが所有します
- 生命状態は、生成時の生死と時刻、飢餓の境界、操作後の新旧状態を所有します
- 通知、死亡処理、配置、出現の条件は集約が所有します。別担当の試験を移管しません
- プレイヤーのMPは不足分を0へ丸めますが、モンスターのMPは不足を拒否します。
  似ている実装という理由で同じ検査へ統合しません
- 直接構築での不正値拒否と、生成メソッドによる丸めは別の契約です
- `get_percentage` は利用者数だけで削除せず、50/100と0/0の公開値契約を残します
- 対象にhashの断言はありません。異なる値に異なるhashを強制する制約を追加しません

## 失敗を検出する証拠

製品を一時的に変える対照を、旧試験と新試験で各1回実施しました。
各実行に未使用のバイトコード保存先を割り当て、終了後に製品を全バイト復元しました。

| 意図した誤り | 旧試験 | 新試験 |
|---|---|---|
| 再出現で古い飢餓時間を保持 | 成功 | 飢餓時間の断言で失敗 |
| 採食で古い飢餓時間を保持 | 成功 | 飢餓時間の断言で失敗 |
| 死亡操作が元の飢餓も変更 | 成功 | 元状態の断言で失敗 |
| 回復結果の生存状態を喪失 | 成功 | 結果状態の断言で失敗 |

保持の対照6種も旧新双方で検出しました。
HP0を生存扱いする、HP上限の丸めを外す、MP不足を受理する、
飢餓閾値を厳密な不等号にする、死亡までの時間を厳密な不等号にする、0設定でも進行する、
の6種です。最終採用した10種20実行に準備・後始末の失敗はありません。
死亡操作の変異は、正しい新状態を作ってから元の飢餓だけを変更する形に絞りました。
新状態の断言を通過し、元状態の断言だけで失敗します。新旧両状態を同時に変えた
最初の対照2実行は、この元状態保存の証拠から除外しています。

## 通常の検証

- 未編集対象49件と関連203件が成功。両範囲の試験ID重複0
- 変更後対象55件が成功
- 変異を復元後、対象55件と関連203件の計258件が成功
- 関連は `test_monster_aggregate.py` 196件と `test_monster_skill_execution_domain_service.py` 7件
- 集約196件には継承で再収集される88件が含まれます。新しい監査宣言として数えません
- Python3.10.22と固定依存を使用し、通信を遮断して実行しました
- 変更試験のruffと差分の空白検査が成功

全リポジトリの試験結果は、この変更を公開する正確なコミットのCIで別途確認します。
ローカルの関連検証から全体成功は主張しません。

## 履歴との対応

HP/MPの算術と例外は [初期実装](https://github.com/Motifman/llm-rpg/commit/452aae918104b0b1041e0b280fd8410831eebf6d)
から存在します。生命状態は [不変値への切出し](https://github.com/Motifman/llm-rpg/commit/b5ae027e80d2c02fe851f1e7739ee21bd18aa0e8)
で導入されました。[引数検証の追加](https://github.com/Motifman/llm-rpg/commit/5e85f0b3346deecfc1963272f97ca67017253fc6)
では負設定を黙って無効扱いせず、0設定と区別しています。これらの契約を保持しました。

## 全49宣言の台帳

位置は固定基準の行です。各行の保持試験は同じ宣言で、移管・削除する試験はありません。
Fの3行も元の契約を残して補強します。製品や共通補助の削除を伴う行はありません。
実利用者と責務の違い、導入履歴は前節に記載しました。

### `tests/domain/monster/value_object/test_monster_hp.py`

| 宣言（基準行） | 判断 | 契約 | 検出すべき退行 |
|---|---|---|---|
| `TestMonsterHp::test_create_success` (10) | R | 80/100の有効値を満タンへ勝手に変えず保存する | 現在値を最大値へ上書きする誤り |
| `TestMonsterHp::test_create_clamped` (16) | R | 120→100、-10→0の両側丸め | 上限または下限の丸めを外す誤り |
| `TestMonsterHp::test_create_fail_negative_max` (25) | R | 最大値-1のHPをドメイン例外で拒否する | 不正な最大値を受理する誤り。特定の検査順序は契約としない |
| `TestMonsterHp::test_damage` (30) | R | 100-30=70、さらに100被害で0へ丸める | 減算を加算にする、過剰被害で負値にする誤り |
| `TestMonsterHp::test_damage_negative_amount_raises_error` (39) | R | 負の被害-10を拒否する | 負の被害で回復してしまう誤り |
| `TestMonsterHp::test_heal` (45) | R | 50+30=80、さらに50回復で100へ丸める | 回復しない、過剰回復を上限に収めない誤り |
| `TestMonsterHp::test_heal_negative_amount_raises_error` (54) | R | 負の回復-10を拒否する | 負の回復で被害を生じさせる誤り |
| `TestMonsterHp::test_is_alive` (60) | R | HP1は生存、0は非生存 | 0を生存扱いする境界誤り |
| `TestMonsterHp::test_get_percentage` (65) | R | 50/100は0.5、0/0は0.0 | 整数除算または0除算。実利用者0のみを理由に削除しない |

### `tests/domain/monster/value_object/test_monster_mp.py`

| 宣言（基準行） | 判断 | 契約 | 検出すべき退行 |
|---|---|---|---|
| `TestMonsterMp::test_create_success` (13) | R | 40/50の有効値を保存する | 現在値を満タンへ上書きする誤り |
| `TestMonsterMp::test_create_clamped` (19) | R | 60→50、-5→0の両側丸め | 上限または下限の丸め欠落 |
| `TestMonsterMp::test_use_mp_success` (28) | R | 50から20を使って30にする | 消費量を無視する、加算する誤り |
| `TestMonsterMp::test_use_mp_fail_insufficient` (34) | R | 10から20を使う要求をMP不足例外で拒否する | プレイヤーMpのように0へ丸めて成功扱いする誤り |
| `TestMonsterMp::test_recover_mp` (40) | R | 10+20=30、さらに50回復で50へ丸める | 回復量の無視または上限超過 |

### `tests/domain/monster/value_object/test_monster_lifecycle_state.py`

| 宣言（基準行） | 判断 | 契約 | 検出すべき退行 |
|---|---|---|---|
| `TestMonsterLifecycleStateCreateForUnspawned::test_creates_dead_state_with_full_hp_mp` (23) | R | 未出現はDEAD、満タンHP/MP、両時刻なし、飢餓とタイマー0 | 未出現をALIVEにする、死亡時刻を初期設定する誤り |
| `TestMonsterLifecycleStateCreateForUnspawned::test_creates_with_minimal_stats` (36) | R | 最小HP1とMP0を許容する | MP0を不正扱いする誤り |
| `TestMonsterLifecycleStateCreateForSpawned::test_creates_alive_state_with_full_hp_mp` (46) | R | 出現はALIVE、満タンHP/MP、出現時刻100、死亡時刻なし、飢餓0 | 出現状態をDEADや過去の時刻にする誤り |
| `TestMonsterLifecycleStateCreateForSpawned::test_creates_with_initial_hunger` (62) | R | 指定された初期飢餓0.3を保存する | 初期飢餓を常に0にする誤り |
| `TestMonsterLifecycleStateCreateForSpawned::test_initial_hunger_clamped_to_valid_range` (73) | R | 初期飢餓1.5→1と-0.1→0 | 片側の丸め欠落 |
| `TestMonsterLifecycleStateValidation::test_rejects_hunger_above_one` (96) | R | 直接構築の飢餓1.1はドメイン例外 | 初期生成の丸めと直接構築の拒否を混同する誤り |
| `TestMonsterLifecycleStateValidation::test_rejects_hunger_below_zero` (112) | R | 直接構築の飢餓-0.1はドメイン例外 | 負の飢餓を直接受理する誤り |
| `TestMonsterLifecycleStateValidation::test_rejects_negative_starvation_timer` (128) | R | タイマー-1はドメイン例外 | 死亡までの計時に負値を受理する誤り |
| `TestMonsterLifecycleStateApplyDamage::test_applies_damage_returns_new_instance` (156) | R | 被害30で新しい状態のHP70、元HP100 | 元のHPを変更する、被害を反映しない誤り |
| `TestMonsterLifecycleStateApplyDamage::test_applies_damage_to_zero_hp` (163) | R | HP0になっても値オブジェクトはALIVEを維持し、死亡遷移を集約へ委ねる | HP計算が死亡時刻や死亡状態まで勝手に変える誤り |
| `TestMonsterLifecycleStateApplyDamage::test_rejects_negative_damage` (170) | R | 状態に対する被害-1を拒否する | 公開状態操作から負被害を受理する誤り |
| `TestMonsterLifecycleStateApplyHeal::test_applies_heal_returns_new_instance` (189) | R | 60から20回復で新しいHP80、元HP60 | 元のHPを変更する、回復を反映しない誤り |
| `TestMonsterLifecycleStateApplyHeal::test_heal_clamped_to_max_hp` (196) | R | HP60へ100回復して上限100にする | 状態操作から過剰回復を上限へ収めない誤り |
| `TestMonsterLifecycleStateApplyHeal::test_rejects_negative_heal` (201) | R | 状態に対する回復-1を拒否する | 負回復を受理する誤り |
| `TestMonsterLifecycleStateApplyMpRecovery::test_applies_mp_recovery` (219) | R | MP30に10回復で40、元は30 | 元MPを破壊する、回復を無視する誤り |
| `TestMonsterLifecycleStateApplyMpRecovery::test_rejects_negative_recovery` (225) | R | 状態に対するMP回復-1を拒否する | 負MP回復を受理する誤り |
| `TestMonsterLifecycleStateApplyMpUse::test_applies_mp_use` (242) | R | MP50から15消費で35、元は50 | 元MPを破壊する、消費を無視する誤り |
| `TestMonsterLifecycleStateApplyMpUse::test_insufficient_mp_raises` (248) | R | 状態のMP50に消費60を要求すると不足例外 | 状態ラッパーが不足を隠して成功する誤り |
| `TestMonsterLifecycleStateWithDeath::test_with_death_sets_status_and_tick` (265) | R | 死亡状態と死亡時刻100へ遷移し、出現時刻10と元ALIVEを保つ | 出現時刻を上書きする、元の生死を変更する誤り |
| `TestMonsterLifecycleStateWithSpawnReset::test_with_spawn_reset_full_recovery` (287) | F | 死亡からALIVE、HP120/MP60へ回復、時刻150、飢餓0.2、タイマー0、死亡時刻なし | タイマーを古い値で保持する誤りを補強前は見逃す（事前値0） |
| `TestMonsterLifecycleStateTickHunger::test_hunger_increases` (317) | R | 飢餓0→0.1、閾値前はタイマー0で死亡判定false | 増加停止、閾値前の誤死亡 |
| `TestMonsterLifecycleStateTickHunger::test_hunger_clamped_to_one` (328) | R | 飢餓0.95+0.1は1.0 | 飢餓上限の丸め欠落 |
| `TestMonsterLifecycleStateTickHunger::test_starvation_timer_increments_when_at_threshold` (346) | R | 増加後に閾値1へ達するとタイマー1、3未満で死亡false | 閾値の>=を>にする、計時の開始ずれ |
| `TestMonsterLifecycleStateTickHunger::test_should_starve_true_after_starvation_ticks` (366) | R | 閾値上でタイマー2→3となり3到達で死亡true | 必要時間の>=を>にする境界誤り |
| `TestMonsterLifecycleStateTickHunger::test_disabled_starvation_returns_unchanged` (385) | R | 必要時間0は同一状態とfalseを返す | 無効設定でも飢餓を進める誤り |
| `TestMonsterLifecycleStateTickHunger::test_rejects_negative_starvation_ticks` (395) | R | 必要時間-1を例外で拒否する | 負設定を無効設定として黙って受理する過去挙動への退行 |
| `TestMonsterLifecycleStateTickHunger::test_rejects_negative_hunger_increase` (405) | R | 増加量-0.1を例外で拒否する | 負増加量を無効設定として黙って受理する過去挙動への退行 |
| `TestMonsterLifecycleStateTickHunger::test_rejects_threshold_below_zero` (415) | R | 閾値-0.1を例外で拒否する | 範囲外の閾値受理 |
| `TestMonsterLifecycleStateTickHunger::test_rejects_threshold_above_one` (425) | R | 閾値1.5を例外で拒否する | 決して到達しない閾値受理 |
| `TestMonsterLifecycleStateTickHunger::test_zero_hunger_increase_returns_unchanged` (435) | R | 増加量0は同一状態とfalseを返す | 増加量0でも新状態を作る、または飢餓処理を進める誤り |
| `TestMonsterLifecycleStateTickHunger::test_timer_resets_when_below_threshold` (445) | R | 飢餓0.6→0.65で閾値未満なら既存タイマー2を0へ戻す | 閾値未満でも過去の飢餓時間を残す誤り |
| `TestMonsterLifecycleStateDecreaseHunger::test_decreases_hunger` (477) | F | 飢餓0.8から0.3減らして0.5、タイマーを0へ戻す | 採食時タイマーを旧値で保持する誤りを補強前は見逃す（事前値0） |
| `TestMonsterLifecycleStateDecreaseHunger::test_decrease_clamped_to_zero` (483) | R | 飢餓0.8から1.0減らして0に丸める | 負の飢餓を作る誤り |
| `TestMonsterLifecycleStateDecreaseHunger::test_zero_or_negative_amount_returns_self` (488) | R | 減少量0と-0.1は同じ状態を返す | 無効量が回復や飢餓増加を起こす誤り |
| `TestMonsterLifecycleStateImmutability::test_all_mutations_return_new_instance` (497) | F | 変更操作7経路が元と別の状態を返す | 別の状態を返しながら元のフィールドも書き換える誤りは補強前は見逃す |
