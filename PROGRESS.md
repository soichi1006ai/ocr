# 進捗状況

> **作業再開時は必ずこのファイルを最初に読むこと。**
> 実装前に `ocr_tool_spec.md` も確認すること。

---

## 現在のフェーズ: ✅ PaddleOCR 2.7.3 + Python 3.11 で動作確認完了

### フェーズ一覧

| フェーズ | 内容 | 状態 |
|---|---|---|
| フェーズ1 | 基盤（環境・PDF変換） | ✅ 完了 |
| フェーズ2 | OCRコア（テキスト抽出） | ✅ PaddleOCR 2.7.3 で実PDF動作確認済み |
| フェーズ3 | 表認識 | ✅ frame_detector で実PDF動作確認済み |
| フェーズ4 | CLI仕上げ | ✅ 完了 |
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
- [x] 日英混在PDFでの精度確認（doc00792520260430181242.pdf で動作確認）
- [x] `result.txt` への出力（ページ番号付き）
- [x] コールバック引数 `on_progress` の実装

### フェーズ3 — 表認識
- [x] `layout_analyzer.py` の実装（PP-Structureによるレイアウト解析）
- [x] `table_extractor.py` の実装（表領域の認識・セル構造の抽出）
- [x] `tables.xlsx` への出力（シート名: `table_ページ番号_表番号`）
- [x] 実際のスキャンPDFで表認識の精度確認（doc00792520260430181242.pdf: 30フレーム候補, 18テーブル候補検出）

### フェーズ4 — CLI仕上げ
- [x] `ocr.py` の実装（エントリポイント・引数処理）
- [x] オプション対応（`--output`, `--pages`, `--dpi`）
- [x] エラーハンドリング（ファイル不存在・OCR失敗等）
- [x] 進捗表示の実装（`[2/5] ページ 2 を処理中...`）
- [x] `requirements.txt` の作成
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

- **EasyOCR移行（2026-05-06）**: paddlepaddle==2.6.2 が Python 3.13 環境でインストール不可（3.0.0 のみ対応）なため、EasyOCR 1.7.x に切り替えた。
  - EasyOCR は Python 3.9+ / macOS / CPU 環境で動作確認済み。
  - `OCREngine` Protocol はそのまま維持し、`PaddleOCREngine` → `EasyOCREngine` に差し替え。
  - EasyOCR の `readtext()` は `(bbox, text, conf)` リストを返すため、`_flatten_ocr_result` と互換性のある形式にラップして渡す。
  - `layout_analyzer.py` から `PPStructureEngine`（PaddleOCR依存）を除去し、`FrameDetectorEngine`（frame_detector.py）に完全移行。レイアウト解析は枠検出ベースのみになった。
  - `table_extractor.py` は `table_frame_candidate` リージョンも処理対象に追加（旧: `table` のみ）。
  - **numpy 競合**: torch 2.2.x が numpy 1.x でコンパイルされているため、numpy<2 が必須。requirements.txt に `numpy>=1.24,<2` を記載。
  - 動作確認: `doc00792520260430181242.pdf`（日本語縦書き・英語混在）で result.txt / tables.xlsx / result.docx の3出力生成を確認。
- **PaddleOCR 2.7.3 に戻した（2026-05-06）**: EasyOCRでは歴史的日本語（元号・干支）の認識精度が低く文字が断片的だった。Python 3.11 に切り替えたことで paddlepaddle==2.6.2 のインストールが可能になり、PaddleOCR 2.7.3 に戻した。
  - **Python バージョン: 3.11.9**（pyenv local で設定済み）。torch/EasyOCR は Python 3.13 未対応のため注意。
  - PaddleOCR 2.7.3 では元号（正保・康熙・寛文など）や干支が正しく認識され、EasyOCRより精度が大幅に向上。
  - `text_extractor.py` の `EasyOCREngine` → `PaddleOCREngine`（2.x API: `ocr(img, cls=True)`）に差し替え済み。
  - 動作確認: `doc00792520260430181242.pdf` で1ページを数分以内に処理完了、result.txt / tables.xlsx / result.docx の3出力生成を確認。
- **表認識の改善（2026-05-06）**:
  - `frame_detector.py` に `detect_grid_lines()` を追加。罫線の水平・垂直位置を検出してセル境界を定義。
  - `table_extractor.py` でグリッド線が十分取れた場合はセル単位クロップOCR（`_ocr_grid_cells`）、取れない場合はyクラスタリングfallback（`_ocr_bbox_clustering`）に切り替え。
  - OCRエンジンを1回だけ初期化して全テーブルで使い回すよう改善（速度改善）。
  - 閾値: 水平0.18、垂直0.28、最小セル間隔 h=18px / v=22px（文字ストロークとの混同防止）。
  - **残課題**: 密なグリッドの文書では複数セルが1テキスト検出にまとめられてしまうケースあり。より高精度な解決にはキャラクター単位OCRまたは専用モデルが必要。
