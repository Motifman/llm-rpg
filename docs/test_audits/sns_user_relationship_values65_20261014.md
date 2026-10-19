# SNSプロフィール・関係値65宣言の試験監査

## なぜ
関係の値試験には、UserIdの検証を重ねる宣言、判定のない不変性、異値のハッシュ衝突を不当に禁止するassertがあった。値の所有者に確認を集め、元の入力と観測を残して失敗の意味を明確にする。

## 範囲と固定元
親PR #1774 のcommit `595065d2d35f3bcb8f6a93ecc5259a5c7252599e`、tree `6cebbad5e2aee251cb404735668c477b2414e300` が基準。ローカルでは同じ3,459 leafのmode/type/blobを照合した再構成commit `f46764e4cb28f98af6843d2ce2c2a6d501f9b5e9` を使用した。ローカルcommitそのものをremote commitと同一とは扱わない。
数値ID54の親6ファイル、投稿内容49の兄弟4試験、製品実装、共有補助は変更しない。対象は以下の4試験だけで、この監査文書を追加する。

- `tests/domain/sns/test_block_relationship.py`: 16→10宣言、193→127行
- `tests/domain/sns/test_follow_relationship.py`: 17→10宣言、215→124行
- `tests/domain/sns/test_subscribe_relationship.py`: 18→10宣言、226→124行
- `tests/domain/sns/test_user_profile.py`: 14→13宣言、143→135行

## 判断と保持する契約
- 元65宣言の分類はR30 / F13 / C13 / D9。統合13・削除9の後は43宣言。表の各行を展開した実行件数とは区別する
- 135個の元assertと14個のraisesを照合。不変性3宣言には元々assertがない
- 同じ時刻と異なる時刻の等価性、同値のhash一致、片側IDだけの違い、自己関係拒否を保持する
- 両ID/created_atへの通常再代入はAttributeErrorで拒否され、全3値が維持される。dataclass固有例外型・深いコピー・迂回手段への耐性は新仕様にしない
- Follow/Subscribeの1→100と100→1は、両属性保持と対象/実行者のqueryをともに移管する
- 123/456のstr/int4観測は関係構築の独立期待値に移す。UserId親試験だけでは456入力を代替できない
- プロフィールの全3値同時差分を残し、1欄ずつ違う条件を加える。bio更新では元のbioとbioの両入力、および!=/is notを保持する
- UserId(0)6宣言は関係値を構築していない。同じ入力をUserId所有者の狭いドメイン例外試験が守る
- 3件の生成repr試験は、独立した表示仕様・利用者を履歴と本番呼出元から見出せなかったため退役する。保存往復試験で同じreprを証明したという意味ではない
- 異値のhash不等要求7箇所だけを外し、非等価と集合への共存を観測する。hash衝突は許される

## 実行した検証
- 元の対象: 65成功。関連SNS・アプリ・SQLite/公開SNS保存: 886成功（対象65を含む）
- 元65宣言を残した保持先先行移管: 88成功
- 統合後: 対象66成功、関連887成功（対象を含む）。失敗・skipなし
- 69変異、旧新版計138実行。保存59、改善8、合法hash衝突対照1、repr退役対照1。検知する契約と旧新版の結果を確認した
- 変異では旧対象65＋既存UserId拒否keeper1=66条件、新対象66＋同keeper1=67条件を実行。親ファイルへの変異は専用対照作業木だけで行い、毎回元のバイト列に復元した
- 不変性と構築時刻の固定化、プロフィールのuser_name/display_name比較欄の脱落は旧試験が通り、新保持先が失敗する。移管した999999/123/456、逆向きの両属性/queryは旧新とも失敗する
- bio比較の脱落1件は当初改善と想定したが、旧の更新後!=も既に検知したため、保持の証明へ分類を訂正した。元実行記録は変更せず、旧C宣言から新update_bioへの移管を確認した
- 合法な定数hashは旧7観測が失敗し、新は成功。生成reprの変更は旧3観測が失敗し、新は成功。この差は意図した退役範囲
- Python 3.10.22、専用オフライン実行器、network_block、各作業木自身のsrc、固有出力/cache/TMPDIRで実行。実API・LLM・SNSへの接続なし
- ruff 0.16.8、git diff --checkを最終候補に実行した
- 試験差分は173追加/440削除、純減267行。製品と試験補助の変更0行

