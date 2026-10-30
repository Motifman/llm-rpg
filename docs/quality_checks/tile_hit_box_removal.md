# タイルの当たり判定を削除したときの確認

Issue #1862の10番。HitBox専用の集約、保存先、サービス、出来事と、damage / hit_box_id / hit_box_collision_policy / hit_box_spawn_paramを削除する。モンスター・状態異常・スポットでの攻撃・追跡のsnapshotには変更を加えない。

## テストリスト

- [x] 専用実装の不在を確認する試験を先に書き、削除前に失敗、削除後に成功することを確認する。
- [x] 共有保存先のHitBoxの項目と採番が無く、全消去でも復活しない。
- [x] SQLiteの束は当たり判定を持たず、物理マップ・モンスター・プレイヤー・世界構造を保持する。過去のHitBoxの表も保持する。
- [x] 形・速度・効果・状態異常・状態補正とスキル装備の試験を保持する。
- [x] 残るタイルの出来事の観測除外と、本番の観測の網羅を保持する。
- [x] smoke_stubと山村・避難訓練の各3シード40tickの全記録種別・観測種別・行動件数が前後一致する。
- [x] 削除したモジュールへのimport・型参照がsrc/testsに残らない。

## 参照経路と判断

削除前にsrcの全PythonファイルをASTで解析し、型だけのimportを含めて依存を確認した。HitBoxへの外部参照は共有メモリ保存先、SQLiteの束に限定される。CombatLogicServiceの製品コードからの呼び出しは0件で、CombatConfigServiceとDamageは同サービスだけが使用していた。プレイヤーとモンスターの集約試験は計算部分だけを外し、ダメージ適用と結果の出来事の確認を残した。

シナリオのモンスター配置 → world_runtimeのSkillLoadoutAggregate.create / MonsterAggregate.reconstitute、および条件付き出現のSpotGraphMonsterSpawnStageService → SkillLoadoutAggregate → SkillDeck → SkillSpec → SkillHitPattern → HitBoxShape / HitBoxVelocityという依存がある。SkillSpec → HitEffectの依存と、別に本番が使う状態異常・状態補正も残す。初期装備の枠数は0だが、型と装備の保存・復元に必要なので、空であることを理由に共通の値を削除しない。

目的の選択はIssueで決定済み。実装前に、専用実装の削除と共通の値の保持を選んだ。全部残す案は変更量が少ないが、実行経路が二重に見える問題を残す。共通の値まで削除する案は本番の装備の型・保存経路を壊す。スポットの世界に当たり判定を導入する要件が生じた場合は、この判断を見直す。

削除後の検索には、維持するSQLiteの過去の列名と、不在を保証する試験の文字列が残る。削除モジュールへのimport・再公開・型参照は無い。物理マップの保存先は別の変更で扱う。

## 質感

スタブ実験は文章の自然さや意思決定の質を測れない。今回は、本番で使わない当たり判定を取り除くため、人物が見聞きする出来事と行動件数が同条件で変わらないことを確認対象にする。質感が改善したとは主張しない。実LLMは呼ばず、.envを置かず、検証時はload_dotenvも無効化した。

## 検証結果

変更前後とも、smoke_stubはsurvival_island_v3_coop / 2tick / stubで動作した。観測と行動は0件のため、それだけで同等とは判定しない。次の6実行は、make fuzz-scenarioと同じ実行関数でNullTraceRecorder.recordを一時的に収集し、全記録種別別件数と観測種別別件数がそれぞれ一致した。すべて40tick到達、例外と検査所見は0件。

| シナリオ | シード | 行動件数（前後共通） | 観測件数（前後共通） |
| --- | --- | ---: | ---: |
| 山村 | 0 | 142 | 92 |
| 山村 | 1 | 139 | 127 |
| 山村 | 2 | 145 | 84 |
| 避難訓練 | 0 | 301 | 531 |
| 避難訓練 | 1 | 199 | 497 |
| 避難訓練 | 2 | 279 | 659 |

山村ではモンスターの出現・遭遇・攻撃、避難訓練では会議・倒れる出来事・落とした品の回収も含む。これはスタブの限られた行動範囲の同等性であり、実LLMの意思決定や全シナリオの同等性まで保証しない。

実行コマンド（前後で同条件）:

```sh
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=<検証用の保存先>
make fuzz-scenario SCENARIO=data/scenarios/mine_village_v1.json SEEDS=0-2 FUZZ_TICKS=40
make fuzz-scenario SCENARIO=data/scenarios/station_drill.json SEEDS=0-2 FUZZ_TICKS=40
```

関連試験は観測・スキル・共通値・集約など1,262件、構造とSQLiteの束105件、残す保存先・シナリオ・モンスターの条件付き出現1,019件が成功した（一部重複あり）。uv run mypyは1,345ファイル成功。変更したPythonファイルに限ったruffも成功。全体試験はCIで確認する。

実行結果と比較用スクリプトは一時保存先 `/tmp/llm-rpg-hitbox-1862/` に置いた。削除前のimport解析、削除後の参照解析、前後の解決済み設定・記録、種別ごとの比較結果を含む。

## 独立自己レビュー

pr-selfreviewで前後比較と判断を点検し、別のレビュー担当が差分と参照を確認した。CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 1。軽微な指摘はHitEffectから状態補正へ直接依存するように読める文書表現で、実際の依存に合わせて修正した。実装の修正指摘は0件。独立実行の関連試験72件も成功した。
