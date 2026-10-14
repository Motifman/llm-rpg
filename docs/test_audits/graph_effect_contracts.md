# 効果指示と可視性の監査

## 範囲と結論

固定したmainは `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。`WorldGraphEffectService` の同じ公開入口を使う2群を1つの修理単位として確認した。元宣言の計上は混ぜない。

| 群 | 元宣言 | 保持R | 修理F | 統合C | 削除D | 候補宣言 |
|---|---:|---:|---:|---:|---:|---:|
| 効果配送・可視性 | 19 | 16 | 3 | 0 | 0 | 19 |
| 領域横断の指示・欲求 | 16 | 11 | 4 | 1 | 0 | 15 |
| 計 | 35 | 27 | 7 | 1 | 0 | 34 |

初読と独立第二読で同じ判定になった。対象4ファイルは870→871行、変更試験3ファイルは追加37・削除36行。実行ケースは35→36件。製品・共有試験支援の変更は0、廃止ファイルは0。削除数や速度改善を成果として扱わない。

## 何を直したか

- 明示した可視性がサマリだけでなく `DamageSpec` にも届くことを確認
- 新規キーの元の値3を残し、値Noneでも新規差分が消えない行を追加
- 本人向け・公開向けの区分を集合から正確な列へ変え、重複と隠し区分への余分を検出
- 合成の削除品目1/2・付与99、複合効果の被害5・転移先10・文面を確認
- 通路指示の元のFalse/0.7を残し、件数1・ID9・CRACKEDも確認
- 複数欲求のHUNGER40/FATIGUE30の値と順序、付随文面を確認
- FATIGUE80をHUNGER50と同じ単一指示の表へ先に移し、元宣言と同居する37件が成功してから旧1宣言だけ除去

## 主担当と保持した層

| 契約 | 主担当 | 今回移管しない責務 |
|---|---|---|
| 全効果の処理登録・未登録時の拒否 | `effect_application/registry.py` と `handlers/__init__.py`、`test_effect_handler_registry.py` | 効果ごとの実適用 |
| 全効果の既定可視性・欠落拒否・属性優先 | `effect_application/visibility.py`、`test_effect_visibility.py` | シナリオ読込時の検証、保存形式 |
| サマリ区分と各回の状態差分 | `world_graph_effect_service.py` と状態別の処理、`test_effect_visibility.py` | 状態更新そのもの、知覚や第三者への実配送 |
| 被害・状態異常・転移・雰囲気・通路の指示生成 | `handlers/cross_domain.py`、`test_cross_domain_effects.py` | HP変化、集約の移動・状態遷移、保存・通知 |
| 合成の入出力品目 | `handlers/items.py` と `item_transfer.py`、`test_cross_domain_effects.py` | 所持品不足の事前拒否、実在庫の保存 |
| 欲求指示の種別・量と蓄積 | `handlers/cross_domain.py`、`test_satisfy_need_effect.py` | PlayerStatusの実回復・上限・通知 |

`SpotInteractionService.execute_interaction` / `execute_declared_interaction` は結果を `InteractionExecutionResult` へ運び、`SpotInteractionApplicationService` が指示を集約へ適用・保存する。対人操作、シナリオイベント、同期操作、会議も同じ効果サービスを呼ぶが、受け取る指示の用途は異なる。指示が1件生成されたことを、適用・保存・配送が成功した証明として扱わない。

品の実状態更新は `test_item_instance_state_effects.py` / `test_target_item_instance_state_effects.py`、自由状態の実更新は `test_player_state_effects.py` に残る。転移の宣言文4種と未指定時のNoneは `service/test_teleport_declared_observations.py` に残る。最小転移先42の元入力も今回保持した。

## 構造試験を残した理由

- [1d4e8d8](https://github.com/Motifman/llm-rpg/commit/1d4e8d8f4d8fd179c42d909cf8f396786b5783e1) は、効果別処理への分割時に全列挙との対応を構築時検査する意図を明記している。登録表の試験を単なる実装の写しとして削除しない
- [823d2b3](https://github.com/Motifman/llm-rpg/commit/823d2b3758faa31022d4da8252077d25eaadc230) と [9b85b29](https://github.com/Motifman/llm-rpg/commit/9b85b299faa0946ab091f23ff41aa2b1fdeb5fd5) は、可視性表の欠落が本人限定へ黙って縮退する問題を、全列挙一致・辞書参照・起動検査で止めた
- 無関係な変更でこの監査が削られた後、[b0cf57d](https://github.com/Motifman/llm-rpg/commit/b0cf57d2c4fe9b7af0acf72d36baf76ae2d62a18) が復元している。全列挙一致、実行時欠落拒否、起動用検査関数の欠落拒否をそれぞれ保持する
- [da34274](https://github.com/Motifman/llm-rpg/commit/da342744875c2246d5af6259678e469c542961a9) は、被害の公開既定値、欠落/Noneを区別する差分、明示属性の優先を修正した。元のNone→値、連続更新、同値更新の確認も残す

起動用検査関数の直接試験は、モジュール読込時の呼出そのものを検査した証明ではない。既存の可視性別名の再公開は変更しない。

## 同時進行の変更との責任分担

2026-10-14 10:27 UTCにmainと公開中76PRの先端・変更パスを再照合した。今回の3変更試験と製品の実主担当に直接パス競合はない。次の共有文脈は意味も分けた。

| PR | 確認した先端 | その変更に残す契約 |
|---|---|---|
| [#1684](https://github.com/Motifman/llm-rpg/pull/1684) | `3857a8ab75726f3299493b888bef41f71550441c` | 備蓄再生・消費と端数 |
| [#1688](https://github.com/Motifman/llm-rpg/pull/1688) | `4f4f39b596eea0a2d0288d28deb7471e88e6c338` | 備蓄条件の明示対象解決 |
| [#1735](https://github.com/Motifman/llm-rpg/pull/1735) | `037b2b17f182c97a174e0bca6a05b8015087a9bc` | 配置・移動通知対と行為者既定値 |
| [#1736](https://github.com/Motifman/llm-rpg/pull/1736) | `4207f79c28566a9ac2f39de2722bfaf99b9f2c91` | 通路の実状態更新・削除索引 |
| [#1739](https://github.com/Motifman/llm-rpg/pull/1739) | `0cd2f97820f89ad8b9e823acbeddf4b6861a768d` | 物体表示と公開状態・照明 |
| [#1740](https://github.com/Motifman/llm-rpg/pull/1740) | `2e291ae04d2d7bdbd9956f4451263b78662f0f6b` | パズル拒否時の保持・罠効果 |
| [#1741](https://github.com/Motifman/llm-rpg/pull/1741) | `fb8d9979fe3d07883ded4f18da0544810d5e985a` | 述語の部分一致・診断結果 |

配置側の未統合AGENTSを複製せず、この文書で今回の保持先を記録する。記憶・SNSの進行中変更を監査成果へ含めず、関連する試験や製品も編集しない。

## 全35宣言の台帳

Rは保持、Fは契約を保って判定を補強、Cは保持先へ先行移管した後に統合、Dは単純削除。位置は固定mainでの元宣言。

### 効果配送・可視性: 19宣言

- **R [test_all_effect_types_except_resolve_ongoing_have_handlers](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/service/test_effect_handler_registry.py#L32)**
  - 契約: 参照展開専用RESOLVE_ONGOING_CONDITIONを除く全列挙に処理が登録される
  - 誤変更: 新効果の登録漏れ、参照展開専用効果の誤登録
  - 判断: 1d4e8d8が新効果の登録漏れを構築時に落とすことを明示。全列挙から導く独立構造契約として保持
- **R [test_unregistered_effect_raises_unsupported_exception](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/service/test_effect_handler_registry.py#L43)**
  - 契約: 未登録効果の配送はUnsupportedInteractionEffectExceptionで止まる
  - 誤変更: handler不在で黙ってreturnする
  - 判断: 公開サービスでは先に展開されるRESOLVEを、registry境界の未登録入力として使用。未登録配送固有の責務
- **R [test_every_effect_type_has_an_explicit_default_visibility](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L79)**
  - 契約: 全効果の既定可視性を明示し、欠落・余剰を認めない
  - 誤変更: 新列挙の既定可視性を書き忘れる
  - 判断: 823d2b3/9b85b29で明示導入、b0cf57dで誤削除を復元。コードの形だけで削除しない
- **R [test_missing_default_visibility_raises_instead_of_falling_back](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L83)**
  - 契約: 可視性表の欠落はその場でKeyErrorになり本人限定へ縮退しない
  - 誤変更: 辞書添字参照をget(...,ACTOR_DIRECT)へ戻す
  - 判断: 起動検査とは異なる実行時の欠落検出。構造監査の過去復元対象として保持
- **R [test_missing_default_visibility_fails_startup_validation](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L100)**
  - 契約: 起動用検査は欠落の効果名を含めて失敗する
  - 誤変更: 検査をno-opにする、欠落を無視する
  - 判断: 直接呼出で検査関数自体を守る。モジュール読込時の呼出そのものを検査したとは主張しない
- **R [test_apply_damage_is_public_observable_by_default](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L161)**
  - 契約: 被害サマリとDamageSpecは既定でPUBLIC_OBSERVABLE、他区分は空
  - 誤変更: 被害の可視性を本人限定へ戻す、Specへの可視性転送を落とす
  - 判断: da34274で第三者に見える流血・よろめきの意味を修正。被害量15の別試験とは別責務
- **R [test_change_acting_item_state_is_actor_direct](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L185)**
  - 契約: 使った品の変化は本人向けでcharges 5→2の差分を返す
  - 誤変更: 使った品の変化を公開へ分類する、差分の更新前値を失う
  - 判断: 品の永続的状態更新はitem_instance_state_effects、ここは観測分類と差分
- **R [test_change_object_state_is_public_observable](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L210)**
  - 契約: 物体の状態変化は公開され、lit=Trueを差分へ載せる
  - 誤変更: 物体変化をHIDDENへ分類する、lit差分を落とす
  - 判断: 物体の照明/知覚/集約更新そのものは#1739に残し、効果結果の分類を保持
- **R [test_change_target_item_state_is_public_observable](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L230)**
  - 契約: 使われる側の品の状態変化は公開区分かつTARGET_ITEM_STATE_CHANGE
  - 誤変更: 使った側と使われる側の区分やkindを取り違える
  - 判断: 対象集約に実際に書き込む契約はtarget_item_instance_state_effects。ここで移管しない
- **R [test_change_player_state_is_hidden](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L253)**
  - 契約: 自由状態poisonedの差分はHIDDENだけへ入り他区分へ漏れない
  - 誤変更: 自由状態を公開/本人向けへ誤分類する
  - 判断: プレイヤー状態の実マージと可視性は異なる責務。毒付与のSpecと混同しない
- **F [test_first_class_field_takes_precedence_over_parameters](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L280)**
  - 契約: 明示属性ACTOR_DIRECTが旧parameters HIDDENより優先し、同じ値を被害指示へ運ぶ
  - 誤変更: サマリだけ上書きを反映しDamageSpec.visibilityをPUBLIC_OBSERVABLEへ固定
  - 判断: 現状は区分件数だけ。元入力を保ちkind/サマリvisibility/単一DamageSpecのvisibilityまで確認
- **R [test_player_state_can_be_lifted_to_actor_direct](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L303)**
  - 契約: 自由状態の既定HIDDENを明示属性でACTOR_DIRECTへ上書きできる
  - 誤変更: 状態効果が明示visibilityを無視する
  - 判断: 毒等を本人に知らせる上書きの独立入力を保持
- **R [test_change_object_state_can_be_hidden](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L326)**
  - 契約: 物理変化も明示HIDDENへ下げ公開区分へ出さない
  - 誤変更: 物体ハンドラが既定PUBLIC_OBSERVABLEへ固定する
  - 判断: 既定値だけでは隠し仕掛けの契約を代替できない
- **R [test_unknown_visibility_falls_back_to_default](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L344)**
  - 契約: 旧parametersに未知の可視性文字列があっても既定の公開区分へ進む
  - 誤変更: 未知値で例外、またはACTOR_DIRECTへ一律縮退する
  - 判断: 059e888/da34274の旧入力互換。欠落した表へのfail-fastと別の契約
- **F [test_new_key_records_before_none](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L366)**
  - 契約: 新規キーの差分をbefore=Noneとして残す。値がNoneでも新規追加を消さない
  - 誤変更: sentinelを捨ててbefore.get/after.getだけで比較する
  - 判断: 現状の{}→charges=3はgetのみでも通る。元の3を保持しNoneの行を加え、差分件数/key/before/afterを検査
- **R [test_explicit_none_to_value_is_recorded](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L387)**
  - 契約: 既存owner=Noneからaliceへの更新を差分として残す
  - 誤変更: Noneを未記録扱いにして差分を捨てる
  - 判断: 明示Noneと欠落は別入力。新規キーへ統合せず保持
- **R [test_sequential_mutations_capture_per_step_diff](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L407)**
  - 契約: 連続更新は5→3と3→1の独立した更新前後を順番に残す
  - 誤変更: 最終状態を両サマリへ使う、順序を反転する
  - 判断: 各回のsnapshotが必要な履歴上の回帰。単一更新で代替不可
- **R [test_no_op_update_yields_empty_delta](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L438)**
  - 契約: 同値更新でもサマリを返し差分は空にする
  - 誤変更: 同値差分を作る、サマリ自体を省く
  - 判断: da34274の明示方針。空結果だけの空振りではなくサマリkindを確認
- **F [test_actor_and_public_summaries_do_not_mix](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_effect_visibility.py#L461)**
  - 契約: 複数効果の本人/公開区分を排他的に分け、重複や隠し区分の余分を出さない
  - 誤変更: 区分内の同じサマリを二重化する、HIDDENへも複写する
  - 判断: 現状はsetと包含で重複を消してしまう。元のSATISFY/OBJECT入力のままkind列の完全一致とHIDDEN空を確認
### 領域横断・欲求: 16宣言

- **R [test_damage_spec_is_generated](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L21)**
  - 契約: 正の被害15とメッセージを1つのDamageSpecへ運ぶ
  - 誤変更: 被害量やメッセージを固定/欠落する
  - 判断: クロス領域の指示を生成する正本。HP減少や保存を証明したとは扱わない
- **R [test_zero_damage_is_ignored](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L36)**
  - 契約: 被害0ではDamageSpecを生成しない
  - 誤変更: 正数ガードを>=0へ緩める
  - 判断: 正数生成の隣の境界対照。負値全域の証明は主張しない
- **R [test_status_effect_spec_is_generated](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L53)**
  - 契約: POISON/3.0/50ticksを1つの状態指示へ運ぶ
  - 誤変更: 型名/値/期間の転送を落とす
  - 判断: 状態の実付与・期限処理はplayer/combat側の責務
- **R [test_empty_type_name_is_ignored](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L70)**
  - 契約: 期間が正でも空の状態種別名では指示を出さない
  - 誤変更: 型名の必要条件を取り除く
  - 判断: duration=10が正なので他ガードによる否定でない
- **R [test_teleport_spec_is_generated](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L87)**
  - 契約: 最小入力spot_id42から移動指示を1件生成する
  - 誤変更: 転移先を固定値/既定値に取り違える
  - 判断: 別所有のteleport_declared_observationsは文面有無/spot7を守る。最小指示と実移動/配置/観測文を同一視せず保持
- **R [test_atmosphere_update_spec_is_generated](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L105)**
  - 契約: spot3の危険度2と説明を環境更新指示へ運ぶ
  - 誤変更: 対象/危険度/説明の転送を取り違える
  - 判断: 環境の実適用・照明/公開知覚は#1739/実runtime試験。指示生成の正本を保持
- **F [test_input_items_removed_and_output_granted](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L130)**
  - 契約: 合成指示は入力品目1,2の削除と出力99の付与を正確に返す
  - 誤変更: 削除を1,1へ重複、付与を別品目にする
  - 判断: 件数だけで値を見ていない。元入力の削除値列[1,2]と付与値列[99]を独立固定値で検査
- **F [test_damage_and_teleport_accumulate](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L151)**
  - 契約: 同時指定の被害5/転移10/文面を別々の結果欄へ運ぶ
  - 誤変更: 複数効果の処理で値を固定/取り違えるが件数は維持する
  - 判断: 現状は3欄の長さのみ。元3効果を保持し各値と文面を完全確認
- **R [test_minimal_parameters_generate_spec](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L180)**
  - 契約: 通路7/BROKENの最小指定は1件になり両上書きはNone
  - 誤変更: 既定値の上書きを勝手にFalse/0へ変更する
  - 判断: 通路の実状態遷移を守る#1736とは別の指示生成。元既定値を保持
- **F [test_overrides_are_propagated_to_spec](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L198)**
  - 契約: 通路9/CRACKEDと通行False/音0.7を単一指示へ運ぶ
  - 誤変更: IDを7へ固定、状態をBROKENへ固定、同指示を二重追加
  - 判断: 現状は最初の2上書き属性のみ。元入力の長さ1・ID9・状態CRACKEDも確認
- **R [test_missing_new_state_is_ignored](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_cross_domain_effects.py#L218)**
  - 契約: connection_idがあってもnew_state未指定なら指示なし
  - 誤変更: 必須状態のガードを外して既定状態を生成する
  - 判断: 正常最小指定の隣の負対照。IDは有効なので状態以外のガードに依存しない
- **R [test_satisfy_need_spec_generated](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_satisfy_need_effect.py#L21)**
  - 契約: HUNGER50の種別/量を単一欲求指示へ運ぶ
  - 誤変更: 量の欠落、種別固定、指示の二重追加
  - 判断: 同じ所有入口のFATIGUE80を表の別行として先に吸収する予定。HUNGER元入力・判定を保つ
- **C [test_fatigue_satisfy](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_satisfy_need_effect.py#L37)**
  - 契約: FATIGUE80の入力から疲労回復指示を作る
  - 誤変更: 欲求種別をHUNGERへ固定する
  - 判断: 同ファイルtest_satisfy_need_spec_generatedの(HUNGER,50)/(FATIGUE,80)表へ吸収。元FATIGUE入力を保ちamount=80も検査してから旧宣言を除去
  - 保持先: `TestSatisfyNeedEffect.test_satisfy_need_spec_generated[FATIGUE-80]`
- **R [test_zero_amount_ignored](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_satisfy_need_effect.py#L51)**
  - 契約: 有効HUNGERでも量0は指示を生成しない
  - 誤変更: amount>0を>=0へ緩める
  - 判断: 種別が有効なので量ガードを独立検査。正例表を維持
- **R [test_empty_need_type_ignored](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_satisfy_need_effect.py#L64)**
  - 契約: 量50でも欲求種別が空なら指示を生成しない
  - 誤変更: 種別必須ガードを取り除く
  - 判断: 量が正なので型名ガードに到達する独立負対照
- **F [test_multiple_satisfy_effects](https://github.com/Motifman/llm-rpg/blob/ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f/tests/domain/world_graph/test_satisfy_need_effect.py#L77)**
  - 契約: HUNGER40/FATIGUE30を順に蓄積し、付随文面を返す
  - 誤変更: 両指示を同じ種別/同じ量へする、順序を反転する、文面を失う
  - 判断: 現状は件数だけ。元3入力を保ち[(HUNGER,40),(FATIGUE,30)]と文面完全一致を検査

## 実行した証拠

Python3.10.22 / pytest8.4.1、固定依存の実行環境で、秘密・proxy設定を除去しネットワーク接続を遮断した。各変異実行は専用のPythonキャッシュと新規証拠名を使い、対象作業木のsrcが読み込まれることを確認した。

- 未編集基準: 所有35件と関連28件、全63件成功
- 保持先先行: 旧FATIGUE宣言を残して37件成功
- 統合後: 所有36件成功
- 復元後最終: 所有36＋関連28＝64件成功。失敗・収集エラー・skip0
- 15種類・旧新30実行。14種類は元の対応焦点が成功し、修復した焦点が意図した判定で失敗。1種類は統合元と保持先が同じ故障を検出
- 毎回元バイトへ復元。原本・候補の追跡src/tests全3176ファイルを照合。原本差分0、候補は指定3試験だけ、製品1601ファイルは全一致
- R27のうち表を拡張した保持先1宣言以外の26宣言は構文木が不変。元のHUNGER50・FATIGUE80・charges=3の入力を残した
- Ruff0.16.8と `git diff --check` 成功

関連28件は品目削除の事前拒否5、転移宣言文2、シナリオイベントの確定/巻戻し10、実runtimeの雰囲気変更・配送11。これらや反復回数を35宣言の監査済み件数へ加算しない。

### 故障ごとの旧新比較

各回は旧35件/新36件の全所有試験を実行した。表の「旧全体失敗数」が0の8種類だけが、この所有範囲全体で新しく検出できた故障である。既存の別試験が既に検出する6種類は、対応する複合・区分試験の空振りを直したものとして分ける。

| 故障 | 旧全体失敗数 | 新全体失敗数 | 対応焦点 |
|---|---:|---:|---|
| 被害指示だけ可視性上書きを失う | 0 | 1 | 旧成功→新失敗 |
| 欠落値をNoneと同一視する | 0 | 1 | 旧成功→新失敗 |
| 本人区分を二重化 | 4 | 5 | 旧成功→新失敗 |
| 公開区分を二重化 | 4 | 5 | 旧成功→新失敗 |
| 公開サマリを隠し区分にも複写 | 1 | 2 | 旧成功→新失敗 |
| 合成の入力品目を最初のIDへ重複 | 0 | 1 | 旧成功→新失敗 |
| 合成出力IDを1ずらす | 0 | 1 | 旧成功→新失敗 |
| 被害量を1ずらす | 1 | 2 | 旧成功→新失敗 |
| 転移先を1ずらす | 1 | 2 | 旧成功→新失敗 |
| 通路IDを7へ固定 | 0 | 1 | 旧成功→新失敗 |
| 通路状態をBROKENへ固定 | 0 | 1 | 旧成功→新失敗 |
| 欲求指示を逆順にする | 0 | 1 | 旧成功→新失敗 |
| 欲求量を1ずらす | 1 | 3 | 旧成功→新失敗 |
| 欲求種別をHUNGERへ固定 | 2 | 3 | 旧新とも検出（統合保持） |
| 文面を別の内容へ変更 | 0 | 2 | 旧成功→新失敗 |

量を1ずらす故障では、統合後のFATIGUE80行も81との相違で失敗した。文面故障では被害/転移の複合と欲求の複合の両方が、件数を保った誤文面を検出した。

文面故障の準備で、置換元を誤って `append(str(msg))` とした。置換件数0の事前検査で製品を書き換える前に止め、実ソースの `append(msg)` へ訂正して残り1種類だけ実行した。既存14種類の生結果は上書き・再実行していない。

## 限界と残した仕事

公開後の正確な先端CIは別途確認する。全リポジトリ試験、実LLM、有料API、性能比較は実行していない。製品不具合の修理、Issue作成、マージは含めない。効果指示の保持を、すべての利用先での効果消費・配送の網羅証明として扱わない。