## 関連未マージ修正と独立性
確認時点の#1456（0c9bb151）、#1457（149fb985）、#1458（df349343）、#1462（cf04a37c）はDraft未マージ、対象4所有者/4試験とファイル重複なし。#1456は関係リストを浅くコピーする案で、現行の集約propertyは元リストを返す。値要素の不変性とは別の契約であり、本変更は深いコピーを要求しない。参照寿命・返信ページ件数・公開範囲による配送制御もこの値試験では代替しない。

## 限界
全リポジトリ試験、公開commitのCI、実LLM/実SNS、製品の問題修正は行っていない。対象65を超える試験を監査済みとして加算しない。ローカル関連試験の成功と公開CI成功は区別する。実行時間短縮や削除数自体を成果目標にはしない。

## 元65宣言の全台帳
R=保持、F=契約を保持して観測を修理、C=保持先へ先行移管して統合、D=重複または独立契約のない観測を退役。

### R: `tests/domain/sns/test_block_relationship.py::test_create_block_relationship_success`
方向付き2者のIDを区別して保持し時刻を自動生成
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_create_block_relationship_success`
現契約を保持する

### R: `tests/domain/sns/test_block_relationship.py::test_create_block_relationship_with_explicit_datetime`
方向付き2者と指定作成時刻を保持
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_create_block_relationship_with_explicit_datetime`
現契約を保持する

### D: `tests/domain/sns/test_block_relationship.py::test_invalid_blocker_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### D: `tests/domain/sns/test_block_relationship.py::test_invalid_blocked_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### R: `tests/domain/sns/test_block_relationship.py::test_self_block_raises_error`
同じ値の2者関係をSelfReferenceValidationExceptionで拒む
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_self_block_raises_error`
現契約を保持する

### C: `tests/domain/sns/test_block_relationship.py::test_boundary_user_id_values`
各位置の最小/大きいIDを維持する
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_create_block_relationship_success`
構築表の(1,2),(999999,2),(1,999999)へ両属性の期待値を保持。最小/大きな値を各位置で確認する。

### R: `tests/domain/sns/test_block_relationship.py::test_is_blocked_method`
対象だけにTrue、実行者と第三者にFalseを返す
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_is_blocked_method`
現契約を保持する

### R: `tests/domain/sns/test_block_relationship.py::test_equality_comparison`
同じ方向の2者は別個体でも等しく同じhash
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_equality_comparison`
現契約を保持する

### F: `tests/domain/sns/test_block_relationship.py::test_inequality_with_different_blocker_ids`
blocker側だけ異なる関係を区別
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_inequality_with_different_blocker_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### F: `tests/domain/sns/test_block_relationship.py::test_inequality_with_different_blocked_ids`
blocked側だけ異なる関係を区別
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_inequality_with_different_blocked_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### R: `tests/domain/sns/test_block_relationship.py::test_hash_with_different_creation_times`
時刻が異なっても同じ方向の関係は等しく同じhash
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_hash_with_different_creation_times`
現契約を保持する

### C: `tests/domain/sns/test_block_relationship.py::test_hash_with_same_creation_time`
同時刻の同じ2者の等価/hash一致
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_equality_comparison`
保持先が同じ同時刻条件を既に持つことを確認する

### F: `tests/domain/sns/test_block_relationship.py::test_immutability`
両IDとcreated_atを構築後に再代入できない
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_immutability`
両IDとcreated_atの3属性を通常のsetattrで変更し、AttributeErrorで拒否（dataclass固有の例外型には固定しない）され元の全3値を保持することを表で検査。元試験はassert 0。deepcopy・内部object.__setattr__迂回耐性など新仕様は固定しない。

### D: `tests/domain/sns/test_block_relationship.py::test_string_representation`
自動生成された診断表示にクラス名とIDの数字を含むという実装形
保持先: なし。生成診断表示の観測を意図して退役する。
独立した表示仕様を見出せないためこのassert自体を退役する。値保持/保存試験で代替したとは扱わない。

### F: `tests/domain/sns/test_block_relationship.py::test_created_at_auto_generation`
省略作成時刻を構築時に生成する
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_created_at_auto_generation`
構築直前beforeと直後afterでbefore<=created_at<=afterを確認し、現在時刻の1秒許容による不安定さを除く。同じ試験内で2回構築し各回を挟み、import時固定や前回の再利用を捕まえる。sleepや製品の時刻注入入口を増やさない。

