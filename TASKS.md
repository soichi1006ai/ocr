# OCR Tool v2 — タスクリスト

> **対象読者**: Claude Code / Codex（実装担当）
> **作成日**: 2026-05-07
> **前提**: `ARCHITECTURE.md` を必ず先に読むこと

---

## 0. このドキュメントの使い方

- 各タスクは **1 issue → 1 branch → 1 PR** で実施する（マスターSの規律）
- フェーズ単位で順序を守る（フェーズ1完了前にフェーズ2に進まない）
- タスク完了時はチェックボックスを `[x]` に更新し、`PROGRESS.md` の作業ログにも記録
- 受け入れ基準（acceptance criteria）を満たさないと完了とみなさない
- 不明点は ARCHITECTURE.md に立ち戻る、それでも不明なら作業を止めて確認

---

## 全体スケジュール（目安・品質優先のため柔軟）

| フェーズ | 内容 | 想定期間 | 状態 |
|---|---|---|---|
| 0 | 準備・ブランチ戦略決定 | 0.5週 | ✅ |
| 1 | ドメイン知識ベース構築 | 2週 | ⬜ |
| 2 | エンジン抽象化レイヤー | 1週 | ⬜ |
| 3 | Claude エンジン全面リプレイス | 3週 | ⬜ |
| 4 | パイプライン構築 | 2週 | ⬜ |
| 5 | ハイブリッドエンジン実装 | 2週 | ⬜ |
| 6 | UI 統合 | 1週 | ⬜ |
| 7 | 旧コード整理・ドキュメント | 1週 | ⬜ |
| **合計** | | **12.5週** | |

実装は別途とのことなので、本タスクリストは Claude Code への発注書として機能する。

---

# フェーズ 0: 準備（0.5週）

## T0.1: ブランチ戦略の確定とリリース計画✅ 完了 (2026-05-07)

**目的**: v1 と v2 が混在するリポジトリで安全に開発を進める

**タスク**:
- [x] `main` ブランチを v1 の最終形としてフリーズ（タグ `v1.0.0` を付与）
- [x] `v2-dev` ブランチを切る（v2 開発の統合先）
- [x] 各タスクは `feature/v2-tXX-名前` 形式のブランチで実施
- [x] PR は `v2-dev` に向ける、`main` にはマージしない
- [ ] 全フェーズ完了後にまとめて `v2-dev` → `main` にマージし `v2.0.0` タグ

**受け入れ基準**:
- `git tag v1.0.0` が main の最新コミットに付いている ✅
- `v2-dev` ブランチが GitHub に存在する ✅

---

## T0.2: 環境変数とシークレット管理 ✅ 完了 (2026-05-07)

**目的**: Claude API キーの安全な管理を確立

**タスク**:
- [x] `.env.example` を作成（`ANTHROPIC_API_KEY=` の雛形）
- [x] `.gitignore` に `.env` を追加
- [x] `python-dotenv` を `requirements-cloud.txt` に追加
- [ ] README に「API キー設定方法」セクション追加（T0.3完了後にまとめて更新）
- [ ] Anthropic Console で月額使用上限を設定（推奨 $50/月、運用実績で調整）

**受け入れ基準**:
- `.env` がリポジトリに含まれていない ✅
- `.env.example` を参照すれば誰でもセットアップできる ✅

---

## T0.3: requirements の3分割 ✅ 完了 (2026-05-07)

**目的**: モードごとに依存を分離して環境構築を軽量化

**タスク**:
- [x] `requirements.txt`: 全モード共通の最小依存（Pillow, pdf2image, openpyxl など）
- [x] `requirements-cloud.txt`: `anthropic`, `python-dotenv`, `tenacity`
- [x] `requirements-local.txt`: `paddleocr==2.7.3`, `paddlepaddle==2.6.2`, `numpy<2`, `opencv-python`
- [ ] README に「軽量インストール（クラウドのみ）」「フルインストール」の手順を分けて記載

