# 資源更新・拒否・成長接続の試験監査

確認日: 2026年10月14日。対象は `PlayerStatusAggregate` の元39宣言。
R21/F18/C0/D0。宣言を削除せず、元139確認式・入力・固有例外を保持した。

## 依存基準と範囲

この変更は [状態効果の保持修理 #1722](https://github.com/Motifman/llm-rpg/pull/1722) に依存する。
固定基準は `7aaa8bbc7a5628de63fb95c4807b2fada58009d4`、
基準ブランチは `codex/test-audit-player-active-effects-20261014`。
この基準に含まれる先行修理を再計上しない。

対象ファイルの元68宣言は、今回39、既監査の注意3＋状態効果3、未監査23に分かれる。
未監査23は位置・追跡14、発話7、合成戦闘2。これらと7準備関数の本文・構文木は不変。
対象は39宣言39実行行から39宣言40実行行、ファイル全体は68宣言69実行行になった。
試験差分は+100/-20行。製品・共有支援の変更はない。

## 何が見えていなかったか

- 元の成長行はHP100/MP50の満タンだった。残量を旧上限に戻しても見逃すため、元行を残してID7・HP37/MP19の行を加え、現在値の持越しと通知先を確認した
- 上限を超える回復は最終残量だけを見ていた。元のHP90+20、MP45+10、stamina90+20を保持し、通知する実回復量10/5/10と回復後値を確認した
- 例外だけを見る拒否行は、対象値の部分変更や成功を表す通知の生成を見逃す。元の固有例外・残量確認を保持し、その操作の対象値と成功通知に限定して追加した
- 部分費用の逐次消費は、今回使わない資源が既定値へ戻る誤りを見逃す。元のMP10→stamina20→HP30と全確認式を残し、省略費用の資源が持ち越されることを確認した

復帰率.5の短い独立入力は統合せずRへ戻した。回避成功のHP不変は既存の合成戦闘行が既に検出するため、移管判断前に同じ比較を追加しなかった。
初期値、通常の増減、0費用、拒否の優先順位も短いことだけを理由に削除していない。

## 主担当と限界

資源値は丸め・算術・不変性、成長値は経験値曲線や能力値の計算を所有する。
集約はその結果をHP/MP上限へ接続し、成立した操作の通知を積む。
実消耗品入口は集約を呼んで保存・配信し、実技能入口は資源消費後に冷却・攻撃判定生成を進める。
今回の集約試験だけで保存や観測配信まで証明したとはしない。

拒否時に禁止するのは対応する成功通知であり、将来の失敗記録など全イベントを禁止しない。
プロフィール・位置・自由状態まで含む一般的な原子性や、任意の入力の巻戻し仕様を新設していない。
一括消費の正量入力での保持は、元試験と導入履歴にある検証後の消費を守る。

成長の期待値は入力由来の37/19とID7。通知の能力値と更新後能力値を比較する自己追認は追加しない。
注入済み係数とレベル別係数のどちらを優先すべきか、通知の能力値の正確な数値は今回新たに検証しない。
これは追加網羅の限界であり、実証済みの製品不具合とは扱わない。元のレベル、経験値、上限増加、HP/MP接続、通知件数・型・旧新レベルの契約は読解し全保持した。

## 元39宣言の台帳

全て同じ `tests/domain/player/aggregate/test_player_status_aggregate.py` の主担当へ残す。
Rは本文不変、Fは元の入力・確認式を残して観測を補う。

| 宣言 | 判定 | 保護する契約 | 保持・修理 |
|---|---|---|---|
| `test_create_status_aggregate` | R | 構築したID、基本能力、資源残量/上限、成長、非ダウン既定値を公開参照できる | 本文と構文木を変更せず保持する。 |
| `test_apply_damage_normal` | R | 100から30の被害で70、未ダウン、通知なし | 本文と構文木を変更せず保持する。 |
| `test_apply_damage_down` | R | 残HPと同じ被害で0/ダウン、加害者なし通知1件 | 本文と構文木を変更せず保持する。 |
| `test_apply_damage_down_with_killer_player_id` | R | 致死被害時に加害者PlayerId(2)を通知する | 本文と構文木を変更せず保持する。 |
| `test_apply_damage_over_kill` | R | 残量より大きい被害を0に制限し集約もダウンする | 本文と構文木を変更せず保持する。 |
| `test_record_evasion_success` | R | 公開の回避記録でHP80の通知を1件得る | 本文と構文木を変更せず保持する。 |
| `test_record_evasion_when_downed_raises_exception` | F | ダウン中の回避記録は専用例外で拒否する | 元is_down=True/HP100と固有例外・文言を保持し、HP100およびPlayerEvadedEventがないことを追加する。 |
| `test_gain_exp_level_up` | F | 経験60でレベル1→2、成長に合わせてHP/MP上限更新し通知1件 | 元ID1・HP100/MP50の行を保持し、ID7・HP37/MP19の行を追加。元の60加算と全assertを維持。現在HP/MPが入力のまま、通知ID/集約型が当人であることを独立した入力値・固定文字列で確認する。 |
| `test_gain_exp_no_level_up` | R | 経験49はレベル1で蓄積され通知しない | 本文と構文木を変更せず保持する。 |
| `test_gain_exp_when_downed` | F | ダウン中の経験獲得を専用例外で拒否する | 元is_down=True、50加算と例外/文言を保持。level1,total_exp0と、PlayerLevelUpEventの不発を確認する。 |
| `test_heal_hp` | R | HP50に30回復して80、実回復量30/総HP80通知を1件出す | 本文と構文木を変更せず保持する。 |
| `test_heal_hp_over_max` | F | HP90に20回復を受けても100に制限する | 元HP90＋20→100を保持し、回復通知1件の型・実回復量10・total_hp100を追加確認する。 |
| `test_use_mp_normal` | R | MP50から20消費して30、消費通知を1件出す | 本文と構文木を変更せず保持する。 |
| `test_use_mp_insufficient` | F | MP10で20消費は拒否し残量10を保持 | 元MP10、20消費の固有例外と残量10を保持。PlayerMpConsumedEventがないことを確認する。 |
| `test_use_mp_when_downed` | F | 足りるMPがあってもダウンなら拒否する | 元ダウン入力と20消費の例外/文言を保持。MP50とPlayerMpConsumedEvent不発を確認する。 |
| `test_heal_mp` | R | MP20に15回復して35、実回復量15の通知 | 本文と構文木を変更せず保持する。 |
| `test_heal_mp_over_max` | F | MP45に10回復して上限50に制限する | 元MP45＋10→50を保持。回復通知1件の型・実回復量5・total_mp50を確認する。 |
| `test_consume_stamina_normal` | R | スタミナ100から20消費して80、対応通知を1件得る | 本文と構文木を変更せず保持する。 |
| `test_consume_stamina_insufficient` | F | 残スタミナ10で20は拒否し10を保つ | 元stamina10、20消費の例外/文言と残量10を保持。PlayerStaminaConsumedEvent不発を確認する。 |
| `test_consume_stamina_when_downed` | F | ダウン中は十分なスタミナでも消費を拒否する | 元ダウン入力・20消費の例外/文言を保持。stamina100とPlayerStaminaConsumedEvent不発を確認する。 |
| `test_heal_stamina` | R | 公開消費後50/100から25回復して75、通知25/75 | 本文と構文木を変更せず保持する。 |
| `test_heal_stamina_over_max` | F | 公開消費後90/100に20回復して100に制限する | 元100から10消費・clear_events・20回復→100を保持。回復通知1件の型・実回復量10・total_stamina100を確認する。 |
| `test_revive_normal` | R | ダウンHP0から0.1回復率で10、ダウン解除、復活通知10/10 | 本文と構文木を変更せず保持する。 |
| `test_revive_custom_rate` | R | 指定0.5回復率はHP50でダウン解除する | 本文と構文木を変更せず保持する。 |
| `test_downed_transition_flow` | R | 公開被害→ダウン中回復無効→蘇生→回復再開の状態遷移 | 本文と構文木を変更せず保持する。 |
| `test_revive_not_down` | F | 未ダウンの蘇生を専用例外で拒否する | 元非ダウン・HP100・回復率.5と例外/文言を保持。HP100/非ダウンおよびPlayerRevivedEvent不発を確認する。 |
| `test_earn_gold` | R | 100に50を加えて150、獲得通知50/150が1件 | 本文と構文木を変更せず保持する。 |
| `test_pay_gold_normal` | R | 100から30支払い70、支払通知30/70が1件 | 本文と構文木を変更せず保持する。 |
| `test_pay_gold_insufficient` | F | 所持20で50支払は専用拒否し所持20を保持 | 元gold20・50支払の固有例外と残額20を保持。PlayerGoldPaidEvent不発を確認する。 |
| `test_pay_gold_when_downed` | F | 100所持してもダウン中30支払を拒否する | 元ダウン・gold100・30支払の例外/文言を保持。gold100とPlayerGoldPaidEvent不発を確認する。 |
| `test_can_act_methods` | R | 非ダウン/ダウンで行動・回復・資源消費の公開可否が反転する | 本文と構文木を変更せず保持する。 |
| `test_consume_resources_zero_costs` | R | 3種0コストは資源を保ち通知しない | 本文と構文木を変更せず保持する。 |
| `test_consume_resources_all_success` | R | 3種の一括消費が70/40/80となりMP/スタミナ2通知 | 本文と構文木を変更せず保持する。 |
| `test_consume_resources_insufficient_mp` | F | MP不足ではHP/MP/スタミナ全てを保持して拒否 | 元HP100/MP5/stamina100、費用10/20/30、例外と全3残量assertを保持。MP/スタミナ消費・ダウンの各成功イベントがないことを追加する。 |
| `test_consume_resources_insufficient_stamina` | F | 先に足りるMPがあってもスタミナ不足は全資源を保持して拒否 | 元HP100/MP50/stamina10、費用10/20/30、例外と全3残量assertを保持。対応する消費・ダウン成功イベント不発を確認する。 |
| `test_consume_resources_insufficient_hp` | F | HPを尽かすコストを拒否し全資源を保持 | 元HP20/MP50/stamina100、費用10/20/30、例外と全3残量assertを保持。対応する消費・ダウン成功イベント不発を確認する。 |
| `test_consume_resources_when_downed` | F | ダウン時は足りる3資源でも一括消費を拒否 | 元ダウンと費用1/1/1、例外/文言を保持。HP100/MP50/stamina100と、対応する消費・ダウン成功イベント不発を確認する。 |
| `test_consume_resources_partial_costs` | F | MPのみ→スタミナのみ→HPのみの指定分だけを消費する | 元の逐次MP10→stamina20→HP30と全assertを保持。第2操作後にHP100/MP40、第3操作後にMP40/stamina80も確認する。 |
| `test_consume_resources_validation_priority` | R | 複数不足時の外部に見える例外優先度MP→スタミナ→HP | 本文と構文木を変更せず保持する。 |

## 意図的な故障との旧新対照

保存した対照は27種類×旧新2＝54実行。25種類は旧84件が全成功し、新版の追加比較だけが失敗した。
全F18が少なくとも1種類の狙った失敗で覆われる。保持2種類は旧新とも元の比較で失敗した。
以下の失敗数は実行全体の数で、準備・後始末・収集の失敗は全て0。

| 故障 | 検証する退行 | 旧失敗 | 新失敗 |
|---|---|---:|---:|
| `01_growth_hp_old_max` | 元満タンでは見えないHP残量の旧上限への置換 | 0 | 1 |
| `02_growth_mp_old_max` | 元満タンでは見えないMP残量の旧上限への置換 | 0 | 1 |
| `03_growth_default_recipient` | 非既定ID7への成長通知が既定ID1へ送られる | 0 | 1 |
| `04_growth_wrong_aggregate_type` | 成長通知の公開集約型取り違え | 0 | 2 |
| `05_evasion_event_before_rejection` | 回避成功通知を行動可否検証前へ移動 | 0 | 1 |
| `06_evasion_hp_before_rejection` | ダウン拒否前にHPを変更 | 0 | 1 |
| `07_growth_before_down_rejection` | ダウン拒否前に獲得経験値を確定 | 0 | 1 |
| `08_growth_event_before_down_rejection` | 拒否された経験値獲得をレベルアップ成功として通知 | 0 | 1 |
| `09_hp_requested_heal_report` | 上限丸め後の実回復量ではなく要求量を通知 | 0 | 1 |
| `10_mp_requested_heal_report` | 上限丸め後の実回復量ではなく要求量を通知 | 0 | 1 |
| `11_stamina_requested_heal_report` | 上限丸め後の実回復量ではなく要求量を通知 | 0 | 1 |
| `12_mp_event_before_validation` | 成功通知を検証前へ移動。正常時の差引後通知値は保つ | 0 | 2 |
| `13_stamina_event_before_validation` | 成功通知を検証前へ移動。正常時の差引後通知値は保つ | 0 | 2 |
| `14_gold_event_before_validation` | 成功通知を検証前へ移動。正常時の差引後通知値は保つ | 0 | 2 |
| `15_mp_deduct_before_down_rejection` | ダウン拒否前に対象資源を消費 | 0 | 1 |
| `16_stamina_deduct_before_down_rejection` | ダウン拒否前に対象資源を消費 | 0 | 1 |
| `17_gold_deduct_before_down_rejection` | ダウン拒否前に対象資源を消費 | 0 | 1 |
| `18_revive_hp_before_rejection` | 非ダウン拒否前に復帰率でHPを再設定 | 0 | 1 |
| `19_revive_event_before_rejection` | 復帰成功通知をダウン検証前へ移動。正常時の値は保つ | 0 | 1 |
| `20_resource_rejection_reports_consumed` | 拒否した消費の記録を成功通知型で積む | 0 | 4 |
| `21_resource_hp_before_down_rejection` | 一括消費のダウン拒否前に一資源だけ更新 | 0 | 1 |
| `22_resource_mp_before_down_rejection` | 一括消費のダウン拒否前に一資源だけ更新 | 0 | 1 |
| `23_resource_stamina_before_down_rejection` | 一括消費のダウン拒否前に一資源だけ更新 | 0 | 1 |
| `24_partial_resets_mp` | 部分費用で省略資源を満タンへ戻す | 0 | 1 |
| `25_partial_resets_stamina` | 部分費用で省略資源を満タンへ戻す | 0 | 1 |
| `26_keep_custom_revive_rate` | Rへ戻した非既定復帰率.5の独立証明を保持 | 2 | 2 |
| `27_keep_evasion_payload` | Rへ戻した回避通知と未監査合成試験の重なりを明示して保持 | 2 | 2 |

保持対照26の復帰率0.1固定は、集約の.5入力と実消耗品入口の.4入力の両方を旧新とも検出した。
具体的には10≠50と1≠4。初期の期待失敗一覧が後者を含めず集計を止めたが、保存済みの同じ結果を再検証し、既存関連の検出として記録した。新しい検出改善に数えず、同じ実行を再計上していない。
保持対照27も回避成功1行と合成戦闘の回避1行、計2行が旧新とも失敗するため、重なりを隠していない。
初期集計の例外表記判定も、pytestの短縮表示による目的のassert失敗を生結果で確認して修正した。製品・試験を通すための変更ではない。

## 実施した試験

- 未編集の全68＋外部関連16＝84一意成功。対象39、既監査6、対象外23を区別
- 候補の全69＋外部16＝85一意成功
- 旧新54実行の失敗位置・実行元・準備と後始末を照合
- 製品1601 Pythonファイルと候補試験を元のバイト列へ復元
- 復元後の全69＋外部16＝85一意成功、重複・失敗・エラー・skipなし
- 元139確認式、R21、既監査6、対象外23、7準備関数の保持を独立照合
- Ruff0.16.8と `git diff --check` 成功。Python3.10.22／pytest8.4.1

外部16は資源値6、成長値4、実消耗品入口4、実技能入口2。
基準#1722にある元の行を実行し、別PR#1674/#1724の追加行を実行したとは数えない。
対象作業木の製品を読み込み、通信を遮断して直列実行した。実LLM呼出しはない。
全リポジトリ試験はローカルでは実施していない。公開後の正確な先端CIは別途確認する。

## 履歴と利用経路

- [集約と元資源試験の導入](https://github.com/Motifman/llm-rpg/commit/9815404270d9c7bf00ea997c03e79fea26ec538f)
- [戦闘計算分離と回避・復帰引数の整理](https://github.com/Motifman/llm-rpg/commit/1cf0e10b10ab80a45380695c6798dde5542c5bf5)。復帰引数を割合から設定へ変更した履歴であり、現在の値引数への変更根拠とはしない
- [技能の一括資源検証・消費](https://github.com/Motifman/llm-rpg/commit/819fb4d4ba29f8219b3303ac57a3a7c2b2742703)

実利用者は `ConsumableEffectHandler`、`SkillExecutionDomainService`、`SkillCommandService`、
`ShopCommandService`、`MonsterDeathRewardHandler`、`QuestProgressReactionService`。
イベント型と観測の登録・整形経路も読み、成功していない操作を成功通知型で表さない範囲へ修理を絞った。

## 今後の所有ルールと引継ぎ

この節は今回の資源・成長接続39だけへ適用する。

1. 資源の算術・丸めを値型で、実回復量や成功通知を集約で検査する。同じ丸めだけを別層に重ねない
2. 成長時の残量保持には非満タンで区別できる値を使う。能力値の計算結果同士を期待値にしない
3. 拒否行は固有ガードへ到達させ、操作対象値と対応成功通知を確認する。無関係な全状態や全イベント空を新仕様にしない
4. 元の値・型・例外・診断の独立入力を残す。既存の強い主担当がある比較を無条件に追加しない
5. 関連試験が故障を検出した場合も記録し、新しい独自改善と既存の保持証明を分ける

`tests/domain/player/aggregate/AGENTS.md` は#1699、親の `tests/domain/player/AGENTS.md` は#1725が新規追加中である。
同名追加の競合を避ける承認済み例外として今回はこの文書に記載し、両PR統合後に既存AGENTSへ本節を追記する引継ぎを残す。既存PRは変更しない。
残る位置・追跡14、発話7、合成戦闘2は未監査のまま。関連16や既監査6へ今回の完了を広げない。