### C: `tests/domain/sns/test_block_relationship.py::test_id_string_conversion`
実行者123/対象456を区別して保持
保持先: `tests/domain/sns/test_block_relationship.py::TestBlockRelationShip::test_create_block_relationship_success`
123/456の独立期待値を含む構築表を先に追加し、両属性の型付き値保持に加えstrが"123"/"456"、intが123/456の4原assertを同じ保持先へ移す。親のUserId試験は456を持たないため代替とは数えず変更しない。

### R: `tests/domain/sns/test_follow_relationship.py::test_create_follow_relationship_success`
方向付き2者のIDを区別して保持し時刻を自動生成
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_create_follow_relationship_success`
現契約を保持する

### R: `tests/domain/sns/test_follow_relationship.py::test_create_follow_relationship_with_explicit_datetime`
方向付き2者と指定作成時刻を保持
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_create_follow_relationship_with_explicit_datetime`
現契約を保持する

### D: `tests/domain/sns/test_follow_relationship.py::test_invalid_follower_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### D: `tests/domain/sns/test_follow_relationship.py::test_invalid_followee_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### R: `tests/domain/sns/test_follow_relationship.py::test_self_follow_raises_error`
同じ値の2者関係をSelfReferenceValidationExceptionで拒む
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_self_follow_raises_error`
現契約を保持する

### C: `tests/domain/sns/test_follow_relationship.py::test_boundary_user_id_values`
各位置の最小/大きいIDを維持する
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_create_follow_relationship_success`
構築表の(1,2),(999999,2),(1,999999)へ両属性の期待値を保持。最小/大きな値を各位置で確認する。

### R: `tests/domain/sns/test_follow_relationship.py::test_is_following_method`
対象だけにTrue、実行者と第三者にFalseを返す
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_is_following_method`
現契約を保持する

### R: `tests/domain/sns/test_follow_relationship.py::test_equality_comparison`
同じ方向の2者は別個体でも等しく同じhash
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_equality_comparison`
現契約を保持する

### F: `tests/domain/sns/test_follow_relationship.py::test_inequality_with_different_follower_ids`
follower側だけ異なる関係を区別
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_inequality_with_different_follower_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### F: `tests/domain/sns/test_follow_relationship.py::test_inequality_with_different_followee_ids`
followee側だけ異なる関係を区別
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_inequality_with_different_followee_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### R: `tests/domain/sns/test_follow_relationship.py::test_hash_with_different_creation_times`
時刻が異なっても同じ方向の関係は等しく同じhash
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_hash_with_different_creation_times`
現契約を保持する

### C: `tests/domain/sns/test_follow_relationship.py::test_hash_with_same_creation_time`
同時刻の同じ2者の等価/hash一致
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_equality_comparison`
保持先が同じ同時刻条件を既に持つことを確認する

### F: `tests/domain/sns/test_follow_relationship.py::test_immutability`
両IDとcreated_atを構築後に再代入できない
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_immutability`
両IDとcreated_atの3属性を通常のsetattrで変更し、AttributeErrorで拒否（dataclass固有の例外型には固定しない）され元の全3値を保持することを表で検査。元試験はassert 0。deepcopy・内部object.__setattr__迂回耐性など新仕様は固定しない。

### D: `tests/domain/sns/test_follow_relationship.py::test_string_representation`
自動生成された診断表示にクラス名とIDの数字を含むという実装形
保持先: なし。生成診断表示の観測を意図して退役する。
独立した表示仕様を見出せないためこのassert自体を退役する。値保持/保存試験で代替したとは扱わない。

### F: `tests/domain/sns/test_follow_relationship.py::test_created_at_auto_generation`
省略作成時刻を構築時に生成する
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_created_at_auto_generation`
構築直前beforeと直後afterでbefore<=created_at<=afterを確認し、現在時刻の1秒許容による不安定さを除く。同じ試験内で2回構築し各回を挟み、import時固定や前回の再利用を捕まえる。sleepや製品の時刻注入入口を増やさない。

### C: `tests/domain/sns/test_follow_relationship.py::test_different_follower_followee_combinations`
ID大小を逆にしても向きの意味が同じ
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_is_following_method`
is_following/is_subscribedの表に(1,100)/(100,1)を追加し、各行で両属性の保持assertと対象True/実行者Falseを先に移す。第三者Falseも保持。queryだけへ移して元の属性assertを失わない。

### C: `tests/domain/sns/test_follow_relationship.py::test_id_string_conversion`
実行者123/対象456を区別して保持
保持先: `tests/domain/sns/test_follow_relationship.py::TestFollowRelationShip::test_create_follow_relationship_success`
123/456の独立期待値を含む構築表を先に追加し、両属性の型付き値保持に加えstrが"123"/"456"、intが123/456の4原assertを同じ保持先へ移す。親のUserId試験は456を持たないため代替とは数えず変更しない。

### R: `tests/domain/sns/test_subscribe_relationship.py::test_create_subscribe_relationship_success`
方向付き2者のIDを区別して保持し時刻を自動生成
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_create_subscribe_relationship_success`
現契約を保持する