**受け入れ基準**:
- `pip install -r requirements.txt -r requirements-cloud.txt` だけでクラウドモードが動く ✅
- `pip install -r requirements.txt -r requirements-local.txt` で従来環境 ✅

---

# フェーズ 1: ドメイン知識ベース構築（2週）

> **このフェーズの重要性**: 全エンジン・全プロンプト・全検証ロジックの土台。ここをサボると後段が全部崩れる。

## T1.1: knowledge/kanshi.json — 干支60組

**タスク**:
- [ ] 60組すべてを ARCHITECTURE.md §5.1 のスキーマで作成
- [ ] `index`, `kanji`, `yomi`, `kan`, `shi`, `gogyou`, `common_misreads` 全て埋める
- [ ] `common_misreads` は最低限、訓練データの誤認識傾向から推定（埋まっていなくても初期値は OK）
- [ ] JSON Schema を `knowledge/schemas/kanshi.schema.json` に定義
- [ ] バリデーションテスト `tests/test_knowledge_kanshi.py` を作成

**受け入れ基準**:
- 60組すべてのエントリがある
- JSON Schema 検証がパスする
- ユニットテストがパスする

---

## T1.2: knowledge/gengou.json — 元号一覧

**タスク**:
- [ ] 江戸時代の主要元号を網羅（正保・慶安・承応・明暦・万治・寛文・延宝・天和・貞享・元禄・宝永・正徳・享保・元文・寛保・延享・寛延・宝暦・明和・安永・天明・寛政・享和・文化・文政・天保・弘化・嘉永・安政・万延・文久・元治・慶応）
- [ ] 明治・大正・昭和・平成・令和も含める（暦表で使われるため）
- [ ] 各元号の `start_year`, `end_year`, `common_variants`, `common_misreads` を埋める
- [ ] JSON Schema 定義
- [ ] バリデーションテスト

**受け入れ基準**:
- 江戸時代の元号が漏れなく入っている
- 西暦範囲が時系列で重複・空白なく連続している
- JSON Schema 検証がパスする

---

## T1.3: knowledge/kyuusei.json — 九星

**タスク**:
- [ ] 一白〜九紫の9種類を定義
- [ ] 「日月火水木金土」の単位対応表も含める
- [ ] 表記揺れ（一白水星 / 一白）に対応

**受け入れ基準**:
- 9種類すべてがある
- 暦表サンプルの全九星表記をカバーできる

---

## T1.4: knowledge/kyuujitai.json — 旧字体マッピング

**タスク**:
- [ ] 江戸時代古文書で頻出する旧字体を最低 50 字収録（國/国, 學/学, 經/経, 體/体 など）
- [ ] 「異体字を正字へ」「旧字体を新字体へ」の方向を明示
- [ ] OCR 補正で使う `from → to` マッピング形式

**受け入れ基準**:
- 50字以上収録
- 暦表 PDF 11ファイルでの誤認識パターンを反映

---

## T1.5: knowledge/loader.py — 読み込みレイヤー

**タスク**:
- [ ] `lru_cache` で各 JSON をメモリキャッシュ
- [ ] `format_kanshi_for_prompt()` などプロンプト用整形関数
- [ ] `validate_kanshi_sequence(items: list[str]) -> bool` などの検証用関数
- [ ] ユニットテスト

**受け入れ基準**:
- 全 JSON が `loader.py` 経由でロードできる
- プロンプト整形関数の出力が読みやすい
- ユニットテストカバレッジ 90% 以上

---

# フェーズ 2: エンジン抽象化レイヤー（1週）

## T2.1: engines/base.py — OCREngine Protocol

**タスク**:
- [ ] `OCREngine` Protocol 定義（ARCHITECTURE.md §2.3）
- [ ] `ExtractionResult`, `PageResult`, `Block` データクラス定義
- [ ] `DocumentType` Enum 定義（`koyomi`, `daichou`, `honbun`, `auto`）
- [ ] エンジン共通のリトライロジック `BaseEngine.retry_with_backoff()` 抽象実装

