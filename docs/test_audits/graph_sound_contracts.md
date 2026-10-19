# 環境音・気配・発話伝播の試験監査

## 対象と結果

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。対象5ファイル43宣言を全件読み、独立した第二読でも R37（保持）・F4（契約を保持して修復）・C2（確認を保持先へ移して統合）・D0（削除のみ）とした。

| 対象 | 元宣言→候補 | 元ケース→候補 | 元行数→候補 |
| --- | ---: | ---: | ---: |
| `aggregate/test_spot_graph_listen_carefully.py` | 8→8 | 8→8 | 250→250 |
| `aggregate/test_spot_graph_sound_observation.py` | 4→4 | 4→4 | 149→149 |
| `aggregate/test_spot_graph_sound_permeability_attenuation.py` | 13→12 | 28→30 | 348→355 |
| `enum/test_sound_intensity_enum.py` | 9→8 | 9→8 | 75→71 |
| `test_sound_propagation_service.py` | 9→9 | 9→9 | 193→193 |
| 計（すべて `tests/domain/world_graph/` 配下） | 43→41 | 58→59 | 1015→1018 |

試験差分は追加29・削除26の3行増。廃止ファイル0。製品、共有準備、試験専用の製品入口は変更0。削除数や速度改善を目的にしていない。保持37宣言のうち36は構文木が不変で、残る `test_level_value` に統合元の不等式2つを移した。

## 修復した4つの検査

1. 人数を返す透過率1.0の元表は0人と1人だけだった。3人の行を追加し、人数を1に丸める誤りを見えるようにした。元7行を維持した
2. 現在地の除外を調べる試験に自己接続が無かった。元入力に加え、公開の `add_connection` で現在地→現在地を登録する行を設けた。自己接続があっても隣接地点Bの通知1件・人数0だけが残る。この試験が独立して証明するのは現在地の観測行除外であり、整合した配置では到達しない「聞き手が隣接地点にも居る」状態を作っていない
3. 非隣接地点Cの否定が `all(...)` だけで、通知が空でも成功していた。元のCに居る人物と否定判定を残し、隣接Bの通知1件・音源B・人数0を確認した。「Cを返さない」と「Bの不在観測が存在する」を同時に確かめる
4. 最良透過経路の試験は、減衰の大きい壁→小さい開扉の順に登録していた。最小比較を落として最後の値で上書きしても通るため、開扉→壁の逆順を追加した。元の壁→扉入力とFAINTの環境音・hops1の気配・各1件という期待値を維持した

## 重複の統合と残す層