### R: `tests/domain/sns/test_subscribe_relationship.py::test_create_subscribe_relationship_with_explicit_datetime`
方向付き2者と指定作成時刻を保持
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_create_subscribe_relationship_with_explicit_datetime`
現契約を保持する

### D: `tests/domain/sns/test_subscribe_relationship.py::test_invalid_subscriber_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### D: `tests/domain/sns/test_subscribe_relationship.py::test_invalid_subscribed_user_id_raises_error`
UserId(0)だけを構築し関係値に到達しない
保持先: `tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error`
UserIdの狭い例外型による同条件を保持。原始IDの重複検査のみ削除する

### R: `tests/domain/sns/test_subscribe_relationship.py::test_self_subscribe_raises_error`
同じ値の2者関係をSelfReferenceValidationExceptionで拒む
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_self_subscribe_raises_error`
現契約を保持する

### C: `tests/domain/sns/test_subscribe_relationship.py::test_boundary_user_id_values`
各位置の最小/大きいIDを維持する
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_create_subscribe_relationship_success`
構築表の(1,2),(999999,2),(1,999999)へ両属性の期待値を保持。最小/大きな値を各位置で確認する。

### R: `tests/domain/sns/test_subscribe_relationship.py::test_is_subscribed_method`
対象だけにTrue、実行者と第三者にFalseを返す
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_is_subscribed_method`
現契約を保持する

### R: `tests/domain/sns/test_subscribe_relationship.py::test_equality_comparison`
同じ方向の2者は別個体でも等しく同じhash
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_equality_comparison`
現契約を保持する

### F: `tests/domain/sns/test_subscribe_relationship.py::test_inequality_with_different_subscriber_ids`
subscriber側だけ異なる関係を区別
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_inequality_with_different_subscriber_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### F: `tests/domain/sns/test_subscribe_relationship.py::test_inequality_with_different_subscribed_ids`
subscribed側だけ異なる関係を区別
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_inequality_with_different_subscribed_ids`
元の両組合せを保ち、両者に同じ明示時刻を渡して片側IDの違いだけを比較。非等価を保持しlen({left,right})==2を確認。hash不等要求のみ外す。

### R: `tests/domain/sns/test_subscribe_relationship.py::test_hash_with_different_creation_times`
時刻が異なっても同じ方向の関係は等しく同じhash
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_hash_with_different_creation_times`
現契約を保持する

### C: `tests/domain/sns/test_subscribe_relationship.py::test_hash_with_same_creation_time`
同時刻の同じ2者の等価/hash一致
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_equality_comparison`
保持先が同じ同時刻条件を既に持つことを確認する

### F: `tests/domain/sns/test_subscribe_relationship.py::test_immutability`
両IDとcreated_atを構築後に再代入できない
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_immutability`
両IDとcreated_atの3属性を通常のsetattrで変更し、AttributeErrorで拒否（dataclass固有の例外型には固定しない）され元の全3値を保持することを表で検査。元試験はassert 0。deepcopy・内部object.__setattr__迂回耐性など新仕様は固定しない。

### D: `tests/domain/sns/test_subscribe_relationship.py::test_string_representation`
自動生成された診断表示にクラス名とIDの数字を含むという実装形
保持先: なし。生成診断表示の観測を意図して退役する。
独立した表示仕様を見出せないためこのassert自体を退役する。値保持/保存試験で代替したとは扱わない。

### F: `tests/domain/sns/test_subscribe_relationship.py::test_created_at_auto_generation`
省略作成時刻を構築時に生成する
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_created_at_auto_generation`
構築直前beforeと直後afterでbefore<=created_at<=afterを確認し、現在時刻の1秒許容による不安定さを除く。同じ試験内で2回構築し各回を挟み、import時固定や前回の再利用を捕まえる。sleepや製品の時刻注入入口を増やさない。

### C: `tests/domain/sns/test_subscribe_relationship.py::test_different_subscriber_subscribed_combinations`
ID大小を逆にしても向きの意味が同じ
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_is_subscribed_method`
is_following/is_subscribedの表に(1,100)/(100,1)を追加し、各行で両属性の保持assertと対象True/実行者Falseを先に移す。第三者Falseも保持。queryだけへ移して元の属性assertを失わない。

