# 進捗状況

> **作業再開時は必ずこのファイルを最初に読むこと。**
> 実装前に `ocr_tool_spec.md` も確認すること。

---

## 現在のフェーズ: フェーズ1（未着手）

### フェーズ一覧

| フェーズ | 内容 | 状態 |
|---|---|---|
| フェーズ1 | 基盤（環境・PDF変換） | ✅ 完了 |
| フェーズ2 | OCRコア（テキスト抽出） | 🔄 進行中 |
| フェーズ3 | 表認識 | 🔄 進行中 |
| フェーズ4 | CLI仕上げ | ⬜ 未着手 |
| フェーズ5 | UI（後日） | ⬜ 未着手 |

---

## タスク進捗

### フェーズ1 — 基盤（環境・PDF変換）
- [x] 必要ライブラリのインストール（paddlepaddle, paddleocr, pdf2image, Pillow, openpyxl, python-docx, opencv-python）
- [x] `brew install poppler` の確認
- [x] `pdf_converter.py` の実装（PDF → PNG画像の変換）
- [x] 複数ページPDFで変換動作確認

### フェーズ2 — OCRコア（テキスト抽出）
- [x] `text_extractor.py` の実装（PaddleOCRでテキスト抽出）
- [ ] 日英混在PDFでの精度確認
- [x] `result.txt` への出力（ページ番号付き）
- [x] コールバック引数 `on_progress` の実装

### フェーズ3 — 表認識
- [ ] `layout_analyzer.py` の実装（PP-Structureによるレイアウト解析）
- [ ] `table_extractor.py` の実装（表領域の認識・セル構造の抽出）
- [ ] `tables.xlsx` への出力（シート名: `table_ページ番号_表番号`）
- [ ] 実際のスキャンPDFで表認識の精度確認

### フェーズ4 — CLI仕上げ
- [ ] `ocr.py` の実装（エントリポイント・引数処理）
- [ ] オプション対応（`--output`, `--pages`, `--dpi`）
- [ ] エラーハンドリング（ファイル不存在・OCR失敗等）
- [ ] 進捗表示の実装（`[2/5] ページ 2 を処理中...`）
- [ ] `requirements.txt` の作成
- [x] `README.md` の作成

### フェーズ5 — UI（後日）
- [ ] UIフレームワークの選定（Streamlit等）
- [ ] ファイルアップロード画面の実装
- [ ] 進捗バーの実装（フェーズ2の `on_progress` を利用）
- [ ] 結果ダウンロード機能の実装

---

## 次のAIへの申し送り

- 作業開始前にこのファイルの「現在のフェーズ」と「タスク進捗」を確認すること
- タスク完了時はチェックボックスを `[x]` に更新し、作業ログに記録してからcommitすること
- 判明した注意点や設計上の決定事項は「技術メモ」セクションに追記すること
- フェーズ完了時はフェーズ一覧の状態を更新すること（⬜ → ✅）

---

## 技術メモ

_作業中に判明した注意点・設計決定・ハマりどころをここに記録する_

- `pdf2image` + `poppler` でページ単位変換を確認。複数ページPDFは `page_001.png` のようなゼロ埋め連番で保存する。
- ページ範囲指定は将来CLIで使えるよう `1,3-5` 形式まで先に実装済み。
- OCRエンジンは `PaddleOCREngine` で遅延初期化し、テスト時は差し替え可能な設計にした。
- 表抽出はまず PP-Structure の `res.html` を優先し、HTMLが無い場合だけ簡易な `res.text` フォールバックを使う。
- Word出力はページ単位で本文→表の順に並べ、ページ間に改ページを入れる。
- `--pages` 指定時も出力上のページ番号が元PDFのページ番号を保つように補正した。

---

## 作業ログ

| 日付 | 担当 | 内容 |
|---|---|---|
| 2026-05-05 | Claude（ベイダー） | 仕様書・タスクリスト・本ファイル作成、GitHubへpush |
| 2026-05-05 | DonCorleone | requirements.txt 追加、pdf_converter.py 実装、poppler確認 |
| 2026-05-05 | DonCorleone | text_extractor.py と ocr.py を追加し、result.txt 出力まで接続 |
| 2026-05-05 | DonCorleone | layout_analyzer.py / table_extractor.py を追加し、tables.xlsx 出力経路を接続 |
| 2026-05-05 | DonCorleone | docx_exporter.py を追加し、result.docx 出力経路を接続 |
| 2026-05-05 | DonCorleone | ページ番号補正を実装し、README.md を追加 |