- 開口を通るLOUD→MODERATEは `TestEmitListenCarefullyAdjacent.test_loud_neighbor_moderate_trigger` を主担当にした。同じSILENTの聞き手地点と隣接LOUD、開口、空の行動可能者集合を使い、元試験の件数・強度に加えて聞き手地点・音源・説明を確認する。`TestOpenPassage1Hop.test_open_loud_moderate` のみを統合した
- `TestLevelOrdering.test_level_order` の不等式2つを `test_level_value` へ移した。4つの整数値を独立定数で確認する試験へ、公開の比較契約をまとめた
- 統合元2宣言が残る状態で保持先を先に整え、61件の成功を確認してから元宣言を除いた。統合後は59件成功
- 初回配置と接続移動の受動環境音、能動的な聞き取り、通路種別ごとの実減衰、公開強度API、発話の到達と方向は入口や結果が異なるため、それぞれ残した
- BROKEN壁・OPEN扉・CLOSED扉・CRACKED壁・INTACT壁・BARRIERのケースは構築の見た目だけで削除していない。実際の聴覚通知まで到達し、既定透過率を利用する契約を持つ
- `sound_permeability_to_hops` の0.7/0.4/0.1の両側、強度の下限、非正のhops、hops省略時の1も公開契約として保持した
- `clarity_for_listener` の現在の製品呼出は0だが、[方向情報の導入](https://github.com/Motifman/llm-rpg/commit/25c7825ab9469bbe161891be94742b3d182e76e7) は互換用の入口として維持すると明記している。呼出数だけで試験や入口を削除していない

## 製品所有者と関連入口

- `SpotGraphAggregate.place_entity` / `move_entity` / `teleport_entity` は受動環境音、`emit_listen_carefully` は環境音と隣接の気配を生成する。実イベントの値を検査し、私有ヘルパーの呼出形へ置き換えていない
- `WorldRuntime.do_listen` が倒れていないプレイヤーの集合を作り、集約は位置を使って人数を数える。観測の受信者解決と文章化はアプリ層の別責任
- `SoundIntensityEnum.attenuate` と `passage.py` の `sound_permeability_to_hops` は環境音の離散減衰を所有する。発話の `SoundPropagationService` は音量による最大距離、透過率の積、明瞭さ、受信直前の接続方向を所有する。似た名前でも同じ計算ではない
- 発話の製品呼出は `SpeechAudienceResolver`、`SpotGraphSpeechRecipientStrategy`、`PlayerObservationFormatter`。`outcome_between_spots` は別位置に居る死亡後の主体にも使われる。このAPIの全契約を今回の9宣言だけで検証したとは主張しない
- SQLiteの音強度保存、観測文章、受信者の本人選別、ツールからruntimeへの接続、実runtimeの発話配送は関連試験として実行した。これらを今回43宣言の監査済み件数へ加えていない

## 意図的な誤変更による旧新対照

同じ局所的な誤変更を元58件と候補59件で直列に実行し、毎回製品ファイルを元のバイト列へ戻した。表中の成功/失敗は各所有一式の結果。収集エラーとskipは全対照で0。

| 誤変更 | 元58件 | 候補59件 | 直接の検出点 |
| --- | --- | --- | --- |
| 高透過率の人数を `min(moving_count, 1)` に丸める | 全成功 | 1失敗 | 追加した1.0・3人→3の行 |
| 現在地への自己接続を除外しない | 全成功 | 1失敗 | 追加した自己接続ありの行 |
| 行動可能者候補が遠隔にだけ居る場合、隣接の0人通知を省略 | 全成功 | 1失敗 | 非隣接Cを残した入力で、隣接Bの通知件数が0になり失敗 |
| 最小減衰を比較せず、後の接続で上書き | 全成功 | 1失敗 | 追加した開扉→壁の逆順行 |
| 開口の量子化を1から2へ変える | 10失敗 | 11失敗 | 統合先 `test_loud_neighbor_moderate_trigger` が旧新ともMODERATEの期待値で失敗 |
| FAINTとMODERATEの公開levelを交換 | 15失敗 | 14失敗 | 統合先 `test_level_value` が旧新とも固定整数の期待値で失敗 |

前半4種が新しく検出できる故障。後半2種は既存契約の保持を確かめる対照で、新規検出とは数えない。全体の失敗だけでなく、統合先自身の失敗を確認した。非隣接の故障は実際に通る人数計算後の分岐で通知を省き、別のガードや例外を失敗理由にしていない。

## 実行結果と限界

Python 3.10.22 / pytest 8.4.1。保存済みの実行器で明示した作業木を指定し、インターネット接続を遮断、秘密値を環境から除外、外部モデルの取得を停止して実行した。通常のquality/live_api除外を維持し、実LLM・有料API・ネットワーク試験は実施していない。

- 未編集基準: 所有58＋関連38＝96件、すべて成功
- 統合元を残した保持先先行: 所有61件、すべて成功
- 統合後: 所有59件、すべて成功
- 意図的誤変更: 6種×旧新の12実行、期待どおり。反復実行を網羅件数へ加算しない
- 復元後の最終: 所有59＋関連38＝97件、すべて成功、失敗・収集エラー・skipなし
- 全製品Python1,601ファイルは両作業木で基準ハッシュと一致。原本は製品・試験Python3,158ファイル、候補は変更2試験以外の3,156ファイルを照合。復元後には変更対象モジュールの生成済みバイトコードも除いて実ソースを再読込
- Ruff 0.16.8 の対象2ファイルと `git diff --check` が成功。書式全体の変更はしていない

関連38件の指定は次のとおり。

1. `tests/application/observation/test_monster_reaction_state_prose.py::TestSpotSoundHeardProse`（4件）
2. 同 `::TestSpotPresenceListenedProse`（5件）
3. `tests/application/observation/test_spot_graph_recipient_strategy.py::TestSpotSoundHeardRecipientResolution`（4件）
4. `tests/application/observation/test_spot_graph_speech_observation.py`（12件）
5. `tests/application/world_runtime/test_world_runtime_listen_presence.py`（1件）
6. `tests/application/llm/test_listen_carefully_tool.py`（3件）
7. `tests/infrastructure/repository/test_spot_atmosphere_codec_sound.py`（3件）
8. `tests/demos/test_world_runtime_speech_via_domain_event.py`（6件）

全リポジトリ試験、性能比較は実施していない。局所基準で製品不具合は再現しておらず、製品修正やIssueの作成は行っていない。

## 履歴と並行変更

- [環境音の受動観測導入](https://github.com/Motifman/llm-rpg/commit/e7c18fabf8d5d95498e14b7891da9cb3f935c868): 公開level、減衰下限、説明の有無、入場・移動での通知
- [能動的な聞き取り導入](https://github.com/Motifman/llm-rpg/commit/34a493ef836b1d8350a63c95a0b241bf5b45ffce): 自身と隣接、重複抑制、通行可否からの分離
- [通路別の減衰導入](https://github.com/Motifman/llm-rpg/commit/3bc43e60af7bb39b53da9b5854f11b4bf116b41b): 量子化境界、最良経路、壁と障壁の違い
- [隣室の気配導入](https://github.com/Motifman/llm-rpg/commit/3a10ff92bd130741e8b2d4a6a67f551033269594) と [部分件数の廃止](https://github.com/Motifman/llm-rpg/commit/0052287d0f5d6bd3897137d86fa95b000bbc2354): 人数/在否/判別不能と、遮音と非隣接を同じ沈黙へ潰さない判断
- [発話の方向情報](https://github.com/Motifman/llm-rpg/commit/25c7825ab9469bbe161891be94742b3d182e76e7): 受信直前の接続、同地点の方向なし、公開照会入口

2026-10-14 09:38 UTCに公開mainと未完了PR72件を確認した。所有試験5ファイルと製品所有者3ファイルへの変更パスの衝突は0。[配置 #1735](https://github.com/Motifman/llm-rpg/pull/1735) の規約を読み、共有規約は変更していない。[通路 #1736](https://github.com/Motifman/llm-rpg/pull/1736) はPassageの既定値・状態往復と接続索引、[経路 #1737](https://github.com/Motifman/llm-rpg/pull/1737) は通行可能な最短経路を扱う。今回の実聴覚・通行不可接続の利用とは別の契約を保っている。

## 全43宣言の判断

以下は基準時点の名前と位置。Rはその宣言を保持、Fは同じ宣言を補強、Cは上記主担当へ統合した。

### `tests/domain/world_graph/aggregate/test_spot_graph_listen_carefully.py`

| 基準宣言（行） | 判断 | 保護する契約・見える誤り |
| --- | --- | --- |
| `TestEmitListenCarefullySelfSpot.test_spot_moderate_event_trigger` (93) | R | 自地点MODERATEは減衰せず、聞き手地点/音源地点と説明を通知。自身にも隣接用減衰を適用、音源/説明の取り違え |
| `TestEmitListenCarefullySelfSpot.test_spot_silent_neighbor_does_not_trigger` (111) | R | 自地点SILENTかつ隣接なしでは環境音通知しない。SILENTの通知抑制を削除 |
| `TestEmitListenCarefullyAdjacent.test_loud_neighbor_moderate_trigger` (126) | R | 自地点SILENTでも開口隣接LOUDはMODERATE、別音源と説明を通知。隣接を見ない、減衰/聞き手地点/説明を誤る |
| `TestEmitListenCarefullyAdjacent.test_faint_neighbor_does_not_trigger` (146) | R | 開口隣接FAINTはSILENTへ減衰し通知しない。減衰前の強度で通知可否を判定 |
| `TestEmitListenCarefullyAdjacent.test_traversable_permeability` (159) | R | 通行不可BARRIERでも透過率1.0ならMODERATE→FAINTが届く。通行可能接続だけへ絞る |
| `TestEmitListenCarefullyDedup.test_same_spot_multiple_connection_one_dedup` (195) | R | 同じ隣接地点への同等接続を1通知へまとめる。接続単位で重複発火 |
| `TestEmitListenCarefullyCombined.test_spot_moderate_neighbor_two_event_trigger` (216) | R | 自身と2隣接の3通知を併存させ、各音源を別強度で伝える。最初の音源だけ発火、音源/聞き手を混同 |
| `TestEmitListenCarefullyErrors.test_entity_raises_exception` (244) | R | 未配置聞き手は固有例外。不在を無音として黙って通す |

### `tests/domain/world_graph/aggregate/test_spot_graph_sound_observation.py`

| 基準宣言（行） | 判断 | 保護する契約・見える誤り |
| --- | --- | --- |
| `TestPlaceEntitySilence.test_silent_spot_event_trigger` (65) | R | SILENT地点への初回配置は環境音通知なし。配置時に無音通知を作る |
| `TestPlaceEntityWithSound.test_moderate_spot_event_trigger_intensity_ambient_included` (79) | R | 初回配置で本人/現在地/音源/強度/説明を持つ通知を1件作る。配置の受動観測呼出を落とす、通知値を取り違える |
| `TestPlaceEntityWithSound.test_loud_spot_intensity_loud` (102) | R | 説明NoneのLOUD入場でも強度LOUDを通知。説明が無いと音源ごと抑制、強度を固定 |
| `TestMoveEntityWithSound.test_spot_sound_event_observation` (118) | R | 実接続移動後に到着地FAINTと説明を本人へ通知。move_entityの受動観測呼出が欠落 |

### `tests/domain/world_graph/aggregate/test_spot_graph_sound_permeability_attenuation.py`

| 基準宣言（行） | 判断 | 保護する契約・見える誤り |
| --- | --- | --- |
| `TestAdjacentMovingOccupants.test_presence_detail_follows_permeability` (119) | F | 隣接の行動可能者を透過率に応じ人数/在否不明へ縮約する。高透過率の人数を1に丸める故障は元表の0/1だけでは見えない |
| `TestAdjacentMovingOccupants.test_listener_and_current_spot_are_not_reported` (139) | F | 聞き手の現在地を隣接気配として返さない。自己接続除外を削っても元入力に自己接続が無い |
| `TestAdjacentMovingOccupants.test_non_adjacent_spot_is_not_reported` (155) | F | 非隣接Cを返さず、実在する隣接Bのゼロ人数通知は残す。遠隔人物しかいない場合に気配通知全体を落とすと元all([])が通る |
| `TestSoundPermeabilityToHops.test_returns_boundary_value_hops` (189) | R | 透過率0.7/0.4/0.1の両側と端点の量子化。境界演算子/閾値/量子化段数を誤る |
| `TestOpenPassage1Hop.test_open_loud_moderate` (199) | C | 開口隣接LOUD→MODERATEを1件返す。listen_carefullyのloud_neighborが同じ入力経路と強度/件数をさらに音源/説明つきで検査 |
| `TestOpenPassage1Hop.test_wall_broken_loud_moderate` (210) | R | BROKEN壁の既定透過率を実聴覚で1段減衰に反映。BROKEN壁の既定値や実配線を誤る |
| `TestOpenPassage1Hop.test_door_open_moderate_faint` (221) | R | OPEN扉の既定透過率を実聴覚で1段減衰に反映。OPEN扉を閉扉と同じ減衰にする |
| `TestClosedDoorAndCrackedWall2Hops.test_door_closed_loud_faint` (236) | R | CLOSED扉のLOUDをFAINTへ減衰。閉扉でも開口と同じ減衰にする |
| `TestClosedDoorAndCrackedWall2Hops.test_door_closed_moderate_silent_does_not_trigger` (247) | R | CLOSED扉のMODERATEは無音へ落ち通知なし。閉扉の追加減衰や無音抑制を落とす |
| `TestClosedDoorAndCrackedWall2Hops.test_wall_cracked_loud_faint` (256) | R | CRACKED壁のLOUDをFAINTへ減衰。ひび壁の既定透過率/適用を誤る |
| `TestIntactWall3Hops.test_wall_intact_loud_silent_does_not_trigger` (271) | R | INTACT壁ではLOUDすら無音へ落ちる。壁を通行可否と分離せず開口相当に扱う |
| `TestMultiConnectionPicksBestPath.test_one_hop` (285) | F | 複数接続から最小減衰を選び、環境音と気配を各1件へまとめる。最小値比較を無条件上書きへ変えても元の壁→扉順だけでは通る |
| `TestSelfSpotIgnoresPermeability.test_spot_self` (326) | R | FAINTの自身の音は周辺が壁でも減衰しない。周辺接続の減衰を自地点へ適用 |

### `tests/domain/world_graph/enum/test_sound_intensity_enum.py`

| 基準宣言（行） | 判断 | 保護する契約・見える誤り |
| --- | --- | --- |
| `TestLevelOrdering.test_level_value` (22) | R | 公開levelはSILENT/FAINT/MODERATE/LOUD=0/1/2/3。レベルのずれ/交換。導入時の整数単位契約 |
| `TestLevelOrdering.test_level_order` (29) | C | 公開levelの順序比較。値4つを独立定数で確かめるtest_level_valueが2つの不等式を含意 |
| `TestAttenuate.test_loud_1hop_moderate` (39) | R | LOUDの1段減衰はMODERATE。1段の計算誤り |
| `TestAttenuate.test_loud_2hop_faint` (46) | R | LOUDの2段減衰はFAINT。hopsを無視して常に1段だけ減衰 |
| `TestAttenuate.test_loud_3hop_silent` (50) | R | LOUDの3段減衰はSILENT。無音に達する等値境界誤り |
| `TestAttenuate.test_loud_4hop_silent` (54) | R | LOUDの4段減衰もSILENT以下へ落とさない。減衰下限のclampを落とす |
| `TestAttenuate.test_silent_hop_silent` (58) | R | 元からSILENTは5段でもSILENT。無音入力だけを非無音に変える |
| `TestAttenuate.test_hops_zero_less` (65) | R | 0と負のhopsは同じ強度のまま。ゼロ/負値を減衰へ適用 |
| `TestAttenuate.test_default_hops_is_one` (70) | R | hops省略時は1段減衰。公開API既定値を0や2へ変更 |

### `tests/domain/world_graph/test_sound_propagation_service.py`

| 基準宣言（行） | 判断 | 保護する契約・見える誤り |
| --- | --- | --- |
| `TestSoundPropagationService.test_whisper_only_same_spot` (50) | R | WHISPERは話者地点だけへ届く。音量の最大距離を無視し隣へ送る |
| `TestSoundPropagationService.test_normal_reaches_neighbor_muffled` (62) | R | NORMALは本人CLEAR、透過率0.5隣接MUFFLED。0/1距離の明瞭さを混同 |
| `TestSoundPropagationService.test_normal_neighbor_low_perm_is_faint` (75) | R | NORMALの透過率0.2隣接はFAINT。隣接明瞭さの透過率分岐を削る |
| `TestSoundPropagationService.test_clarity_for_listener` (87) | R | 公開clarity_for_listenerは対象の明瞭さを返す。ラッパーが対象や戻り値を誤る。現非試験呼出0でも#269で互換入口維持と明記 |
| `TestSoundPropagationService.test_recipient_carries_first_hop_connection_name_for_neighbor` (103) | R | 隣接受信者は到来した接続名と話者地点を持つ。到来方向の値を落とす |
| `TestSoundPropagationService.test_speaker_self_has_no_source_direction` (117) | R | 同地点の話者は到来方向を持たない。全受信者へ方向を付ける |
| `TestSoundPropagationService.test_two_hop_listener_uses_last_hop_connection` (128) | R | SHOUTの2辺先は最初の辺でなく受信直前の辺/地点を返す。方向を最初の辺へ固定 |
| `TestSoundPropagationService.test_outcome_for_listener_returns_recipient_or_none` (145) | R | outcome_for_listenerは対象の方向付き結果、届かないWHISPERはNone。対象抽出の誤り/届かない時に話者結果を返す |
| `TestSoundPropagationService.test_iter_outgoing_used_for_sound` (172) | R | LOCKED扉でも透過率0.6で発話は隣接へ届く。発話伝播を通行可能接続だけへ絞る |
