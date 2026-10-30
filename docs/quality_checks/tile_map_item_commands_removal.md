# タイルの宝箱・設置物・品の操作の削除

Issue #1862 の変更範囲6のうち、worldサービスの品の操作だけを対象とする。
本番の品の受け渡し・消費・あふれの処理と、所持品・取引・戦利品・施設割当は維持する。

## テストリストと削除境界

- [x] 削除前にASTと文字列検索で実行時・型の参照と再公開を確認する。
- [x] 対象9サービスと5例外の参照は、対象内と専用試験6本だけと確認する。再公開はない。
- [x] 専用試験に混在した共有コマンドの入力検証4件を契約の試験へ移し、削除前にも成功を確認する。
- [x] 物理マップ・宝箱の部品とドメイン試験、共有契約を残す。
- [x] 構造検査の自担当5行と、品の付与経路の一覧1行だけを外す。
- [x] 削除したモジュール名がsrc/tests/scriptsに残っていないことをASTと文字列検索で確認する。
- [x] 関連試験、変更Python限定のruff、mypyが通る。
- [x] smoke_stubと山村・避難訓練各3シード40tickの前後比較が一致する。
- [x] 独立レビューで巻き添えの削除がないことを確認する。

新しい振る舞いは加えない。残す共有コマンドの検証は、従来の4件の入力と
期待結果を維持し、サービスの準備への依存だけを外した。
他の専用試験は、削除対象の呼び出し結果・専用例外を調べるものであり一緒に消す。

## 前後の振る舞いと判断

| 場面 | 削除前 | 削除後 |
| --- | --- | --- |
| スポットで品を拾う・渡す・落とす・使う | スポットの処理を呼ぶ | 同じ処理を呼ぶ |
| 所持品があふれる・消耗品の効果が生じる | 本番の地面への配置・効果処理を呼ぶ | 同じ処理を呼ぶ |
| タイルの宝箱や設置物を操作する旧入口 | 未接続のサービスが存在する | 入口と専用例外・専用試験が無い |
| 共有コマンドへ無効なIDやスロットを渡す | ValueErrorを投げる | 同じ検証を維持する |

実装前に比較した目的上の選択は、未接続の入口を残すか削除するか。
削除は二つの世界の処理を取り違える余地を減らすが、旧入口との互換性は失う。
Issueで旧世界を廃止すると決めており、その互換性を維持する必要はない。
コード上は物理マップと共有契約まで削る案と比べ、利用側のないサービスだけを
消す案を採った。削除量は小さくなるが、残る問い合わせの依存を壊さず独立して確認できる。
一案だけの判断や事後に作った代替案はない。

## 比較条件

比較用出力は `/tmp/llm-rpg-1862-items/`。作業ツリーに.envを置かず、
一時的なsitecustomizeからdotenv.load_dotenvを無効にする。実LLMは呼ばない。
`make experiment EXPERIMENT_PROFILE=smoke_stub` と、
`make fuzz-scenario SCENARIO=... SEEDS=0-2 FUZZ_TICKS=40` を前後で実行する。
山村と避難訓練では、同じrun_random_agentsのNullTraceRecorder.recordを
検証専用スクリプトで収集し、全記録種別・観測種別ごとの件数と行動件数を比べる。

## 質感の所見と限界

本番の操作と観測文、手番を起こす規則は差分に含まれない。
未接続のタイルの入口を消すため、世界の中で知覚できる変化は意図していない。
本番の品の操作とあふれ・効果の試験、およびスタブの記録比較で維持を確かめる。
この確認は配線と処理の維持を見るもので、実LLMの語り口や長期の協調の同等性まで
保証しない。質感の改善を主張する変更ではなく、実LLMでの観察は行わない。

## 実行結果

関連試験3,677件が成功した。変更したPython3ファイルのruffと、mypyの
1,425ファイルも成功した。共有コマンドの4件は削除前にも成功を確認した。

smoke_stubの解決済み設定は前後とも既定の無人島シナリオ・2tick・stubで、
全記録種別ごとの件数が一致した。観測・行動は0件なので、この実行だけで
同等性を判断せず、次の40tickの比較も行った。

| シナリオ | シード | 行動件数（前後共通） | 観測件数（前後共通） |
| --- | --- | ---: | ---: |
| mine_village_v1 | 0 | 142 | 92 |
| mine_village_v1 | 1 | 139 | 127 |
| mine_village_v1 | 2 | 145 | 84 |
| station_drill | 0 | 301 | 531 |
| station_drill | 1 | 199 | 497 |
| station_drill | 2 | 279 | 659 |

全6試行で例外・検出事項0件。全記録種別・観測種別ごとの件数と行動件数が
一致した。合計は観測1,990件、行動1,205件だった。

独立したレビュー用サブエージェントの指摘はCRITICAL 0 / HIGH 0 / MEDIUM 0 /
LOW 0。独立したAST検査でも14モジュール・34クラスの残存参照は0件だった。
移した4件の試験本体は削除前とASTが一致している。修正が必要な指摘はなかった。

関連試験の再実行コマンド（全体試験はCIに任せる）:

```sh
uv run pytest tests/architecture tests/application/world tests/application/world_graph \
  tests/application/world_runtime/test_give_item_command_scope_wiring.py \
  tests/application/world_runtime/test_use_item_command_scope_wiring.py \
  tests/application/llm/test_use_item_quoted_inventory.py \
  tests/application/llm/test_spot_graph_drop_pickup_resolver.py \
  tests/application/llm/services/test_inventory_use_item_warning.py \
  tests/application/llm/services/executors/test_spot_graph_use_item_spoiled.py \
  tests/application/llm/services/executors/test_give_item_domain_error_messages.py \
  tests/application/test_item_grant_paths_declare_a_stance.py \
  tests/domain/player tests/domain/item \
  tests/domain/world/service/test_chest_interaction_policy.py \
  tests/domain/world/entity/test_chest_component.py \
  tests/application/trade tests/application/shop tests/domain/world_graph -n 4 -q
```