**受け入れ基準**:
- 型チェック（mypy）がパスする
- runtime_checkable で `isinstance(engine, OCREngine)` が動く

---

## T2.2: 既存エンジンの Protocol 適合

**タスク**:
- [ ] `text_extractor.py` のロジックを `engines/paddle_engine.py` に移植
- [ ] `OCREngine` Protocol を実装
- [ ] 既存の `OCRPageResult` から新しい `PageResult` への変換ヘルパ
- [ ] 既存テストが通ることを確認

**受け入れ基準**:
- `paddle_engine.PaddleEngine().extract(...)` が動く
- 既存 CLI（`ocr.py --engine paddleocr`）が動作継続

---

# フェーズ 3: Claude エンジン全面リプレイス（3週）

## T3.1: prompts/ ディレクトリと loader

**タスク**:
- [ ] `prompts/loader.py` 実装（ARCHITECTURE.md §6.2）
- [ ] `prompts/classify.md` 作成（文書種別判定用）
- [ ] `prompts/koyomi.md` 作成（ARCHITECTURE.md §6.1 ベース）
- [ ] `prompts/daichou.md` 作成（台帳用、暦表ベースに調整）
- [ ] `prompts/honbun.md` 作成（本文用、汎用テキスト抽出）
- [ ] `prompts/verify_koyomi.md` 作成（検証 NG 時の再抽出用）
- [ ] テスト：`load_prompt("koyomi")` がドメイン知識を正しく注入できる

**受け入れ基準**:
- 各プロンプトが実際の暦表サンプルで意図通りの構造化出力を生成する（ノートブック等で目視確認）
- テンプレート展開が正しく動く

---

## T3.2: engines/claude_engine.py 全面書き直し

**タスク**:
- [ ] 旧 `claude_engine.py` を `_legacy_claude_engine.py` にリネーム保管（参考用）
- [ ] 新 `claude_engine.py` を OCREngine Protocol で実装
- [ ] **モデル**: `claude-opus-4-7` をデフォルト（マスターS指定）
- [ ] **Extended Thinking** 有効化（`thinking={"type": "enabled", "budget_tokens": 4000}`）
- [ ] **max_tokens**: 8192（構造化 JSON 出力に十分な余裕）
- [ ] 画像エンコード: 既存の `_b64_image()` ロジックを継承（解像度保持・JPEG変換）
- [ ] 文書種別ごとのプロンプト切り替え
- [ ] ドメイン知識を context として注入
- [ ] JSON 出力をパース→`PageResult` に変換
- [ ] `tenacity` でリトライロジック（指数バックオフ、3回まで）
- [ ] APIエラー時のグレースフル処理（部分結果でも返す）

**受け入れ基準**:
- 暦表サンプル（今回の `doc00794320260507095906.pdf`）で構造化 JSON が抽出できる
- Web版 Claude と同等の精度（CER < 1%）
- API エラー時もクラッシュしない

---

## T3.3: pipeline/classifier.py — 文書種別判定

**タスク**:
- [ ] Claude API（軽量モデル: Sonnet 4.6）でページ画像から文書種別を判定
- [ ] `classify(image_path: Path) -> tuple[DocumentType, float]` 関数
- [ ] 信頼度が低い場合（< 0.7）はユーザーに確認を求める仕組み
- [ ] キャッシュ機構（同じ PDF を再処理する場合）

**受け入れ基準**:
- 暦表 / 台帳 / 本文の3種別を90%以上の精度で判別
- 1ページあたり約 $0.005 以下のコスト

---

## T3.4: pipeline/splitter.py — 見開き分割

**タスク**:
- [ ] 画像のアスペクト比から見開きスキャン検出（横/縦 > 1.3 で見開き判定）
- [ ] OpenCV のヒストグラム解析で中央の綴じ目位置を精密検出
- [ ] 左右に分割（読み順は文書種別による：縦書きなら右→左）
- [ ] 元のページ番号を保持しつつ `page_001_R.png`, `page_001_L.png` 形式で保存