### C: `tests/domain/sns/test_subscribe_relationship.py::test_subscription_vs_following_difference`
実際にはSubscribeの2者保持とis_subscribedのみ。Followとの比較はない
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_is_subscribed_method`
元入力(1,2)の両属性assertと対象Trueをis_subscribedの(1,2)行に先行保持。Followとの非等価は元々試していないため証明として追加計上しない。

### C: `tests/domain/sns/test_subscribe_relationship.py::test_id_string_conversion`
実行者123/対象456を区別して保持
保持先: `tests/domain/sns/test_subscribe_relationship.py::TestSubscribeRelationShip::test_create_subscribe_relationship_success`
123/456の独立期待値を含む構築表を先に追加し、両属性の型付き値保持に加えstrが"123"/"456"、intが123/456の4原assertを同じ保持先へ移す。親のUserId試験は456を持たないため代替とは数えず変更しない。

### R: `tests/domain/sns/test_user_profile.py::test_create_user_profile_success`
アカウント名・表示名・bioを区別して保持
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_create_user_profile_success`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_user_name_too_short_raises_error`
2文字のアカウント名をUserNameValidationExceptionで拒む
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_user_name_too_short_raises_error`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_user_name_too_long_raises_error`
21文字のアカウント名を同例外で拒む
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_user_name_too_long_raises_error`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_display_name_too_short_raises_error`
空表示名をDisplayNameValidationExceptionで拒む
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_display_name_too_short_raises_error`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_display_name_too_long_raises_error`
31文字表示名を同例外で拒む
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_display_name_too_long_raises_error`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_bio_too_long_raises_error`
201文字bioをBioValidationExceptionで拒む
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_bio_too_long_raises_error`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_boundary_user_name_length`
3文字と20文字のアカウント名を保持
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_boundary_user_name_length`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_boundary_display_name_length`
1文字と30文字の表示名を保持
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_boundary_display_name_length`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_boundary_bio_length`
空bioと200文字bioを受容する
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_boundary_bio_length`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_update_bio_returns_new_instance`
bio更新は他の2値と元のbioを維持する
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_update_bio_returns_new_instance`
現契約を保持する

### R: `tests/domain/sns/test_user_profile.py::test_update_display_name_returns_new_instance`
表示名更新は他の2値と元の表示名を維持する
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_update_display_name_returns_new_instance`
現契約を保持する

### C: `tests/domain/sns/test_user_profile.py::test_immutability_after_update`
bio変更の結果は元と異なる個体/値
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_update_bio_returns_new_instance`
元入力(testuser,表示名,bio)と更新後bio=新しいbioを保持した行をupdate_bio試験へ追加し、元の!=とis notを先に移す。既存の元のbio→新しいbio行も維持。属性代入拒否を証明したとは扱わない。

### R: `tests/domain/sns/test_user_profile.py::test_equality_comparison`
同じ3値の個体を等しく同じhashにする
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_equality_comparison`
現契約を保持する

### F: `tests/domain/sns/test_user_profile.py::test_inequality_comparison`
アカウント名・表示名・bioを個別に等価性へ反映
保持先: `tests/domain/sns/test_user_profile.py::TestUserProfile::test_inequality_comparison`
元の(testuser1,表示名1,bio1)対(testuser2,表示名2,bio2)を必ず維持し、user_nameのみ/display_nameのみ/bioのみ異なる3行を追加。各行で非等価とlen({left,right})==2。hash不等要求だけ外す。

## 履歴と参照
- d25af3295dd67160d1a68105558ff902a5386b4c: 値試験の一括追加。独立した関係表示仕様の導入はない
- 822a5b69418a37537a93702f4cfdbfc262568cd3: DDD構造とUserIdへの移行。現在の負例は関係型へ到達しない
- 値の本番所有者: domain/sns/value_objectのblock/follow/subscribe/user_profile
- 呼出元: UserAggregate、SnsUser、InMemoryDataStore、sqlite_sns_state_codec、user_query_service
- 保存はpublic_sns_snapshot_codec/sqlite_sns_state_codecのID欄とisoformat時刻、表示はDTOの個別欄で行う
