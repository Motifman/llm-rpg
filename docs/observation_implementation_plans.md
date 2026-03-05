# 観測まわり実装計画・設計メモ

本ドキュメントは、Observation 機能の今後の拡張として「ObservationRecipientResolver の責務分離」「attention_level による観測フィルタリング」の実装計画と、`ApplicationExceptionFactory` のモック用フォールバックに関する見解をまとめたものです。

---

## 1. ObservationRecipientResolver の責務分離 実装計画

### 現状の課題

- `ObservationRecipientResolver` が「イベント型ごとの配信先ルール」と「WorldObjectId → PlayerId 解決」を一つのクラスに持っており、イベント種別が増えるほど `resolve()` 内の `isinstance` 分岐が肥大化する。
- 配信先ルールの追加・変更時に同じファイルを編集し続けることになり、単一責任の観点で分離した方がよい。

### 分離方針

1. **戦略パターン（イベント型 → 配信先解決戦略）**
   - インターフェース: `IRecipientResolutionStrategy`（例: `resolve(event) -> List[PlayerId]` または `supports(event) -> bool` + `resolve(event) -> List[PlayerId]`）
   - 各観測対象イベント型（またはグループ）ごとに実装クラスを用意する。
     - 例: `GatewayTriggeredRecipientStrategy`, `PlayerStatusEventRecipientStrategy`, `MapEventRecipientStrategy`（LocationExited / WorldObjectInteracted 等で WorldObjectId 解決を利用）
   - `ObservationRecipientResolver` は「戦略のレジストリ」として、イベント型に応じて対応する戦略を選び `resolve()` を委譲する。

2. **WorldObjectId → PlayerId 解決の共通化**
   - 現在の `_resolve_player_id_from_world_object_id` は、複数戦略から使われる共通ロジックである。
   - これを「ドメインのリポジトリに依存するサービス」として切り出す。
     - 例: `IWorldObjectToPlayerResolver`（または `IPlayerIdFromWorldObjectResolver`）をアプリケーション層のポートに定義し、実装で `PhysicalMapRepository` を用いる。
   - 各戦略はこのリゾルバを依存に持ち、`actor_id` / `object_id` をプレイヤーIDに変換する。

3. **実装ステップ案**

   | ステップ | 内容 |
   |--------|------|
   | 1 | `IRecipientResolutionStrategy` と「イベント型 → 戦略」のマッピングを定義する。既存の `resolve()` はそのまま動作するよう、一つの「デフォルト戦略」に現在のロジックを移す。 |
   | 2 | デフォルト戦略を「マップ系」「プレイヤー状態系」「インベントリ系」などに分割し、それぞれを別クラスに切り出す。Resolver は戦略リストを走査して `supports(event)` が True のものの `resolve(event)` を実行。 |
   | 3 | `IWorldObjectToPlayerResolver` を導入し、`PhysicalMapRepository` を使う実装を用意。マップ系戦略がこのリゾルバに依存するように変更。 |
   | 4 | 既存テストを「Resolver の統合テスト」と「各戦略の単体テスト」に整理。新規イベント追加時は新戦略クラス＋マッピング追加で対応できるようにする。 |

4. **配置案**

   - ポート: `application/observation/contracts/interfaces.py` に `IRecipientResolutionStrategy`, `IWorldObjectToPlayerResolver` を追加。
   - 戦略実装: `application/observation/services/recipient_strategies/` を新設し、`gateway_triggered.py`, `player_status_events.py`, `map_events_with_object_resolver.py` などに分割。
   - Resolver: `ObservationRecipientResolver` はコンストラクタで戦略リスト（またはレジストリ）を受け取り、`resolve(event)` で先頭の supports する戦略に委譲。

---

## 2. attention_level による観測フィルタリング 実装計画

### 仕様の整理（domain_events_observation_spec.md より）

- **FULL**: 全ての観測をそのまま渡す（現状の実装と同等）。
- **FILTER_SOCIAL**: 他プレイヤー入室・視界入り等を省略または要約する。
- **IGNORE**: 自分に直接関係するもの（ダメージ・アイテム・クエスト等）のみ渡す。

### 現状

- `IObservationFormatter.format(..., attention_level=...)` はインターフェースで受け取っているが、実装では未使用。常に FULL 相当の出力を返している。

### 実装方針

1. **観測種別の分類**
   - 各イベント／フォーマット結果を「自分専用」「他プレイヤー関連（ソーシャル）」「環境（天気・地形等）」などに分類する。
   - 例: `ObservationOutput` に `category` のようなメタ情報を持たせるか、Formatter 内部で「この出力はソーシャルか」を判定する。