**受け入れ基準**:
- 暦表サンプル（見開き）が正しく左右分割される
- 単一ページ（横/縦 ≤ 1.3）はそのまま通す
- ページ番号の対応が崩れない

---

# フェーズ 4: パイプライン構築（2週）

## T4.1: pipeline/extractor.py — メインオーケストレーター

**タスク**:
- [ ] `Extractor.run(pdf_path, mode, doc_type)` のトップレベル関数
- [ ] フロー: PDF→PNG→Splitter→Classifier→Engine→Validator→Corrector→Export
- [ ] モード別のエンジン選択ロジック
- [ ] 進捗コールバック（`on_progress(stage, current, total)`）
- [ ] エラーハンドリング（ページ単位で継続）

**受け入れ基準**:
- 3モード全てで暦表サンプルを処理できる
- 進捗がリアルタイムで取れる
- 1ページのエラーが全体を停止させない

---

## T4.2: pipeline/validator.py — 出力検証

**タスク**:
- [ ] `validate_koyomi(result)`: 日数チェック + 干支60組連続性 + 九星循環
- [ ] `validate_daichou(result)`: 元号時系列、人名一貫性
- [ ] `validate_honbun(result)`: 基本のみ（空でないか、文字化けがないか）
- [ ] エラー一覧を返す（`list[ValidationError]`）
- [ ] テスト: 既知の不正データで適切にエラー検出

**受け入れ基準**:
- 暦表で日数/干支/九星の3軸検証が動く
- 既知の正解データでエラー検出 0
- 既知の誤りデータでエラー検出 100%

---

## T4.3: pipeline/corrector.py — 辞書補正

**タスク**:
- [ ] 既存の `text_extractor.py` の干支補正ロジックを移植
- [ ] `knowledge/` の各 JSON を活用するように書き換え
- [ ] 旧字体→新字体変換は **オプショナル**（ユーザーが選択可能）
- [ ] 補正前後の差分ログを取得（後で精度評価に使う）

**受け入れ基準**:
- 既存の補正テストケースが全てパス
- 旧字体変換のオン/オフが切り替え可能

---

## T4.4: pipeline/preprocessor.py — 既存コード整理

**タスク**:
- [ ] `image_preprocessor.py` のロジックを移動
- [ ] `pdf_converter.py` のロジックを統合
- [ ] 関数名・引数を統一（`preprocess(image: Path) -> Path`）
- [ ] PaddleOCR 専用の前処理（傾き補正・二値化）と Claude 用の前処理（リサイズのみ）を分離

**受け入れ基準**:
- 既存の前処理テストが全てパス
- Claude エンジンと Paddle エンジンで適切な前処理が呼ばれる

---

## T4.5: 検証 NG 時の自動再抽出

**タスク**:
- [ ] `extractor.py` に `extract_with_retry()` を実装
- [ ] バリデーションエラーをプロンプトに含めて再抽出（最大2回）
- [ ] 再抽出時は `prompts/verify_*.md` を使用
- [ ] 最終的に NG でも結果を返す（エラーフラグ付き）

**受け入れ基準**:
- 暦表サンプルで意図的に誤らせた場合、再抽出で修正される
- 最大リトライ回数を超えてもクラッシュしない

---

# フェーズ 5: ハイブリッドエンジン実装（2週）

## T5.1: PaddleOCR の信頼度取得

**タスク**:
- [x] `paddle_engine.py` から各セル/行の confidence スコアを取得
- [x] `PageResult.blocks[].confidence` に保持（行単位で 1 Block）
- [x] テスト: 信頼度が常に 0〜1 の範囲

**受け入れ基準**:
- すべてのブロックに confidence が付与される
- 既知の難読箇所で confidence が低くなる

---

## T5.2: engines/hybrid_engine.py 実装

**タスク**:
- [x] PaddleEngine と ClaudeEngine を内部で使用
- [x] フロー: Paddle で全体抽出 → confidence 評価 → 低信頼ブロックのみ Claude に再質問
- [x] 閾値 `confidence_threshold` をコンストラクタで受け取る（デフォルト 0.85）
- [x] 低信頼ブロックが含まれるページを Claude に再抽出（画像全体）
- [x] 結果をマージして PageResult を返す

