# 未使用戦闘例外の整理

Issue #1862の担当B。製品コードの変更はcombat_exceptions.pyの未使用例外3種と、不要になる基底例外のimportだけ。

## テストリスト

- [x] 不在保証3件を先に書き、変更前に3件とも失敗することを確認する。
- [x] 削除後に不在保証と、形・速度・効果・状態異常・スキル装備の関連試験が成功する。
- [x] src/tests/scriptsをASTとrgで調べ、実行時・型・再公開・動的文字列・error_codeの利用がない。
- [x] smoke_stubと山村・避難訓練の各3シード40tickで、全記録種別・観測種別・行動件数が前後一致する。
- [x] 変更Pythonのruff、mypy、空白検査、独立レビューを完了する。

## 調査と判断

DamageValidationExceptionとHitBoxInactiveExceptionの利用側は、PR #1876で退役したdamage.pyとhit_box_aggregate.pyだった。CombatTargetNotFoundExceptionは元から未使用であり、今回の削除漏れとは区別する。現在は3種の名前・error_codeとも定義以外に参照がない。パッケージによる再公開もなく、保存・復元のcodecや本番の接続からの参照もない。ASTではimport、TYPE_CHECKING内、名前、属性、文字列を検査し、rgでも名前・コード・モジュール参照を照合した。不在保証の期待値だけは削除後も試験に残す。

形・効果の例外はそれぞれHitBoxShape / HitEffectが実際に送出する。SkillSpecとSkillHitPattern、およびスキル装備の保存・復元はこれらの値を使う。CombatDomainExceptionとこの2種を保持し、基底型やerror_codeを変えない。判断は[D1862-23](../design_decisions/D1862-23.md)に残した。

## 前後比較と質感

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| 未使用の例外3種を取得する | 定義が残る | 定義なし。不在保証で再導入を検出する |
| 空の形や不正な効果値を渡す | 対応する検証例外を送出 | 同じ例外・error_codeを維持する |
| スポットで行動し、出来事を見聞きする | 本番の戦闘・観測の経路を使用 | 同じ経路を維持する |

スタブでは文章の自然さや意思決定の質は評価できない。本変更では質感の改善を主張せず、同条件で見聞きする出来事の種類・件数と行動件数が変わらないことを確認する。実LLMを呼ばず、作業ツリーに.envを置かず、検証用sitecustomize.pyでdotenv.load_dotenvを無効化する。

## 検証結果

比較基準はdd7180879ef998ffaacad4a55dce0c433323170c。変更前の実験時の未追跡差分は不在保証の試験だけで、製品コードは基準と同一。実行結果とAST調査は`/tmp/llm-rpg-1862-b/`に保存する。全体試験はCIへ任せ、手元は関連試験だけを最大4並列で実行する。quality/live_apiの手動試験は実行しない。


変更後の製品コードは98d5c0f096a068eb56a18563f65a716a91a0c422。以降の変更は検証文書のみ。保持する3種の例外クラスは前後のASTが一致した。関連試験556件成功、変更Pythonのruff成功、uv run mypyは1,276ファイル成功、空白検査成功。

前後とも次を実行した。

```sh
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=<比較用の固有保存先>
make fuzz-scenario SCENARIO=data/scenarios/mine_village_v1.json SEEDS=0-2 FUZZ_TICKS=40
make fuzz-scenario SCENARIO=data/scenarios/station_drill.json SEEDS=0-2 FUZZ_TICKS=40
```

解決済み設定はsmoke_stub / survival_island_v3_coop / 2tick / stubを確認。smokeの全記録種別別件数は一致したが、行動と観測が0件なのでこれだけでは同等性を判定しない。fuzzは同じ実行関数のNullTraceRecorder.recordを外部スクリプトで収集し、全記録種別別件数とstructured.typeごとの観測件数、makeの行動件数を照合した。全6試行で一致し、40tick到達、例外・検出事項0件だった。

| シナリオ | シード | 行動件数（前後共通） | 観測件数（前後共通） |
| --- | --- | ---: | ---: |
| 山村 | 0 | 142 | 92 |
| 山村 | 1 | 139 | 127 |
| 山村 | 2 | 145 | 84 |
| 避難訓練 | 0 | 301 | 531 |
| 避難訓練 | 1 | 199 | 497 |
| 避難訓練 | 2 | 279 | 659 |

観測合計1,990件、行動合計1,205件。これはスタブの限られた行動範囲の確認であり、実LLMの判断や全シナリオの同等性は未確認。比較の詳細は一時保存先のcomparison.json、前後のtrace・解決済み設定・makeログに残した。

## 独立自己レビュー

pr-selfreviewの前後比較・設計判断・実装・試験・説明を点検した。独立レビュー担当もAST・参照・本番の装備生成・SQLite保存復元を確認し、CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0件、範囲外の問題0件だった。独立実行の不在保証・戦闘・スキル・SQLiteスキル保存先の試験111件も成功した。修正が必要な指摘と未対応事項はない。