- **ndlocr-lite エンジン追加（2026-05-06）**: 国立国会図書館公開の古典日本語OCR専用ツール。
  - `ndlocr_engine.py` を新規作成。サブプロセス呼び出しで numpy 競合を回避。
  - `ocr.py` に `--engine [paddleocr|ndlocr]` オプションを追加。UIでの切り替えに対応。
  - ndlocr-liteの専用venvは `/tmp/ndl_test/` （恒久化する場合は `~/.ndl_venv/` 推奨）。
  - **速度**: 4.5秒/ページ（paddleocrより高速）。
  - **精度**: 元号・干支・縦書きの認識精度がpaddleocrより明確に優れている。
  - 使い方: `python ocr.py input.pdf --engine ndlocr`

- `pdf2image` + `poppler` でページ単位変換を確認。複数ページPDFは `page_001.png` のようなゼロ埋め連番で保存する。
- ページ範囲指定は将来CLIで使えるよう `1,3-5` 形式まで先に実装済み。
- OCRエンジンは `PaddleOCREngine` で遅延初期化し、テスト時は差し替え可能な設計にした。
- 表抽出はまず PP-Structure の `res.html` を優先し、HTMLが無い場合だけ簡易な `res.text` フォールバックを使う。
- Word出力はページ単位で本文→表の順に並べ、ページ間に改ページを入れる。
- `--pages` 指定時も出力上のページ番号が元PDFのページ番号を保つように補正した。
- OCR失敗はページ単位で警告して継続し、成功ページだけ `result.txt` / `result.docx` に残す。
- レイアウト解析失敗もページ単位で警告して継続し、抽出できた表だけ `tables.xlsx` / `result.docx` に残す。
- fake `paddleocr` モジュールを使ったCLIスモークテストで `result.txt` / `tables.xlsx` / `result.docx` の生成を確認した。
- **PaddleOCRは2.7.3に固定**: 3.x は API 変更が大きく、CPU環境で極端に遅い問題があるため、このリポジトリでは `paddleocr==2.7.3` を正とする。
  - `text_extractor.py` は 2.x API（`ocr(..., cls=True)`）に戻した。
  - `paddlepaddle==2.6.2` / `numpy<2` も固定し、OpenCV ABI不整合を避ける。
  - `layout_analyzer.py` は PP-Structure の制約に合わせて `lang="ch"` を使う。
  - 本文OCRでは前処理（傾き補正・コントラスト強調・二値化）を挟み、薄い印字や小さい文字の改善を狙う。
  - 干支・元号に寄った辞書補正を追加し、資料群固有の誤認識を減らす。
  - 縦書きページでは列分割して右→左に統合する。
  - 追加の枠検出で矩形領域を拾い、線分密度と交点数から表らしさを判定する。
  - 次は実スキャンPDFで再確認する。

---

## 作業ログ

| 日付 | 担当 | 内容 |
|---|---|---|
| 2026-05-05 | Claude（ベイダー） | 仕様書・タスクリスト・本ファイル作成、GitHubへpush |
| 2026-05-05 | DonCorleone | requirements.txt 追加、pdf_converter.py 実装、poppler確認 |
| 2026-05-05 | Claude（ベイダー） | 実スキャンPDFでテスト実行 → PaddleOCR 3.x のAPI変更・速度問題を発見、text_extractor.py を3.x対応に修正するも速度問題は未解決 |
| 2026-05-05 | DonCorleone | PaddleOCR 2.7.3 前提に戻し、README / requirements / text_extractor を修正 |
| 2026-05-05 | DonCorleone | paddlepaddle/numpy を固定し、PP-Structure を ch モデルへ切り替え |
| 2026-05-05 | DonCorleone | 本文OCRの前処理（傾き補正・強調・二値化）を追加 |
| 2026-05-05 | DonCorleone | 干支・元号向けの辞書補正を追加 |
| 2026-05-05 | DonCorleone | 縦書き列分割OCRを追加 |
| 2026-05-05 | DonCorleone | 枠検出と表らしさ判定のヒューリスティックを追加 |
| 2026-05-06 | DonCorleone | EasyOCRに切り替え（paddlepaddle 2.x が Python 3.13 未対応のため） |
| 2026-05-06 | Claude（ベイダー） | Python 3.11.9 に切り替え、PaddleOCR 2.7.3 に戻す。実PDFで動作確認完了（元号・干支の認識OK） |
| 2026-05-06 | DonCorleone | PaddleOCR → EasyOCR に全面移行: requirements.txt / text_extractor.py / layout_analyzer.py / table_extractor.py / ocr.py を更新 |
| 2026-05-06 | DonCorleone | numpy<2 制約を確認・設定（torch との ABI 競合対応） |
| 2026-05-06 | DonCorleone | doc00792520260430181242.pdf（日本語縦書き・英語混在）で動作確認完了。result.txt / tables.xlsx / result.docx 生成を確認 |
| 2026-05-05 | DonCorleone | text_extractor.py と ocr.py を追加し、result.txt 出力まで接続 |
| 2026-05-05 | DonCorleone | layout_analyzer.py / table_extractor.py を追加し、tables.xlsx 出力経路を接続 |
| 2026-05-05 | DonCorleone | docx_exporter.py を追加し、result.docx 出力経路を接続 |
| 2026-05-05 | DonCorleone | ページ番号補正を実装し、README.md を追加 |
| 2026-05-05 | DonCorleone | OCR失敗ページをスキップ継続する挙動に修正 |
| 2026-05-05 | DonCorleone | レイアウト失敗ページもスキップ継続に修正し、CLIスモークテストで出力一式を確認 |