**受け入れ基準**:
- 暦表サンプルで Paddle 単独より精度が向上
- API コストが精度モードの 1/5 以下

---

## T5.3: tests/accuracy_eval.py — 精度評価フレームワーク

**タスク**:
- [x] `tests/ground_truth/` に正解データを配置（暦表3件、台帳3件）
- [x] CER（Character Error Rate）計算ロジック
- [x] 構造化データの一致率計算（JSON diff ベース）
- [x] モード別精度比較レポート出力（Markdown / JSON 形式）
- [ ] CI で自動実行（コスト発生するためマニュアル実行 or 月1回）

**受け入れ基準**:
- 3モードの精度を一覧で比較できる
- レポートが Markdown / JSON で出力できる
- 目標 CER（ARCHITECTURE.md §10.2）を達成しているか判定できる

---

# フェーズ 6: UI 統合（1週）

## T6.1: launcher.py — モード選択 UI

**タスク**:
- [ ] 設定パネルに「モード」ラジオボタン追加（精度 / ハイブリッド ★ / オフライン）
- [ ] 「文書種別」ラジオボタン追加（自動 / 暦表 / 台帳 / 本文）
- [ ] モードに応じて関連設定の表示/非表示
- [ ] ハイブリッドモードの「信頼度閾値」スライダー
- [ ] 精度モードのモデル選択（Opus 4.7 / Sonnet 4.6）

**受け入れ基準**:
- UI から3モードすべて切り替えられる
- 不要な設定項目が適切に隠れる

---

## T6.2: launcher.py — 進捗表示の高度化

**タスク**:
- [ ] パイプラインの各段階を進捗バーに反映（分割 → 分類 → 抽出 → 検証 → 出力）
- [ ] エンジン別のサブ進捗（ハイブリッド時は Paddle と Claude の両方）
- [ ] コスト累計表示（Claude API 使用時）

**受け入れ基準**:
- 処理がどの段階かリアルタイムで分かる
- API コスト累計が処理中も見える

---

## T6.3: launcher.py — 結果プレビューと再実行

**タスク**:
- [ ] 完了後に結果ファイル（JSON / XLSX / DOCX）を開くボタン
- [ ] 検証エラーがあった場合の警告表示
- [ ] 「再実行」「別モードで再実行」ボタン

**受け入れ基準**:
- 結果がワンクリックで開ける
- 検証エラーがあっても作業を続行できる

---

# フェーズ 7: 旧コード整理・ドキュメント（1週）

## T7.1: 旧コードの削除/格下げ

**タスク**:
- [ ] `_legacy_claude_engine.py` を削除（v2 で完全置換済み）
- [ ] `frame_detector.py` / `layout_analyzer.py` を `engines/paddle_internal/` に移動
- [ ] `table_extractor.py` のロジックを `exporters/xlsx_exporter.py` と `engines/paddle_engine.py` に分離
- [ ] 不要なテストコードの削除

**受け入れ基準**:
- ルートディレクトリがクリーン（v1 ファイルが散在しない）
- 既存の Paddle モードが動作継続

---

## T7.2: README.md 全面書き換え

**タスク**:
- [ ] v2 の機能紹介
- [ ] 3モードの使い分け表
- [ ] セットアップ手順（クラウドのみ / フル）
- [ ] よくある質問（コスト、精度、機密文書）
- [ ] v1 からの移行ガイド
- [ ] スクリーンショット（launcher.py の新 UI）

**受け入れ基準**:
- 新規ユーザーが README だけでセットアップできる
- v1 ユーザーが移行できる情報がある

---

## T7.3: PROGRESS.md 最終更新

**タスク**:
- [ ] フェーズ6（Claude APIエンジン精度チューニング）→ ✅ 完了に更新
- [ ] 新フェーズ「v2 リアーキテクチャ」を追加して全タスクの完了状況を記録
- [ ] 作業ログに本リアーキテクチャを追記

