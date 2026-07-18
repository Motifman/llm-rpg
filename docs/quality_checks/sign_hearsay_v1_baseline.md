# sign_hearsay_v1: 看板を読んだ観測は P9 伝聞抽出に乗るか

## 背景

#714 で看板 (書き置き) primitive が入った。`examine` すると「『本文』 —
書き手名」形式の観測が読んだ本人に流れる。#714 の「マージ後の予定」で
「読んだ内容が書き手名つきの主張として伝聞 (HEARSAY) 抽出に乗るか」を
次の品質チェックで確認することになっていた。本ドキュメントはその確認結果。

## 結論

**静的には確実に乗る。プロンプトの指示文言は当初 (P9 導入時) 発話中心
だったため、看板を明示する 1〜2 行を追記した (本 PR で対応)。**

## 静的な確認 (コードで追跡した経路)

1. `src/ai_rpg_world/domain/world_graph/service/world_graph_effect_service.py`
   の `SHOW_PLAYER_TEXT` 分岐が `messages.append(f"『{text}』 — {author_name}")`
   を積む
2. `src/ai_rpg_world/application/world_graph/spot_interaction_application_service.py`
   が `result_message="；".join(result.messages)` として集約
3. `src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py`
   の `_interact` が `msg = "; ".join(result.messages)` を
   `LlmCommandResultDto.message` にする
4. `src/ai_rpg_world/application/llm/result_summary_builder.py` の
   `build_result_summary` が成功時に `dto.message` をそのまま
   `ActionResultEntry.result_summary` にする
5. `src/ai_rpg_world/application/llm/contracts/chunk_encoding.py` の
   `format_action_result_line_for_recent_events` が
   `[行動] {action_summary} → [結果] {result_summary}` の形で統一タイムライン
   (`unified_timeline`) の 1 行にする (`interact` は `omit_result_in_prompt`
   を立てないので省略されない)
6. `src/ai_rpg_world/application/llm/services/chunk_episode_draft_builder.py`
   がこの統一タイムラインを `SubjectiveEpisode.observed` にする
7. `src/ai_rpg_world/application/llm/services/episodic_chunk_subjective_fields.py`
   の `_format_draft_facts` が `observed` を P9 抽出 LLM の user prompt
   (`## ルール草案` 節) にそのまま出す

`tests/quality/test_sign_hearsay_v1.py` はこの経路をプロダクションコードの
文字列生成規則 (2 の `messages.append` 相当) をそのまま使って再現し、
実際に生成される prompt を `sign_hearsay_v1.prompt.txt` に dump している。
dump の `messages[1] role=user` の `observed (統一タイムライン)` と
`行動結果（ソース事実）` の両方に

```
『山頂への道は川沿い。乾いた枯れ葉は高地の泉の近くにある』 — カイ
```

がそのまま現れている。これは「コード変更なしで P9 抽出の入力に乗る」という
#714 の設計が実際に成立していることの回帰確認 (LLM は呼ばない静的確認)。

## LLM が実際に heard_claims として拾うかの判定

- **実 LLM での確認はできなかった**: このワークツリー / リポジトリに
  `.env` が存在せず、`OPENAI_API_KEY` 等の環境変数も未設定だったため、
  litellm 経由の実行は不可能だった。この確認だけは静的分析 + 目視判定に
  留まる (task の制約通り、限界として明記する)。
- 目視判定の根拠: `_HEARD_CLAIMS_INSTRUCTION` (伝聞抽出の指示文) は導入時
  (P9) から一貫して「この期間に他者が…**語った**主張」「誰の**発言**か」
  という発話中心の語彙で書かれていた。一方、看板の観測は
  - 引用記号が `『』` (発話は `「」`)
  - 語順が「本文 — 名前」(発話は「名前が動詞: 「本文」」)
  - 「語った」でも「言った」でもなく、読んだ本人の**行動結果**
    (`[結果] ...`) として現れる

  という、指示文の想定パターンと表層的に異なる形。名前と本文の紐付け自体は
  明確だが、指示が発話専用の語彙で閉じているため、「これも対象に含む」と
  明示しないと拾い漏れる (speaker が特定できず配列に入らない) リスクが
  ある、と判断した。

## 対応

`_HEARD_CLAIMS_INSTRUCTION` に次の 1 文を追記した (flag `HEARSAY_ENABLED`
が ON のときだけ append される節なので、既存の byte 不変保証には触れない):

> 看板や書き置きを読んだ観測 (「『本文』 — 書き手名」の形式) も、その書き手が
> 語った主張として同様に扱う。

既存テスト (`tests/application/llm/test_episodic_chunk_subjective_fields_hearsay.py`
等) はこの文言の exact match をしていないため regression なし。

## 残った限界

- 実 LLM (litellm 経由) での再生確認は API key 不在のため実施できなかった。
  次に API key が使える環境で本テストの `_StubSubjectivePort` を実 LLM 呼び出しに
  差し替え、`heard_claims` に `speaker="カイ"` が実際に返るかを確認するのが
  次の一歩 (v3_coop シナリオへの看板配置後の実 run 分析でも観察できる)。
- v3_coop シナリオに実際に看板オブジェクトを配置した run (#714 の
  「マージ後の予定」) での trace 分析はまだ行っていない。今回はエンジン側の
  経路確認のみ。
