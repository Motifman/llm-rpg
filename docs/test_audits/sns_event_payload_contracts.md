# SNSイベントの公開値・発生情報の試験監査

## なぜ

人物が違うイベントの試験11件は、人物を取り違えても別event_idだけで非等価になり成功していた。同じ内容を二回生成する試験7件は、時刻が必ず違うという時計の分解能に依存する条件を要求していた。生成値は外側の通知・観測が使う公開契約なので残し、独立した期待値と各回のUTC生成区間で検査する。

元の全入力と118観測（assert116個、AttributeError拒否2個）を対応付け、保持先を先に追加した75条件が成功してから、原宣言をまとめた。以下は全38宣言の判断であり、削除数を監査完了数として足していない。

## 範囲と固定点

- 対象: `tests/domain/sns/event/test_sns_events.py` の元38宣言
- 親: [#1779](https://github.com/Motifman/llm-rpg/pull/1779)、`6b5c7c4c1174a870f631e16026ce10c1d689b2e0`
- 親tree: `890bc48b4a5695b296a29adf6f3426e18187f3ca`。3460追跡ファイルのmodeとGit blobを照合して検証した
- main確認: `7c7dc63c5f4be701832a3f1443e27682fe9869d1`（2026-10-14）
- 試験: 787行→619行、168行減。38宣言→4宣言、38実行条件→37実行条件
- 製品・共有補助・親PRの4試験と監査文書・AGENTSの変更0。新しい製品注入口や公開API撤去0

## 保持する境界

イベントはUserAggregate・PostAggregate・ReplyAggregate・BaseSnsContentAggregateから作られ、旧通知、関係解除、SNS観測、公開通知adapterに渡る。人物・本文・親・任意欄は公開生成境界の意味であり、dataclassであることだけを理由に削除しない。検査する公開属性だけを明示し、内部属性一覧や全dataclass比較は固定しない。

DomainEventCollectorはevent_idで同じイベントの二重収集を除く。公開通知adapterはevent_id/occurred_atを引き継ぎ、dispatcherはsource_event_id・recipient_token・kindで既存通知を確認する。全payload比較へ業務同一性を変える根拠はない。UUID版ビット、IDの単調増加、時刻同士の必ず異なる保証は追加していない。

UTCは[#311の実回帰](https://github.com/Motifman/llm-rpg/commit/ca3d161361a0364c831353a65400940b9f885d88)を保持する。各createの直前/直後UTC時刻で挟み、datetime型・tzinfo・UTC offsetゼロを検査する。同じ時計値でも通る非厳密比較を使う。共通イベントのoccurred_tick試験だけを代替証拠とは扱わない。

## 保持先

- A: `test_event_payload_fields`、17行。生成14＋種類2宣言の計17生成。元の日本語と`test`文字列、非空集合、片側None、親ID、省略入力を別行で保持
- B: `test_changed_people_are_preserved`、11行。元の(1,2)/(3,2)または(1,2)/(1,4)を双方の独立UserId期待値で検査
- C: `test_repeated_events_keep_payload_and_fresh_metadata`、7行。両方の公開値、別整数ID、各回の現在UTCを独立期待値で検査
- D: `test_event_reassignment_is_rejected`、2行。元の通常代入拒否に加え、拒否後も元値が残ることを検査

PostCreatedのmentionsとMentionedの名前集合は入力集合をそのまま期待値に使わない。生成途中に集合を空にしても、旧試験では共有された期待値まで空になって成功していた。新しい独立集合期待値は両方を検知する。深い集合不変性や呼出元の集合コピーを新仕様として要求するものではない。

## 全38宣言の台帳

Rは独立契約の保持、Fは契約を残して観測を修理、Cは保持先へ先行移管して統合、Dは契約を持たない削除。実際の分類は **R1 / F20 / C17 / D0**。

| 元宣言（固定版） | 判断 | 実際に守るもの・修理 | 保持先と行 |
|---|---|---|---|
| [`TestSnsUserCreatedEvent::test_create_user_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L30-L48) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_user_event_success` |
| [`TestSnsUserCreatedEvent::test_user_event_immutability`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L50-L63) | F | 元の通常属性代入とAttributeErrorを保持し、拒否後に元の属性値が変わっていないことを明示値で確認。set内部まで凍結する仕様は追加しない。 | D: `user_event_immutability` |
| [`TestSnsUserFollowedEvent::test_create_followed_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L69-L81) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_followed_event_success` |
| [`TestSnsUserFollowedEvent::test_followed_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L83-L106) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `followed_event` |
| [`TestSnsUserFollowedEvent::test_followed_event_inequality_with_different_follower`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L108-L124) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `followed_event_inequality_with_different_follower` |
| [`TestSnsUserProfileUpdatedEvent::test_create_profile_updated_event_with_both_fields`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L130-L142) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_profile_updated_event_with_both_fields` |
| [`TestSnsUserProfileUpdatedEvent::test_create_profile_updated_event_with_only_bio`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L144-L155) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_profile_updated_event_with_only_bio` |
| [`TestSnsPostCreatedEvent::test_create_post_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L161-L179) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_post_event_success` |
| [`TestSnsReplyCreatedEvent::test_create_reply_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L185-L204) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_reply_event_success` |
| [`TestSnsContentLikedEvent::test_create_like_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L210-L226) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_like_event_success` |
| [`TestSnsContentLikedEvent::test_like_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L228-L257) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `like_event` |
| [`TestSnsContentDeletedEvent::test_create_delete_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L263-L277) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_delete_event_success` |
| [`TestSnsContentMentionedEvent::test_create_mentioned_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L283-L300) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_mentioned_event_success` |
| [`TestEventBaseFunctionality::test_all_events_have_unique_ids`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L306-L323) | R | 同一Followed入力の2回生成で別整数IDという元契約をfollowed_event行へ移動・拡張する。新しいUUID版指定・単調増加・一定長は追加しない。 | C: `followed_event` |
| [`TestEventBaseFunctionality::test_all_events_have_current_timestamp`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L325-L340) | C | #311の実回帰をfollowed_event行へ先行移管。元UserId(1)/(2)・UserAggregateを保持。tzinfo非Noneと±1秒窓より狭い各生成区間、offsetゼロを検査。独立宣言は退役するがUTC契約を残す。 | C: `followed_event` |
| [`TestEventBaseFunctionality::test_event_immutability`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L342-L353) | F | 元の通常属性代入とAttributeErrorを保持し、拒否後に元の属性値が変わっていないことを明示値で確認。set内部まで凍結する仕様は追加しない。 | D: `event_immutability` |
| [`TestEventTypeValidation::test_user_events_have_correct_aggregate_type`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L359-L370) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `user_events_have_correct_aggregate_type` |
| [`TestEventTypeValidation::test_content_events_have_correct_aggregate_type`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L372-L392) | C | 元の全create引数・省略を維持した2行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `content_events_have_correct_aggregate_type-1`, `content_events_have_correct_aggregate_type-2` |
| [`TestSnsUserUnfollowedEvent::test_create_unfollowed_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L398-L410) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_unfollowed_event_success` |
| [`TestSnsUserUnfollowedEvent::test_unfollowed_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L412-L435) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `unfollowed_event` |
| [`TestSnsUserUnfollowedEvent::test_unfollowed_event_inequality_with_different_follower`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L437-L453) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unfollowed_event_inequality_with_different_follower` |
| [`TestSnsUserUnfollowedEvent::test_unfollowed_event_inequality_with_different_followee`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L455-L471) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unfollowed_event_inequality_with_different_followee` |
| [`TestSnsUserBlockedEvent::test_create_blocked_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L477-L489) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_blocked_event_success` |
| [`TestSnsUserBlockedEvent::test_blocked_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L491-L514) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `blocked_event` |
| [`TestSnsUserBlockedEvent::test_blocked_event_inequality_with_different_blocker`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L516-L532) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `blocked_event_inequality_with_different_blocker` |
| [`TestSnsUserBlockedEvent::test_blocked_event_inequality_with_different_blocked`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L534-L550) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `blocked_event_inequality_with_different_blocked` |
| [`TestSnsUserUnblockedEvent::test_create_unblocked_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L556-L568) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_unblocked_event_success` |
| [`TestSnsUserUnblockedEvent::test_unblocked_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L570-L593) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `unblocked_event` |
| [`TestSnsUserUnblockedEvent::test_unblocked_event_inequality_with_different_blocker`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L595-L611) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unblocked_event_inequality_with_different_blocker` |
| [`TestSnsUserUnblockedEvent::test_unblocked_event_inequality_with_different_blocked`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L613-L629) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unblocked_event_inequality_with_different_blocked` |
| [`TestSnsUserSubscribedEvent::test_create_subscribed_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L635-L647) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_subscribed_event_success` |
| [`TestSnsUserSubscribedEvent::test_subscribed_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L649-L672) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `subscribed_event` |
| [`TestSnsUserSubscribedEvent::test_subscribed_event_inequality_with_different_subscriber`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L674-L690) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `subscribed_event_inequality_with_different_subscriber` |
| [`TestSnsUserSubscribedEvent::test_subscribed_event_inequality_with_different_subscribed`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L692-L708) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `subscribed_event_inequality_with_different_subscribed` |
| [`TestSnsUserUnsubscribedEvent::test_create_unsubscribed_event_success`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L714-L726) | C | 元の全create引数・省略を維持した1行へ移管。公開属性は独立した値で比較し、元のevent_id整数/非None、datetime型も共通assertで保持。 | A: `create_unsubscribed_event_success` |
| [`TestSnsUserUnsubscribedEvent::test_unsubscribed_event_business_equality`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L728-L751) | F | 元の2回の同一入力を維持。元の相互payload比較を双方の独立期待値に置換。ID非等価を保持し、時刻非等価だけを各回の現在UTC区間へ修理。 | C: `unsubscribed_event` |
| [`TestSnsUserUnsubscribedEvent::test_unsubscribed_event_inequality_with_different_subscriber`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L753-L769) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unsubscribed_event_inequality_with_different_subscriber` |
| [`TestSnsUserUnsubscribedEvent::test_unsubscribed_event_inequality_with_different_subscribed`](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/event/test_sns_events.py#L771-L787) | F | 元の2入力を残す。人物の変化側だけでなく不変側も、両イベントについて独立UserId期待値へ比較する。aggregate_id=UserId(1)も元どおり維持。 | B: `unsubscribed_event_inequality_with_different_subscribed` |

旧`test_all_events_have_current_timestamp`はCだが、UTC契約を削除していない。元Followed入力をCの`followed_event`行に移し、#311のnaive時刻を旧新対照で確認した。元の±1秒窓より狭い各生成区間を守る。旧7件のoccurred_at非等価だけは、同じ時刻でも発行できることを確認して退役した。

## 他の試験と並行変更

UserAggregateの発行試験は人物等を守るが、投稿・返信の外側試験には型名や存在だけの検査もある。今回の公開factoryへの直接入力、省略、別人物、拒否後元値、ID/UTCの全てを代替しない。外側の重複して見える試験32シナリオを読み、編集せず関連試験として実行した。

公開経路の`test_replayed_event_cannot_duplicate_notification`と`test_domain_follow_and_like_events_create_incoming_notifications`は再投入の一件化を守る。通知メタデータ保存はmemory/sqliteで不変ID、source_event_id、全文、出典、配送済み状態を守る。旧配送と新しい公開配送の宛先・件数の規則は統一しない。

次のDraft4本は2026-10-14にheadと全差分を再確認し、初回調査から変更なしだった。この監査との複合適用試験ではない。

| PR | head | この変更との関係 |
|---|---|---|
| [#1456](https://github.com/Motifman/llm-rpg/pull/1456) | `0c9bb151ede4b9fae3b463d0333c80dc18ff5ca7` | 集約の入力集合・取得リストのコピー。イベント所有者は不変更 |
| [#1457](https://github.com/Motifman/llm-rpg/pull/1457) | `149fb985600eee3180bca2e5afe31492a988529a` | 画面参照の通番/名前空間。event_idの同一性とは別 |
| [#1458](https://github.com/Motifman/llm-rpg/pull/1458) | `df349343c1c8722f153c251b40aa343ab3197056` | 投稿詳細の返信ページング。生成値契約とは別 |
| [#1462](https://github.com/Motifman/llm-rpg/pull/1462) | `cf04a37c32e6b1989269e2d4241a9a9914eed7e9` | 旧受信入口のPRIVATE本文抑止。イベント型/保存形式は不変更 |

## 実施済み検証

- Python3.10.22、既存の固定依存、外部接続遮断、専用srcの読込みを確認。cache/TMPDIRは作業系統ごとに固有化し、各試行の出力名は新規作成
- 未編集対象38件・関連883件成功
- 原38＋保持先37の併存75件成功後に統合
- 最終対象37件・関連882件成功。関連は対象を含み、未変更の845件も成功
- 編集前の独立第二読と、実差分・原入力・全対照・復元を調べた独立最終保持審査は合格
- 変更1試験ファイルのruff 0.16.8、git diff --check成功
- 全製品1587ファイルのmode/blobを元commitと照合し、製品差分0

関連範囲はSNS domain/social、共通イベント/collector、SNS観測の宛先/文面、通知メタデータ、SQLite通知、公開snapshot、識別子保存である。

## 対照変異の全結果

70種を旧38/新37へ同じ条件で当て、計140実行。修理16種は旧が見逃し新が検知、保持53種は旧新とも検知、合法な同一時計1種は旧の時刻非等価7件だけが失敗し新が成功した。各回に製品bytesを戻し照合した。収集・準備時の例外による偽の赤はない。

| 変異 | 種別・意味 | 旧成功/失敗 | 新成功/失敗 |
|---|---|---:|---:|
| `people-followed-follower` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unfollowed-follower` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unfollowed-followee` | 修理: 元4を2へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-blocked-blocker` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-blocked-blocked` | 修理: 元4を2へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unblocked-blocker` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unblocked-blocked` | 修理: 元4を2へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-subscribed-subscriber` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-subscribed-subscribed` | 修理: 元4を2へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unsubscribed-subscriber` | 修理: 元3を1へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `people-unsubscribed-subscribed` | 修理: 元4を2へ取り違える。旧全体非等価は別IDで通り、新の独立人物期待値が赤になる。 | 38/0 | 36/1 |
| `keep-usercreated-user_id` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性user_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-usercreated-user_name` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性user_nameの観測を新保持先も検知する。 | 37/1 | 34/3 |
| `keep-usercreated-display_name` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性display_nameの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-usercreated-bio` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性bioの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-usercreated-aggregate_id` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性aggregate_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-usercreated-aggregate_type` | 保持: 元のTestSnsUserCreatedEvent::test_create_user_event_successが持つ公開属性aggregate_typeの観測を新保持先も検知する。 | 36/2 | 35/2 |
| `keep-userfollowed-follower_user_id` | 保持: 元のTestSnsUserFollowedEvent::test_create_followed_event_successが持つ公開属性follower_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userfollowed-followee_user_id` | 保持: 元のTestSnsUserFollowedEvent::test_create_followed_event_successが持つ公開属性followee_user_idの観測を新保持先も検知する。 | 37/1 | 34/3 |
| `keep-userprofileupdated-user_id` | 保持: 元のTestSnsUserProfileUpdatedEvent::test_create_profile_updated_event_with_both_fieldsが持つ公開属性user_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-userprofileupdated-new_bio` | 保持: 元のTestSnsUserProfileUpdatedEvent::test_create_profile_updated_event_with_both_fieldsが持つ公開属性new_bioの観測を新保持先も検知する。 | 36/2 | 35/2 |
| `keep-userprofileupdated-new_display_name` | 保持: 元のTestSnsUserProfileUpdatedEvent::test_create_profile_updated_event_with_both_fieldsが持つ公開属性new_display_nameの観測を新保持先も検知する。 | 36/2 | 35/2 |
| `keep-postcreated-post_id` | 保持: 元のTestSnsPostCreatedEvent::test_create_post_event_successが持つ公開属性post_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-postcreated-author_user_id` | 保持: 元のTestSnsPostCreatedEvent::test_create_post_event_successが持つ公開属性author_user_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-postcreated-content` | 保持: 元のTestSnsPostCreatedEvent::test_create_post_event_successが持つ公開属性contentの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-postcreated-mentions` | 保持: 元のTestSnsPostCreatedEvent::test_create_post_event_successが持つ公開属性mentionsの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-replycreated-reply_id` | 保持: 元のTestSnsReplyCreatedEvent::test_create_reply_event_successが持つ公開属性reply_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-replycreated-author_user_id` | 保持: 元のTestSnsReplyCreatedEvent::test_create_reply_event_successが持つ公開属性author_user_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-replycreated-content` | 保持: 元のTestSnsReplyCreatedEvent::test_create_reply_event_successが持つ公開属性contentの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-replycreated-parent_post_id` | 保持: 元のTestSnsReplyCreatedEvent::test_create_reply_event_successが持つ公開属性parent_post_idの観測を新保持先も検知する。 | 36/2 | 35/2 |
| `keep-replycreated-parent_reply_id` | 保持: 元のTestSnsReplyCreatedEvent::test_create_reply_event_successが持つ公開属性parent_reply_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-contentliked-target_id` | 保持: 元のTestSnsContentLikedEvent::test_create_like_event_successが持つ公開属性target_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-contentliked-user_id` | 保持: 元のTestSnsContentLikedEvent::test_create_like_event_successが持つ公開属性user_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-contentliked-content_author_id` | 保持: 元のTestSnsContentLikedEvent::test_create_like_event_successが持つ公開属性content_author_idの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-contentliked-content_type` | 保持: 元のTestSnsContentLikedEvent::test_create_like_event_successが持つ公開属性content_typeの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-contentdeleted-target_id` | 保持: 元のTestSnsContentDeletedEvent::test_create_delete_event_successが持つ公開属性target_idの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentdeleted-author_user_id` | 保持: 元のTestSnsContentDeletedEvent::test_create_delete_event_successが持つ公開属性author_user_idの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentdeleted-content_type` | 保持: 元のTestSnsContentDeletedEvent::test_create_delete_event_successが持つ公開属性content_typeの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentmentioned-target_id` | 保持: 元のTestSnsContentMentionedEvent::test_create_mentioned_event_successが持つ公開属性target_idの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentmentioned-mentioned_by_user_id` | 保持: 元のTestSnsContentMentionedEvent::test_create_mentioned_event_successが持つ公開属性mentioned_by_user_idの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentmentioned-mentioned_user_names` | 保持: 元のTestSnsContentMentionedEvent::test_create_mentioned_event_successが持つ公開属性mentioned_user_namesの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-contentmentioned-content_type` | 保持: 元のTestSnsContentMentionedEvent::test_create_mentioned_event_successが持つ公開属性content_typeの観測を新保持先も検知する。 | 37/1 | 36/1 |
| `keep-postcreated-aggregate_type` | 保持: 元のTestEventTypeValidation::test_content_events_have_correct_aggregate_typeが持つ公開属性aggregate_typeの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-replycreated-aggregate_type` | 保持: 元のTestEventTypeValidation::test_content_events_have_correct_aggregate_typeが持つ公開属性aggregate_typeの観測を新保持先も検知する。 | 37/1 | 35/2 |
| `keep-userunfollowed-follower_user_id` | 保持: 元のTestSnsUserUnfollowedEvent::test_create_unfollowed_event_successが持つ公開属性follower_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userunfollowed-followee_user_id` | 保持: 元のTestSnsUserUnfollowedEvent::test_create_unfollowed_event_successが持つ公開属性followee_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userblocked-blocker_user_id` | 保持: 元のTestSnsUserBlockedEvent::test_create_blocked_event_successが持つ公開属性blocker_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userblocked-blocked_user_id` | 保持: 元のTestSnsUserBlockedEvent::test_create_blocked_event_successが持つ公開属性blocked_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userunblocked-blocker_user_id` | 保持: 元のTestSnsUserUnblockedEvent::test_create_unblocked_event_successが持つ公開属性blocker_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userunblocked-blocked_user_id` | 保持: 元のTestSnsUserUnblockedEvent::test_create_unblocked_event_successが持つ公開属性blocked_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-usersubscribed-subscriber_user_id` | 保持: 元のTestSnsUserSubscribedEvent::test_create_subscribed_event_successが持つ公開属性subscriber_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-usersubscribed-subscribed_user_id` | 保持: 元のTestSnsUserSubscribedEvent::test_create_subscribed_event_successが持つ公開属性subscribed_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userunsubscribed-subscriber_user_id` | 保持: 元のTestSnsUserUnsubscribedEvent::test_create_unsubscribed_event_successが持つ公開属性subscriber_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-userunsubscribed-subscribed_user_id` | 保持: 元のTestSnsUserUnsubscribedEvent::test_create_unsubscribed_event_successが持つ公開属性subscribed_user_idの観測を新保持先も検知する。 | 37/1 | 33/4 |
| `keep-profile-none` | 保持: bioのみ更新する元行のNoneが文字列に変わる退行。 | 37/1 | 36/1 |
| `keep-type-input-usercreated` | 保持: 元の種類試験だけにあるtest文字列と省略入力の保持を個別に確認。 | 37/1 | 36/1 |
| `keep-type-input-postcreated` | 保持: 元の種類試験だけにあるtest文字列と省略入力の保持を個別に確認。 | 37/1 | 36/1 |
| `keep-type-input-replycreated` | 保持: 元の種類試験だけにあるtest文字列と省略入力の保持を個別に確認。 | 37/1 | 36/1 |
| `repair-nonempty-mentions` | 修理: createの途中でmentionsを空にすると旧共有集合との比較は通る。新は独立した非空集合を検査する。 | 38/0 | 36/1 |
| `repair-mentioned-names` | 修理: createの途中で名前集合を空にすると旧共有集合との比較は通る。新は独立した二人の集合を検査する。 | 38/0 | 36/1 |
| `id-fixed` | 保持: 同入力の別ID発行という収集/通知の独立契約を旧新とも検知する。 | 30/8 | 30/7 |
| `id-string` | 保持: 元の整数型観測が新保持先にも残る。 | 37/1 | 13/24 |
| `time-naive-311` | 保持: #311の修正前と同じnaive時刻を旧新とも検知する。 | 37/1 | 30/7 |
| `time-ancient` | 保持: 現在の発生時刻を古い固定値にすると旧新とも失敗する。 | 30/8 | 30/7 |
| `time-nonutc-offset` | 修理: 同じ瞬間の非UTC時刻は旧のaware比較を通るが、新のoffsetゼロが拒否する。 | 38/0 | 30/7 |
| `keep-reassignment-user_name` | 保持: 通常再代入を許す退行を旧新のAttributeError観測が検知する。 | 37/1 | 36/1 |
| `repair-mutate-then-reject-user_name` | 修理: 値を書換えてから拒否する誤実装は旧拒否だけでは通るが、新の拒否後元値が検知する。 | 38/0 | 36/1 |
| `keep-reassignment-follower_user_id` | 保持: 通常再代入を許す退行を旧新のAttributeError観測が検知する。 | 37/1 | 36/1 |
| `repair-mutate-then-reject-follower_user_id` | 修理: 値を書換えてから拒否する誤実装は旧拒否だけでは通るが、新の拒否後元値が検知する。 | 38/0 | 36/1 |
| `legal-equal-clock` | 合法な時計: 同じUTC値を返す時計を製品と観測側へ等しく適用。時刻非等価だけを要求する旧7件が失敗し、新は全件成功する。 | 31/7 | 37/0 |

同一時計の対照では一時的な試験pluginで製品側と試験側のdatetimeを同じ固定UTC時計へ差し替えた。新しい製品注入口を足していない。旧7件の発生時刻非等価だけが赤になることを確認し、対象型の生成、整数ID、UTC日時の型検査は双方で成功する条件である。

## 限界と公開後の確認

- ローカルで全リポジトリ試験、quality/live、実LLM、有償API、SNS本番接続は実行していない
- 公開した正確なcommitのCIはこの文書作成時点では未確認。CIはPython3.10、uv固定依存、pytest -n autoなどの全ゲートを別途確認する
- 基準失敗・製品不具合修理・製品簡素化は0。既存の任意項目全てや深い集合不変性を新しく保証したという主張はしない
- 発行元の業務規則、公開範囲、PRIVATE配送、画面参照寿命、保存同一性は別の所有者。今回の生成値試験で代替したとは扱わない
