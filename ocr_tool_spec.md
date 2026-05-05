# OCRツール 実装指示書

## 概要

スキャンしたPDFから日本語・英語混在のテキストを抽出し、表（テーブル）はExcel形式で出力するPythonツールを作成する。
すべて無料・ローカルで動作すること（有料APIは使用しない）。

---

## 実行環境

- OS: macOS
- 言語: Python 3.x（インストール済み）
- パッケージ管理: pip

---

## 使用ライブラリ（すべて無料・OSS）

| ライブラリ | 用途 | インストールコマンド |
|---|---|---|
| `paddlepaddle` | PaddleOCRの実行エンジン | `pip install paddlepaddle` |
| `paddleocr` | OCR本体（日英対応） | `pip install paddleocr` |
| `pdf2image` | PDF→画像変換 | `pip install pdf2image` |
| `Pillow` | 画像処理 | `pip install Pillow` |
| `openpyxl` | Excel出力 | `pip install openpyxl` |
| `opencv-python` | 画像前処理 | `pip install opencv-python` |

macOSでpdf2imageを使うには別途Homebrewで`poppler`が必要:
```bash
brew install poppler
```

---

## 機能要件

### 1. PDF読み込み
- スキャンされたPDF（画像PDF）を入力として受け取る
- 複数ページに対応すること
- PDFを1ページずつ画像（PNG/JPG）に変換して処理する

### 2. レイアウト解析
- PaddleOCRの **PP-Structure** を使用してページのレイアウトを解析する
- ページ内の各領域を以下に分類する:
  - `table`（表）
  - `text`（通常テキスト）
  - `title`（見出し）
  - `figure`（図）

### 3. テキスト抽出（表以外）
- `text` / `title` 領域はOCRでテキストを抽出する
- 日本語・英語が混在していても正しく認識すること
- PaddleOCRの言語設定: `lang='japan'`（日英混在対応）

### 4. 表認識・出力
- `table` 領域はPP-Structureのテーブル認識機能で処理する
- 行・列のセル構造を保持すること
- 出力形式:
  - **Excel (.xlsx)**: 表ごとに1シートとして保存
  - シート名は `table_ページ番号_表番号`（例: `table_1_1`）

### 5. 出力ファイル
```
output/
├── result.txt          # 全ページのテキスト（ページ番号付き）
├── tables.xlsx         # 全ページの表をシートごとに格納
└── pages/
    ├── page_001.png    # 変換済み画像（中間ファイル）
    └── page_002.png
```

---

## 処理フロー

```
入力: sample.pdf
    ↓
[1] PDF → 画像変換（pdf2image）
    ↓
[2] 各ページにPP-Structureを適用（レイアウト解析）
    ↓
[3] 領域ごとに分岐
    ├── text/title → PaddleOCR → result.txt に追記
    └── table      → テーブル認識 → tables.xlsx に追記
    ↓
出力: result.txt + tables.xlsx
```

---

## 開発タスクリスト（フェーズ別）

### フェーズ1 — 基盤（環境・PDF変換）
- [ ] 必要ライブラリのインストール（paddlepaddle, paddleocr, pdf2image, Pillow, openpyxl, opencv-python）
- [ ] `brew install poppler` の確認
- [ ] `pdf_converter.py` の実装（PDF → PNG画像の変換）
- [ ] 複数ページPDFで変換動作確認

### フェーズ2 — OCRコア（テキスト抽出）
- [ ] `text_extractor.py` の実装（PaddleOCRでテキスト抽出）
- [ ] 日英混在PDFでの精度確認
- [ ] `result.txt` への出力（ページ番号付き）
- [ ] コールバック引数 `on_progress` の実装

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
- [ ] `README.md` の作成

### フェーズ5 — UI（後日）
- [ ] UIフレームワークの選定（Streamlit等）
- [ ] ファイルアップロード画面の実装
- [ ] 進捗バーの実装（フェーズ2の `on_progress` を利用）
- [ ] 結果ダウンロード機能の実装

---

## 開発前提・拡張方針

### UIについて
- **フェーズ1（現在）**: CLIのみ実装する
- **フェーズ2（将来）**: GUIを追加する予定。**Webアプリ（Streamlit等）になる可能性がある**

### 実装上の制約
以下を守ることで、将来のUI追加をスムーズにする:

1. **OCR処理ロジックをUIから完全に分離すること**
   - OCRコア処理（`pdf_converter.py` / `layout_analyzer.py` 等）はUIに依存しない純粋な関数として実装する
   - CLIの `ocr.py` はコア処理を呼び出す薄いラッパーにとどめる

2. **処理の進捗を戻り値やコールバックで通知できる設計にすること**
   - GUIやWebアプリで進捗バーを表示できるよう、進捗情報をprint以外の方法でも返せるようにする
   - 例: `on_progress(current_page, total_pages)` のようなコールバック引数を設ける

3. **入出力はファイルパスで受け渡しすること**
   - WebアップロードやGUIファイル選択にも対応できるよう、パス文字列を引数に取る設計にする

---

## インターフェース（CLI）

```bash
# 基本実行
python ocr.py input.pdf

# 出力先指定
python ocr.py input.pdf --output ./my_output

# 特定ページのみ処理
python ocr.py input.pdf --pages 1-3
```

### 引数一覧

| 引数 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `input` | ○ | - | 入力PDFのパス |
| `--output` | - | `./output` | 出力ディレクトリ |
| `--pages` | - | 全ページ | 処理するページ範囲（例: `1-5`, `2`） |
| `--dpi` | - | `300` | PDF→画像変換の解像度 |

---

## ファイル構成

```
ocr_tool/
├── ocr.py              # メインスクリプト（エントリポイント）
├── pdf_converter.py    # PDF→画像変換モジュール
├── layout_analyzer.py  # PP-Structureによるレイアウト解析
├── text_extractor.py   # テキスト領域のOCR処理
├── table_extractor.py  # 表領域の認識・Excel出力
├── requirements.txt    # 依存ライブラリ一覧
└── README.md           # 使い方説明
```

---

## エラーハンドリング

- PDFが存在しない場合: エラーメッセージを表示して終了
- 表が1つも検出されない場合: `tables.xlsx` は作成しない（警告メッセージのみ）
- OCR失敗ページがある場合: スキップしてログに記録、処理は継続する
- 処理中は進捗をコンソールに表示する（例: `[2/5] ページ 2 を処理中...`）

---

## 非機能要件

- 有料APIは一切使用しない（完全ローカル動作）
- 初回実行時にPaddleOCRのモデルが自動ダウンロードされる（許容）
- Python 3.8以上で動作すること
- 外部サービスへのデータ送信は行わないこと

---

## 実装上の注意点

1. **PP-Structureの初期化**は処理開始時に1回だけ行うこと（ループ内で毎回初期化しない）
2. **DPI=300**が品質と速度のバランスが良い。スキャン品質が低い場合は前処理（グレースケール化・二値化）を検討
3. **日英混在**の場合、PaddleOCRの`lang='japan'`は英語も認識できるため追加設定不要
4. テーブルのセル結合（colspan/rowspan）は可能な範囲で対応し、難しければ分割セルとして出力してよい

---

## 参考

- PaddleOCR公式: https://github.com/PaddlePaddle/PaddleOCR
- PP-Structure: https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppstructure/README_ch.md
