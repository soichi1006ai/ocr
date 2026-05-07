# OCR Tool v2

江戸時代古文書（暦表・台帳・本文）に特化したスキャン PDF テキスト抽出ツールです。  
**3モード対応**: クラウド AI（Claude API）/ ハイブリッド / オフライン（PaddleOCR）

---

## モード比較

| モード | 精度 | コスト | インターネット |
|---|---|---|---|
| **精度**（Claude API）| ★★★ | 従量課金 | 必要 |
| **ハイブリッド** ★ | ★★☆ | 低コスト | 必要 |
| **オフライン**（PaddleOCR）| ★☆☆ | 無料 | 不要 |

ハイブリッドモードは PaddleOCR で全体を処理し、信頼度が低いページのみ Claude API で再抽出します。コストを抑えながら精度モードに近い結果を得やすいため、通常運用には **ハイブリッド ★** を推奨します。

### 対応文書種別

| 種別 | 説明 |
|---|---|
| **暦表** | 日付・干支・九星・二十四節気を列挙した古暦 |
| **台帳** | 元号・人名・数量を含む記録帳簿 |
| **本文** | 上記以外の縦書き和文 |
| **自動** | 文書種別を Claude API で自動判定（クラウド系のみ） |

---

## セットアップ

### クラウド系モード（精度 / ハイブリッド）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-cloud.txt
brew install poppler  # macOS
```

`ANTHROPIC_API_KEY` を環境変数またはプロジェクトルートの `.env` ファイルに設定してください。

```bash
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY=... を記入
```

### オフラインモード（PaddleOCR）

> Python **3.11** が必要です（paddlepaddle 2.6.2 が 3.12+ 未対応）

```bash
pyenv local 3.11.9          # 例: pyenv を使う場合
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-local.txt
brew install poppler
```

初回 OCR 実行時は PaddleOCR モデルが自動ダウンロードされます。

---

## 使い方

### GUI ランチャー（推奨）

```bash
python launcher.py
```

ドラッグ＆ドロップでファイルを追加し、モード・文書種別・出力先を設定して「OCR 開始」を押します。

### CLI

```bash
# ハイブリッドモード（デフォルト推奨）
python ocr.py input.pdf --engine hybrid --document-type koyomi

# 精度モード（Opus 4.7）
python ocr.py input.pdf --engine claude --model claude-opus-4-7

# オフラインモード
python ocr.py input.pdf --engine paddleocr

# 見開きスキャン（左右分割）
python ocr.py input.pdf --engine hybrid --spread

# 出力先・DPI・形式を指定
python ocr.py input.pdf --output ./results --dpi 400 --formats txt xlsx
```

主なオプション:

| オプション | 説明 | デフォルト |
|---|---|---|
| `--engine` | `hybrid` / `claude` / `paddleocr` / `ndlocr` | `paddleocr` |
| `--document-type` | `auto` / `koyomi` / `daichou` / `honbun` | `auto` |
| `--model` | `claude-opus-4-7` / `claude-sonnet-4-6` | Sonnet 4.6 |
| `--confidence-threshold` | ハイブリッド時の Claude 再抽出閾値（0〜1） | `0.85` |
| `--spread` | 見開きスキャンを左右に分割して処理 | off |
| `--dpi` | PDF→PNG 変換解像度 | `300` |
| `--formats` | `txt xlsx docx`（複数指定可） | 全形式 |
| `--pages` | ページ指定（例: `1,3-5`） | 全ページ |

---

## 出力

```
output/
├── result.txt        # 抽出テキスト（全ページ）
├── tables.xlsx       # 表データ（表が検出された場合）
├── result.docx       # Word 形式（本文＋表）
└── pages/
    ├── page_001.png
    └── page_002.png
```

---

## v1 からの移行

v2 では以下が変わりました:

- **エンジン選択**: `--engine ndlocr` が `--engine hybrid` / `--engine claude` に加わりました
- **文書種別**: `--document-type` オプションで暦表・台帳・本文を指定できます
- **GUI**: `launcher.py` でモード・文書種別・信頼度閾値を GUI 操作できます
- **ディレクトリ構成**: `engines/`, `pipeline/`, `exporters/`, `knowledge/` に整理されました

基本的な CLI コマンド（`--engine paddleocr` 等）は v1 と互換性があります。

---

## コスト目安（Claude API）

| モード | 10ページ | 50ページ |
|---|---|---|
| 精度（Opus 4.7） | ~$0.27 | ~$1.35 |
| 精度（Sonnet 4.6） | ~$0.05 | ~$0.27 |
| ハイブリッド（Sonnet 4.6 相当） | ~$0.02 | ~$0.09 |

1ページあたり約 1,800 トークン（入出力合計）と想定した参考値です。

---

## 注意事項

- `tables.xlsx` は表が検出された場合のみ生成されます
- OCR 精度はスキャン品質に依存します（推奨: 300 dpi 以上、傾き 5° 以内）
- PaddleOCR モードは **Python 3.11 / paddleocr==2.7.3 / paddlepaddle==2.6.2** を使ってください
- Anthropic Console での月額上限設定を推奨します（目安: $50/月）
