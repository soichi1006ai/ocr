# OCR Tool

スキャンPDFから本文テキストを抽出し、表は Excel と Word に出力するローカルOCRツールです。

## 機能
- PDF をページごとの PNG に変換
- PaddleOCR による本文テキスト抽出
- PP-Structure による表領域解析
- `result.txt` / `tables.xlsx` / `result.docx` を出力
- `--pages 1,3-5` 形式のページ範囲指定

## セットアップ
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install poppler
```

初回の OCR 実行時は PaddleOCR モデルが自動ダウンロードされます。

## 使い方
```bash
python ocr.py input.pdf
python ocr.py input.pdf --output ./output
python ocr.py input.pdf --pages 1,3-5 --dpi 300
```

## 出力
```text
output/
├── result.txt
├── tables.xlsx
├── result.docx
└── pages/
    ├── page_001.png
    └── page_002.png
```

## 注意
- `tables.xlsx` は表が検出された場合のみ作成されます。
- OCR や表認識の精度はスキャン品質に依存します。
- 実スキャンPDFでの最終精度確認はまだ残っています。