2. **Formatter 側の変更**
   - `format()` の先頭で `attention_level` を参照。
   - **FILTER_SOCIAL**: 「他プレイヤーがやってきた」「〇〇が戦闘不能になった」など、配信先が「本人」でない観測（または structured の `role != "self"` かつ 他者関連）を、要約文（例: 「他プレイヤーの動きがありました」）に置き換えるか、`None` を返してスキップする。
   - **IGNORE**: 上記に加え、天気変化・地形・「誰かが入ってきた」など、自分に直接関係しない観測を `None` でスキップ。自分専用（ゴールド獲得・レベルアップ・ダウン・復帰・インベントリ等）のみ出力する。

3. **分類の持ち方**
   - 案A: `ObservationOutput` に `observation_category: Literal["self_only", "social", "environment"]` を追加し、Formatter が各 _format_* でそれを設定。`format()` 内で attention_level と category に応じて None または要約に変換。
   - 案B: Formatter 内で「このイベント＋recipient の組み合わせがソーシャルか」をメソッドで判定し、FILTER_SOCIAL/IGNORE のときはそこで None または要約を返す（Output の型は変えない）。

4. **実装ステップ案**

   | ステップ | 内容 |
   |--------|------|
   | 1 | 仕様書で「どのイベント／どの structured を FILTER_SOCIAL / IGNORE でどう扱うか」を一覧化する（例: Gateway 他者向け＝ソーシャル、PlayerGoldEarned＝自己専用）。 |
   | 2 | 案A を採用する場合、`ObservationOutput` に `category` を追加し、既存のすべての _format_* で category を設定。既存テストが壊れないようデフォルトは FULL 相当。 |
   | 3 | `ObservationFormatter.format()` の先頭で、`attention_level == FILTER_SOCIAL` のとき category がソーシャルのものを要約 or None、`attention_level == IGNORE` のときは自己専用以外を None にする分岐を実装。 |
   | 4 | テスト: FULL / FILTER_SOCIAL / IGNORE それぞれで、代表イベントについて「期待する観測が返る／スキップされる／要約になる」を検証する。 |

5. **イベントハンドラとの関係**

   - ハンドラは既に `_get_attention_level(player_id)` でプレイヤーの注意レベルを取得し、Formatter に渡している。フィルタリング実装後は、そのまま「渡した attention_level に応じて Formatter が None または要約を返す」だけでよい。

---

## 3. ApplicationExceptionFactory のモック用フォールバックについて

### 指摘されている点

- `ApplicationExceptionFactory.create_from_domain_exception` に「テストの Mock や DomainException 以外の例外が渡される場合があるためフォールバックを許容する」というコメントと、`getattr(domain_exception, "error_code", domain_class_name.upper())` によるフォールバックがある。
- 本番で「DomainException 以外」が渡り続けることは設計上想定していないため、**本番用の振る舞いをテストの都合でゆるめてはいけない**という懸念がある。

### 見解

- **本番コード側で「モックや想定外の型」を許容するフォールバックを入れるのは適切ではない**と考えます。
  - 本番で `create_from_domain_exception` に渡すのは「ドメイン層で捕捉した DomainException のサブクラス」に限定し、`domain_exception` がその型であることを呼び出し元が保証する設計にすべきです。
  - そのうえで、`error_code` は DomainException のサブクラスに定義されているはずなので、`getattr(..., domain_class_name.upper())` は「サブクラスが error_code を定義していない場合のフォールバック」にのみ使い、**「DomainException のサブクラスでない型が渡ってきた場合」は例外を投げる**ようにした方がよいです。

- **テストのあり方**
  - テストでは、`create_from_domain_exception` に渡すのは **必ず DomainException のサブクラス（またはそのインスタンス）** にすべきです。
  - モックで「任意の Exception を渡してアプリケーション例外に変換されること」を検証したい場合は、**DomainException を継承したテスト用の例外クラス** を定義し、それを使ってテストするのが正しいやり方です。
  - そうすれば、本番コードは「DomainException 系のみ受け付ける」と明示でき、フォールバックは「DomainException のサブクラスだが error_code を持たないレガシーな例外」用の最小限のフォールバックに留められます。

### 推奨する修正

1. **本番コード**
   - `create_from_domain_exception` の先頭で `if not isinstance(domain_exception, DomainException): raise TypeError("domain_exception must be a DomainException")` を入れる。
   - `error_code` の取得は `getattr(domain_exception, "error_code", domain_class_name.upper())` のままでよいが、コメントは「DomainException のサブクラスが error_code を定義していない場合のフォールバック」に限定して記載する。
   - これにより、モックで誤って通常の Exception を渡したテストは失敗し、テストの誤りに気づけます。

2. **テスト**
   - ApplicationExceptionFactory を利用しているテストで、DomainException のサブクラスでない例外を渡している箇所があれば、**DomainException を継承したテスト用例外** に差し替える。
   - それにより「想定外の型が渡ったときは TypeError」もテストで検証できます。

結論として、**「モックのためのフォールバック」を本番コードに含めるのではなく、テスト側で渡す型を DomainException 系に揃えるべき**であり、そのうえで本番コードは「DomainException 以外は受け付けない」と明示する実装にするのがよいと考えます。
