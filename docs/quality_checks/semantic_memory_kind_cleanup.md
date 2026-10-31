# MemoryKindの使われなくなった宣言を外す検証 (#1893)

> D1928-2 で `find_all_attached_to` は消えた。Being の保存先は `find_by_id` で引く。


基準: `f86d9fcde0ba4ada9d1e3124c13452dfa3b3aae2`。担当D、ブランチ `codex/1893-remove-semantic-memory-kind`。

## テストリスト

- [x] enumからSEMANTICがなくなり、現役3種類の値が変わらない。
- [x] v1/v2の旧snapshotでsemantic宣言だけを除き、同一性・所属・現役宣言を保つ。
- [x] semanticだけの宣言と重複した宣言を読み、再保存で復活させない。
- [x] semantic以外の未知値を、混在時も拒否する。
- [x] ファイル復元で宣言の除去件数を報告し、記憶本文の除去件数と区別する。
- [x] SQLiteの旧JSON行を読み、新規保存・再保存できる。表・必須列・migrationは変えない。
- [x] snapshot_loadで宣言の除去件数を観測する。ユーザー指定によりA担当が2ファイルの配線を作成し、Dへ合流した。
- [x] 関連試験、ruff、mypy、空白検査、変更前後のsmokeと6回のfuzzを確認する。

## 調査

ASTでsrc/scriptsのimport・属性参照・変換呼出を調べた。MemoryKindのimportはBeing集約とcodecだけで、本番からSEMANTICへの属性参照は0件。宣言生成のbeing_provisioning_serviceは空の既定値を使う。rgでも型import・再公開・動的参照・文字列の宣言を確認した。

SQLiteのbeings表はbeing_id_value / snapshot_version / snapshot_json / updated_atがNOT NULL。種類専用の列や制約はなく、find_by_idとfind_all_attached_toが共通codecで復元する。スキーマの変更は不要。

対象の入口はBeingSnapshotCodecのdeclared_memory_kinds。A担当の世界の追跡snapshotとは別で、world.jsonや世界のsubsystemキーは扱わない。memory_payload_jsonも別契約であり、この削除で記憶本文やremoved_memory_payload_keysの表を変更しない。

## 変更前後の比較

専用`.venv`と絶対PYTHONPATHで読込元を固定した。`/tmp/llm-rpg-1893-d/no-dotenv/sitecustomize.py`でdotenv.load_dotenvを無効にし、実LLMは呼んでいない。smokeのresolved configでprofile・scenario・2tick・基準commitと変更後差分を確認した。

各欄は前後で一致した。fuzzは40tick・各seedで`make fuzz-scenario`を実行し、NullTraceRecorderのrecordを一時的に記録して種類別件数を比較した。観測はstructured.type別、全記録はkind別の件数を比較している。

| run | 全記録件数 / 種類数 | 観測件数 / 種類数 | 行動件数 |
|---|---:|---:|---:|
| smoke_stub | 98 / 13 | 0 / 0 | 0 |
| mine_village_v1 seed 0 | 4065 / 22 | 92 / 11 | 142 |
| mine_village_v1 seed 1 | 4055 / 22 | 127 / 14 | 139 |
| mine_village_v1 seed 2 | 4068 / 22 | 84 / 15 | 145 |
| station_drill seed 0 | 3512 / 25 | 531 / 17 | 301 |
| station_drill seed 1 | 2585 / 24 | 497 / 14 | 199 |
| station_drill seed 2 | 3436 / 25 | 659 / 19 | 279 |

smokeの観測0件だけでは回帰を保証できないため、観測が出たfuzzも比較した。fuzzの例外・漏れの指摘は全6回0件。生データと実行ログは`/tmp/llm-rpg-1893-d/{before,after-final}`、比較結果は同ディレクトリの`trace-comparison.json`。

## 検索結果の扱い

`MemoryKind.SEMANTIC`の参照はsrc/tests/scriptsから0件。src/testsの`SEMANTIC`は、不在保証の試験と大文字の未知値を拒否する互換fixtureに残る。文字列`semantic`はcodecの旧宣言との比較、互換fixture、既存の不透明なpayloadの試験に残す。

`removed_memory_payload_keys.py`とその試験にあるsemantic_entries等は別の記憶本文の移行で、今回の対象ではない。semantic_resolver、semantic_repeat、semanticsは別概念。docs/design_decisions、docs/memory_systemの実験記録、docs/test_audits/being_identity_contracts.mdの4種類を保持した判断は当時の履歴なので改変しない。

## レビュー材料

目的の選択はIssue #1893で決定済みの宣言削除。MemoryKind全体の削除や知り合いの種類追加は対象外で、ここは仕様上の一択。実装前に、共通codecで旧宣言だけを除く案とDBの一括更新案を比較し、ファイルにも適用できスキーマ変更不要の前者を採った。代償はcodecに互換分岐が残ること。旧snapshotを受け付けない方針に変わった場合は見直す。後から追加した代替案はない。

pr-selfreviewのpr-before-after / pr-decision-cardの観点と独立code-reviewerで点検した。初回の指摘は0件。最終差分ではCRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 1で、残存文字列の説明から未知値拒否fixtureが抜けていた点を修正した。配線はA担当が作成した独立パッチを適用し、通し試験も含めて再確認し、最終判定はApprove。未対応の指摘はない。

## snapshot_loadへの配線

`snapshot_load.payload.removed_declared_memory_kinds`に`[{"being_id": "…", "counts": {"semantic": 2}}]`の形で出る。0件のBeingは含めず、全員0件なら空配列。`removed_memory_keys`は引き続き記憶本文だけの件数を扱う。世界のsnapshotはこの配線の対象外。

通し試験はsmoke_stubで複数Beingを保存し、1人だけの宣言を書き換えて再開する。0件・2件のケースで実際のtraceの値を検証した。配線前は両方KeyErrorで失敗し、A担当の配線を合流して成功した。codecの不在・旧宣言試験も変更前5件失敗から成功、ファイル入口の件数・保存前拒否試験も変更前3件失敗から成功を確認済み。

## 検証結果

関連252件成功。対象はdomain/being、Beingのファイル入出力・復元・記憶snapshot・実験session、InMemory/SQLiteのBeing保存先、snapshot CLIと実験スクリプト、不在保証と今回の通し試験。実行は専用venvの`uv run pytest`、並列4以下。mypyは1,261ファイル成功、変更したPythonのruff check / formatとgit diff --checkも成功。全体試験はCIに任せ、quality/live_apiは手元では実行していない。

初回CIでは設計判断文書の見出し形式が構造検査で1件失敗した。見出しを`## D1893-5. 題名`へ直し、`tests/architecture/test_one_number_one_decision.py`の10件成功を確認した。ゲームのコードと前後比較の対象には変更なし。