**受け入れ基準**:
- 全フェーズの状態が最新
- 過去の作業ログが残っている

---

## T7.4: ARCHITECTURE.md の追補

**タスク**:
- [ ] 実装中に発見した設計上の決定を「決定ログ（ADR）」セクションに追加
- [ ] 当初設計から変更した点とその理由を記録
- [ ] 将来の拡張案（追加文書種別、別モデル対応など）を「Future Work」セクションに記載

**受け入れ基準**:
- ADR が最低 5 件記録されている
- 将来の改善方針が明確

---

## T7.5: リリース

**タスク**:
- [ ] `v2-dev` → `main` のマージ PR 作成
- [ ] 全テスト通過確認
- [ ] `v2.0.0` タグ付与
- [ ] GitHub Releases にリリースノート作成（変更点・移行ガイド・既知の問題）

**受け入れ基準**:
- main に v2 がマージされている
- v2.0.0 タグが付いている
- GitHub Releases に記載がある

---

# 付録 A: タスク間の依存関係

```
T0.1 → T0.2 → T0.3
                ↓
T1.1 ─┐
T1.2 ─┼→ T1.5 → T2.1 → T2.2 → T3.1 → T3.2 → T3.3 → T3.4
T1.3 ─┤                                              ↓
T1.4 ─┘                                              ↓
                                                     ↓
                              T4.1 ← T4.4 ← T4.5 ← T4.2 ← T4.3
                                ↓
                              T5.1 → T5.2 → T5.3
                                              ↓
                              T6.1 → T6.2 → T6.3
                                              ↓
                              T7.1 → T7.2 → T7.3 → T7.4 → T7.5
```

# 付録 B: チェックリスト（各タスク開始時）

- [ ] ARCHITECTURE.md の関連セクションを再読
- [ ] feature ブランチを切る（`feature/v2-tXX-名前`）
- [ ] テストファースト：受け入れ基準をテストコードに落とす
- [ ] 実装
- [ ] テストパス確認
- [ ] PR 作成（`v2-dev` 向け）
- [ ] レビュー（マスターS or 自己レビュー）
- [ ] マージ
- [ ] PROGRESS.md 更新
- [ ] このファイルのチェックボックスを `[x]` に

---

# 付録 C: Claude Code への指示テンプレート

各タスクを Claude Code に発注する際は、以下のテンプレートを使う：

```
@claude-code

タスク: TX.Y（タスクID）
参照: ARCHITECTURE.md §X.Y、TASKS.md TX.Y

実装内容:
（TASKS.md の「タスク」項目をコピペ）

受け入れ基準:
（TASKS.md の「受け入れ基準」をコピペ）

ブランチ: feature/v2-tXY-名前
PR向け先: v2-dev

開始時にやること:
1. ARCHITECTURE.md の関連セクションを読む
2. 既存の関連コードを確認
3. テストを先に書く
4. 実装
5. PR 作成

完了報告:
- 変更ファイル一覧
- 受け入れ基準のチェック結果
- PROGRESS.md の更新内容
```

---

# 付録 D: 想定外の事態への対応

| 事態 | 対応 |
|---|---|
| ドメイン知識 JSON の作成中に未知の干支表記を発見 | `common_misreads` に追加、JSON Schema は維持 |
| Claude API のレスポンス形式が変わった | `claude_engine.py` のパーサーのみ更新、他レイヤーは無影響 |
| PaddleOCR が Python 3.11 で動かなくなった | オフラインモードを `--mode offline=ndl` に切替（NDL OCR 経由） |
| 暦表11ファイルで精度が目標に届かない | プロンプトの `common_misreads` セクションを充実、Extended Thinking の budget を増やす |
| API コストが想定を超える | Anthropic Console で月額上限を厳しめに設定、ハイブリッドモードの閾値を上げる |

---

以上。このタスクリストに従って実装を進めれば、品質を担保しつつ12〜13週間で v2 が完成する。
