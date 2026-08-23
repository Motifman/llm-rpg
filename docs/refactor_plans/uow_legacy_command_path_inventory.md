# #1244 旧確定経路の機械棚卸し

## 目的

この文書は、`codex/uow-rearchitecture` の本番runtimeで使う更新入口について、
`CommandScope`へ移行済みの経路と、未配線時に旧更新へ戻れる経路を区別する正本である。
一覧は `tests/architecture/test_legacy_command_path_inventory.py` と対応し、追加・撤去を
同じPRで更新する。

ここでいう「旧経路」は、次のいずれかを指す。

- `CommandScopeFactory`が無いと長寿命repositoryを直接更新する
- 状態確定前に外部publisherへ直接配送する
- 旧`domain.common.unit_of_work.UnitOfWork`へイベント処理まで委ねる

query、確定後の最善努力通知、fixture・移行・管理用の単発書込みは、この一覧の更新command
とは分けて扱う。

## 監査結果

2026-08-24時点で、`create_world_runtime`は現在利用する更新serviceへ必要な
`CommandScopeFactory`をすべて注入している。したがって通常の実験・server sessionは
移行済み経路を通る。一方、次の14サービスは未配線時に旧経路へ戻れるため、#1244を
閉じる前に撤去が必要である。

| 区分 | 残存サービス | 残っている旧挙動 |
|---|---|---|
| world tick | `SpotGraphNeedsDecayStageService` | 長寿命status repositoryと旧publisher |
| world tick | `StatusEffectsTickStageService` | 長寿命status repositoryと旧publisher |
| world tick | `FoodSpoilageStageService` | 長寿命item repositoryと直接callback |
| world tick | `TradeOfferExpiryStage` | pending store・予約解除・通知の直接実行 |
| world tick | `SpotGraphEnvironmentStageService` | 天候・乱数更新と直接callback |
| world tick | `SpotGraphDayNightStageService` | 昼夜更新と直接callback |
| world tick | `ReactiveObjectStateBindingStageService` | interior・graphの直接更新 |
| world tick | `SynchronizedActionResolverStageService` | flag・graphの直接更新とmessage callback |
| world tick | `SpotMonsterBehaviorTickService` | monster単位scopeを迂回した直接更新 |
| 取引 | `PlayerTradeService` | offer・accept・decline・cancelの直接更新 |
| 取引 | `SpotGraphMerchantTradeService` | buy・sellの直接更新 |
| 取引 | `MarketService` | 注文作成・約定・価格変更・取消の直接更新 |
| interaction | `SpotInteractionApplicationService` | factory無しの通常interactionを直接更新 |
| interaction | `PlayerInteractionApplicationService` | factory無しの対人interactionを直接更新 |

`CALL_MEETING`は専用`MeetingCommandService`が自分のscopeで完結するため、interactionの
通常更新へ戻してはならない。ただし現在は「factory無し」と「`CALL_MEETING`」が同じ分岐に
入る。撤去時は、会議専用分岐を保ちながらfactory無しの通常更新だけをfail-fastへ変える。

## 移行済みで旧分岐を持たない入口

次は公開更新入口がscopeを必須とし、未配線なら更新対象へ触れる前に拒否する。

- item transfer (`give_item` / `drop_item` / `pickup_item`)
- movement、exploration、scenario event、reactive passage、monster spawn
- market order expiry、player outcome rule、death grace
- meeting、trade command
- `use_item`、`tend_to_player`、`prepare_action`

空のrules・bindings・slotsなど、更新対象が存在しない場合の副作用なし終了は旧経路ではない。

## 旧UnitOfWork群

旧`domain.common.unit_of_work.UnitOfWork`を直接importするapplication moduleは35ファイル、
`UnitOfWorkFactory`経由で生成するmoduleは5ファイル残る。1ファイルが両方に属するため、
旧UoW clientは合計39ファイルである。主なまとまりはguild、quest、shop、skill、SNS、
observation handler、旧physical-world command・handlerである。
現在の`create_world_runtime`、LLM実行配線、presentationからは構築されておらず、現行の
spot-graph runtimeとは別の未接続機能・fixture/library面である。

汎用executorとevent handler packageの再exportにより、旧`MovementApplicationService`、
`MovementStepExecutor`、`SkillCommandService`、notification / relationship handlerの
5 moduleは現行compositionのimport時にもロードされる。ただし、いずれのclassも現行の
`WorldLlmWiring`・presentationからは構築されない。
構造試験は再exportを含むimport graphを辿り、ロード対象の増加と旧classの構築を別々に禁止する。

これらを今回のspot-graph移行へ混ぜて一括削除しない。機能ごとに「本番へ再接続して
`CommandScope`化する」「fixture・移行専用と明記する」「未使用機能として削除する」の
いずれかを決める。構造試験は新しい旧`UnitOfWork`利用と、本番composition rootからの
再接続を禁止する。

## 直接publisherの分類

- `CommandContextEventPublisher`とcommit後dispatcher/handoffは正規経路である。
- speechのように永続状態を更新せず観測そのものを生成する入口は、この撤去対象ではない。
- `ConversationCommandService`など本番runtimeから未接続の旧機能は、上記旧UnitOfWork群と
  同様に別途接続・削除判断を行う。
- 更新service内の互換publisherは、対応する残存サービスの旧分岐撤去と同時に消す。

## 残作業の順序

1. needs decay / status effects（共有status transaction）
2. food spoilage、trade offer expiry
3. weather / day-night
4. reactive object、synchronized action
5. monster behavior
6. player trade、merchant trade、market
7. spot / player interaction（`CALL_MEETING`専用分岐を維持）
8. 許可表を空にし、全体試験・全scenario構築・本番配線監査を行って#1244を閉じる

各PRは許可表から対象だけを除き、未配線拒否がrepository・provider・publisherへの接触より
先に起きる試験を追加する。
