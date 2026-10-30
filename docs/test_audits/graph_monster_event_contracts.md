# 空間上のモンスター反応イベントの試験監査

## なぜ

理由を渡して同じ属性を読むだけの試験では、理由が実際の観測へ届くことを
確かめられない。逃走イベントの最小構築も、反応から発火したイベントを
確かめる既存試験と同じ識別子を読み直していた。

この2宣言を、公開formatterと実ハンドラの既存試験へ集約する。
追跡対象の排他的指定はイベント生成時の独立した不変条件なので保持する。

## 範囲と基準

- 基準: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- 対象: `tests/domain/world_graph/event/test_monster_reaction_events_validation.py`
- 元6宣言・展開10件を `R4 / F0 / C2 / D0` に分類
- 対象は106行から63行、6宣言から4宣言へ変更
- 保持先2ファイルを含む試験行数は976行から938行。差分は13行追加・51行削除
- 製品コードと共通準備の差分は0
- 対象外の保持先宣言を、6宣言の監査完了数へ加算しない

`R` は契約を保持、`F` は検査を修復、`C` は強い保持先へ統合、`D` は削除を表す。

## 全6宣言の判断

| 元の宣言 | 判定 | 保護する契約と保持先 |
|---|---|---|
| `TestStartedChasingValidation::test_player_target_non_none_ok` | R | プレイヤー7だけを指定でき、モンスター対象が空。過剰な拒否を検出する |
| `TestStartedChasingValidation::test_monster_target_non_none_ok` | R | モンスター202だけを指定でき、プレイヤー対象が空。片側だけの拒否を検出する |
| `TestStartedChasingValidation::test_none_raises_value_error_2` | R | 対象なしを生成時に拒否し、排他的指定の診断を返す。`test_no_target_raises_value_error` へ改名 |
| `TestStartedChasingValidation::test_none_raises_value_error` | R | 両方指定を生成時に拒否し、同じ診断を返す。`test_both_targets_raise_value_error` へ改名 |
| `TestAbandonedChaseReason::test_all_abandon_chase_reason_value_event_can_build` | C | 理由5値を公開formatterの `TestAbandonedChaseProse::test_reason_single_prose` へ集約 |
| `TestStartedFleeingShape::test_min_can_build` | C | 逃走主体101と地点1を実ハンドラの `TestStartedFleeingEvent::test_always_flee_event_trigger` へ集約 |

R4の入力・検査・例外の照合文字列は変更していない。成功2状態は、常に例外を
投げる実装で拒否2状態だけが通ることも防ぐ。通常の反応ハンドラは正しい対象を
作るため、不正な2状態を直接拒否するイベント試験の代わりにはならない。

## 所有者と入力の保存

製品の流れは `SpotMonsterBehaviorTickService` → `MonsterReactionHandler.try_react`
→ 実イベントの `create` → グラフのイベント蓄積となる。観測側は型登録・配信先解決を
経て `SpotGraphObservationFormatter.format` が実イベントを読み取る。

### 理由の保持

保持先は `tests/application/observation/test_monster_reaction_state_prose.py`。

- 元の理由は `grace_expired`、`max_ticks_exceeded`、`target_lost`、`search_expired`、`no_path` の5値
- 元の `aggregate_id=1` に対し、既存保持先は999だったため、両方を表に残した
- いずれも `aggregate_type="SpotGraphAggregate"`、`monster_id=101`、`spot_id=1`
- 追加の任意引数は渡さず、最小構築を維持
- 元の `ev.reason == reason` は、実formatterが `event.reason` をそのまま入れる
  `result.structured["reason"] == reason` に包含される。期待値は試験の独立したパラメータ
- 既存の名前・事実描写・内部理由の本文への非漏洩も保持

`Literal` の型注釈は実行時の値制限ではない。元の値写し試験が、静的型検査や
ハンドラの全発火経路を保証していたとは扱わない。`target_lost` は予約された理由であり、
現在の通常ハンドラから到達可能だとは主張しない。関連する既存試験の説明も更新した。

### 逃走の主体と場所

保持先は `tests/application/monster/test_monster_reaction_state_events.py`。
元と同じグラフ1・モンスター101・地点1、同じ最小引数で実イベントを生成する。
ハンドラの `try_react` を通し、イベント1件と元の2属性の等価検査を行う。
リポジトリと移動協力処理は模擬するが、イベント・モンスター・グラフは実体を使う。

試験専用の製品公開口や削除可能な共通準備は見つからなかった。

## 履歴と設計

- [PR #142](https://github.com/Motifman/llm-rpg/pull/142): 移動だけでは伝わらない逃走・追跡・諦めの瞬間を観測へ流した
- [55b9308](https://github.com/Motifman/llm-rpg/commit/55b93084d8747c125ab8c7072dcfe4b2e90cc451): 対象の排他的指定を生成時に強制し、今回の6宣言を追加した
- [PR #189](https://github.com/Motifman/llm-rpg/pull/189): 観測者に分からない内部理由を本文から伏せ、`structured` には残した
- `docs/observation_model_axes.md` の軸1・2に沿い、事実の保持と読み手への表現を別々に守る

既存の `ValueError` はこの導入時に明示された契約であり、例外体系の変更は行わない。

## 検証

Python 3.10.22、pytest 8.4.1、外部通信を遮断し、各作業先の実ソースを読み込む環境で直列実行した。

| 段階 | 一意の実行件数 | 結果 |
|---|---:|---|
| 未編集の対象 | 10 | 全成功 |
| 未編集の保持先2ファイル | 35 | 全成功 |
| 統合前の保持先先行確認 | 11 | 全成功。両グラフの各5理由と逃走1件 |
| 復元後の対象＋保持先2ファイル | 44 | 全成功。対象4件＋保持先40件 |

保持の対照として、元試験と保持先へ同じ製品変異を個別に適用した。

| 故意に入れた誤り | 元試験の失敗件数 | 保持先の失敗件数 |
|---|---:|---:|
| 理由を `grace_expired` へ誤って上書き | 4 | 8（両グラフで各4理由） |
| 逃走主体を101から102へ置換 | 1 | 1 |
| 逃走地点を1から2へ置換 | 1 | 1 |

3種類・6実行とも収集失敗ではなく、期待した値の不一致を検出した。
各回の後に製品ソースを元のバイト列へ戻し、最後に製品1601ファイルのハッシュ一致を確認した。
残した4試験の本体と、説明以外のハンドラ保持先の構文木も変更前と一致した。

再現する通常コマンド:

```bash
uv run --frozen pytest \
  tests/domain/world_graph/event/test_monster_reaction_events_validation.py \
  tests/application/monster/test_monster_reaction_state_events.py \
  tests/application/observation/test_monster_reaction_state_prose.py
```

変更した試験3ファイルの `ruff check`、`git diff --check`、リポジトリの内部ホスト名検査も成功。
全リポジトリの試験・型検査・公開後のCI成功は、この局所実行の結果には含めない。
