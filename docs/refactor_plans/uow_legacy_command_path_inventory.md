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

2026-08-29時点で、`create_world_runtime`が現在利用する更新serviceはすべて
`CommandScopeFactory`を必須とし、未配線時に長寿命repositoryへ戻る公開更新入口は0件である。

`CALL_MEETING`は専用`MeetingCommandService`が自分のscopeで完結するため、factoryの存在を
確認した後にだけ通常interactionのscopeを迂回する。会議を通常interactionの内側へ入れると
入れ子transactionになるため、この専用分岐は旧更新fallbackではない。

## 移行済みで旧分岐を持たない入口

次は公開更新入口がscopeを必須とし、未配線なら更新対象へ触れる前に拒否する。

- item transfer (`give_item` / `drop_item` / `pickup_item`)
- movement、exploration、scenario event、reactive passage、reactive object、monster spawn、monster behavior
- needs decay、status effects、food spoilage、weather、day-night、synchronized action
- trade offer expiry、market order expiry、player outcome rule、death grace
- player trade、merchant trade、marketの注文作成・約定・価格変更・取消
- spot object / item interaction、player interaction
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
  market order expiryの確定後観測口は更新fallbackではないため残す。

## 残作業の順序

なし。#1244の最終監査で次を確認した。

- `data/scenarios/*.json`の全17シナリオを`create_world_runtime`で構築できる
- 各シナリオに存在する19〜24個の更新service・stageは、すべて本番の
  `CommandScopeFactory`へ接続される
- `use_item`、`tend_to_player`、`prepare_action`のLLM更新入口にもfactoryが接続される
- scope factory所有serviceの分類漏れはなく、任意fallback許可表は空である
- 旧`UnitOfWork` clientは既知39ファイルから増えておらず、本番compositionから構築されない
- 全体試験、構造試験、全シナリオ配線試験を継続的な回帰契約として残す

各PRは許可表から対象だけを除き、未配線拒否がrepository・provider・publisherへの接触より
先に起きる試験を追加する。

## #1244受入条件との照合

| 受入条件 | 最終状態 | 継続的な検査 |
|---|---|---|
| 本番compositionから旧transaction・publisherへ到達するcommandを一覧化する | 完了。scope所有26 module、旧UoW client 39 module、ロードのみ5 moduleを分類した | `test_legacy_command_path_inventory.py` |
| 各経路を移行・問い合わせ・fixture／migration・削除へ分類する | 完了。更新入口はscope必須、queryと確定後通知は対象外、未接続旧機能は別途接続または削除判断とした | 本文の「監査結果」「旧UnitOfWork群」「直接publisherの分類」 |
| 移行済みserviceの任意fallbackを除去する | 完了。許可表は空で、全17シナリオの全更新service・stageがfactory接続済みである | `test_no_public_update_path_retains_an_optional_scope_fallback`、`test_all_shipped_scenarios_command_scope_wiring.py` |
| repository内部commitと旧UoWイベントAPIを本番commandから除去する | 完了。scope repositoryは同一transactionへ参加し独自commitせず、旧UoW clientは本番で構築されない | repository provider契約試験、transaction adapter契約試験、AST import graph試験 |
| commit前の直接外部配送を構造上追加できなくする | 完了。更新中のeventは`CommandContext`へ収集し、必須処理後のhandoffだけが外部配送する | `CommandScope`のイベント相試験、各commandのrollback時無観測・commit後観測試験 |
| 残す単独書込み入口を用途別に明示する | 完了。query、確定後通知、fixture・migration・管理用単発書込みを更新commandから分離した | 本文の「目的」「直接publisherの分類」 |
| 旧経路の再導入をAST・依存構造試験で防ぐ | 完了。別名import、再export、presentationを含む本番import graphまで検査する | `test_legacy_command_path_inventory.py` |

この照合は「旧型がコードベースに一件も存在しない」という意味ではない。未接続の39 clientを
現行spot-graph runtimeへ再接続できないことと、本番更新入口が新しい確定契約だけを使うことを
#1244の完了条件とする。旧client自体の移行・削除は各機能を再開するときに個別に判断する。
