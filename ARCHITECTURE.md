# OCR Tool — 根本リアーキテクチャ設計書

> **対象読者**: Claude Code / Codex（実装担当）
> **作成日**: 2026-05-07
> **バージョン**: v2.0（根本改善版）
> **前提読み物**: `PROGRESS.md`, `ocr_tool_spec.md`

---

## 0. このドキュメントの位置づけ

このリポジトリ `soichi1006ai/ocr` を v1（PaddleOCR 中心）から v2（Claude API 中心 + ハイブリッド）へ全面リアーキテクチャするための設計書。

実装にあたっては本書 + `TASKS.md` を必ずペアで参照すること。

- **本書（ARCHITECTURE.md）**: なぜこう作るか、どう作るか（設計思想・モジュール構成・データフロー）
- **TASKS.md**: 何を作るか（フェーズ別タスクリスト・受け入れ基準）

---

## 1. 改善の背景（なぜリアーキテクチャするか）

### 1.1 v1 の構造的問題

PROGRESS.md の作業ログから読み取れる根本問題：

1. **エンジン並列で全部中途半端**
   PaddleOCR / EasyOCR / NDLOCR / Claude API と4エンジン同居。各エンジンへの最適化リソースが分散し、どれも江戸時代古文書ドメインで本気の精度が出ていない。

2. **「OCR」発想で限界**
   PaddleOCR 系は「文字を1文字ずつ認識する」古典的アプローチ。江戸時代古文書のような難文書では、**文字認識ではなく「文書理解」が必要**。
   Web版 Claude が高精度なのは、画像を理解しながら文脈で読んでいるから。

3. **Claude 統合が浅い**
   `claude_engine.py` の現プロンプトは汎用的で、ドメイン知識（元号一覧・干支60組・旧字体）を一切活用していない。Web版 Claude が手作業でやっている「画像分割・段階推論・自己検証」もコード化されていない。

4. **テキスト中心の出力設計**
   テキストとして書き起こしてから後処理でパースする現行設計は情報損失が大きい。最初から構造化データ（JSON）で抽出すべき。

5. **ドメイン知識が散逸**
   干支補正・元号補正は `text_extractor.py` の中に文字列リテラルとして埋め込まれている。プロンプトでも検証でも辞書補正でも使い回せる**独立レイヤー**に切り出すべき。

### 1.2 改善の3本柱

```
柱1: Claude API を主役に据える（精度モード）
柱2: PaddleOCR は補助役として残す（オフライン・高速・コスト削減）
柱3: ドメイン知識を独立レイヤーに切り出して全エンジンで共有
```

---

## 2. 設計思想

### 2.1 3つのモード（ユーザーが選ぶ）

| モード | 主役 | 用途 | コスト/ページ | 速度/ページ |
|---|---|---|---|---|
| **精度モード** | Claude API | 最終納品、難読古文書、見開きスキャン | $0.07〜0.15 | 10〜30秒 |
| **高速・オフラインモード** | PaddleOCR | プレビュー、機密文書、大量バッチ一次処理 | 0 | 2〜5秒 |
| **ハイブリッドモード（推奨）** | Paddle + Claude | 通常運用 | $0.01〜0.03 | 5〜15秒 |

ハイブリッドの仕組み：

```
PaddleOCR で一次抽出 → confidence スコア取得
    ↓
信頼度 ≥ 閾値 → そのまま採用
信頼度 < 閾値 → Claude API に再質問
    ↓
ドメイン知識で辞書補正 → 検証 → 出力
```

### 2.2 「エンジン」と「パイプライン」と「ドメイン」を分離

v1 は処理ロジックとドメイン知識が混在していた。v2 は3層に分離する：

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Pipeline（処理の流れを定義）                    │
│   分類 → 分割 → 前処理 → 抽出 → 検証 → 補正 → 出力      │
└────────────────────┬────────────────────────────────────┘
                     │ 使う
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Engine（OCR/Vision エンジンの実装）            │
│   ClaudeEngine / PaddleEngine / HybridEngine / NDLEngine│
│   → 全て OCREngine Protocol を満たす                     │
└────────────────────┬────────────────────────────────────┘
                     │ 参照
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Domain Knowledge（江戸時代古文書ドメインの知識） │
│   干支60組 / 元号一覧 / 旧字体 / 九星 / 文書種別プロンプト│
│   → JSON で外部化、プロンプトでも辞書補正でも検証でも共用 │
└─────────────────────────────────────────────────────────┘
```

### 2.3 エンジン抽象化（OCREngine Protocol）

全エンジンが共通インタフェースを実装する。これによりモード切替がプラガブルになる。

```python
# engines/base.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class OCREngine(Protocol):
    """全 OCR エンジンの共通インタフェース"""

    name: str  # "claude" | "paddle" | "hybrid" | "ndl"

    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType,  # "koyomi" | "daichou" | "honbun" | "auto"
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """画像群から構造化データを抽出する"""
        ...
```

返り値は**最初から構造化されたデータ**（テキストと表が独立した古い設計をやめる）：

```python
@dataclass
class ExtractionResult:
    pages: list[PageResult]
    errors: list[PageError]
    metadata: dict  # engine_name, total_cost, total_time, confidence_avg

@dataclass
class PageResult:
    page_number: int
    document_type: DocumentType
    blocks: list[Block]  # テキストブロック・表・注記など
    confidence: float
    raw_text: str  # 互換用（既存の result.txt 互換）

@dataclass
class Block:
    type: str  # "paragraph" | "table" | "marginal_note" | "header"
    content: Any  # str | TableData | dict
    bbox: Optional[tuple[int, int, int, int]]
    confidence: float
```

---

## 3. ディレクトリ構造（新）

```
ocr/
├─ ocr.py                    # CLI エントリ（--mode 引数追加）
├─ launcher.py               # GUI（モード選択追加）
├─ requirements.txt          # 共通最小依存
├─ requirements-cloud.txt    # Claude API 用（anthropic）
├─ requirements-local.txt    # PaddleOCR 用（重い依存）
│
├─ engines/                  # 【新】エンジン抽象化レイヤー
│   ├─ __init__.py
│   ├─ base.py               # OCREngine Protocol、共通データクラス
│   ├─ claude_engine.py      # ★全面書き直し
│   ├─ paddle_engine.py      # 既存 text_extractor.py から移植
│   ├─ hybrid_engine.py      # 【新】Paddle + Claude のハイブリッド
│   └─ ndl_engine.py         # 既存 ndlocr_engine.py をリネーム移動
│
├─ pipeline/                 # 【新】処理パイプライン
│   ├─ __init__.py
│   ├─ classifier.py         # 文書種別判定（暦表/台帳/本文）
│   ├─ splitter.py           # 見開き自動分割
│   ├─ preprocessor.py       # 既存 image_preprocessor.py を移動
│   ├─ extractor.py          # メインオーケストレーター
│   ├─ validator.py          # 出力の妥当性検証
│   └─ corrector.py          # 干支・元号・旧字体の辞書補正
│
├─ knowledge/                # 【新】ドメイン知識（JSON）
│   ├─ kanshi.json           # 干支60組
│   ├─ gengou.json           # 元号一覧
│   ├─ kyuusei.json          # 九星
│   ├─ kyuujitai.json        # 旧字体→新字体マッピング
│   └─ loader.py             # JSON 読み込み・キャッシュ
│
├─ prompts/                  # 【新】プロンプトテンプレート（Markdown）
│   ├─ classify.md           # 文書種別判定用
│   ├─ koyomi.md             # 暦表専用
│   ├─ daichou.md            # 台帳専用
│   ├─ honbun.md             # 本文用
│   ├─ verify_koyomi.md      # 暦表用検証プロンプト
│   └─ loader.py             # テンプレート + コンテキスト注入
│
├─ exporters/                # 【新】出力レイヤー独立化
│   ├─ __init__.py
│   ├─ json_exporter.py      # 構造化 JSON 出力
│   ├─ xlsx_exporter.py      # 既存 table_extractor 相当
│   └─ docx_exporter.py      # 既存 docx_exporter.py を移動
│
├─ tests/                    # 【新】精度評価
│   ├─ ground_truth/         # 正解データ
│   │   ├─ koyomi_001.json
│   │   └─ daichou_001.json
│   ├─ accuracy_eval.py      # CER（文字誤認率）測定
│   └─ test_*.py             # ユニットテスト
│
├─ ARCHITECTURE.md           # 本書
├─ TASKS.md                  # タスクリスト
├─ PROGRESS.md               # 進捗（既存・更新する）
└─ README.md                 # ユーザー向け（書き換え）
```

### 3.1 v1 から v2 への移行マッピング

| v1 ファイル | v2 移行先 | 備考 |
|---|---|---|
| `text_extractor.py` | `engines/paddle_engine.py` | 共通インタフェースに合わせて書き直し |
| `claude_engine.py` | `engines/claude_engine.py` | 全面書き直し |
| `ndlocr_engine.py` | `engines/ndl_engine.py` | リネームのみ |
| `frame_detector.py` | 削除候補 | Claude / Hybrid モードでは不要、Paddle 用に残すか検討 |
| `layout_analyzer.py` | 削除候補 | 同上 |
| `table_extractor.py` | `exporters/xlsx_exporter.py` + 一部 `engines/paddle_engine.py` | 役割分離 |
| `image_preprocessor.py` | `pipeline/preprocessor.py` | 移動のみ |
| `pdf_converter.py` | `pipeline/preprocessor.py` 内 | 統合 |
| `docx_exporter.py` | `exporters/docx_exporter.py` | 移動のみ |
| `ocr.py` | `ocr.py` | `--mode` 引数追加 |
| `launcher.py` | `launcher.py` | モード選択 UI 追加 |

**削除しない判断**: PaddleOCR 系コードは「オフライン・機密文書・コスト削減・APIフォールバック」のために残す。ただし**主役から脇役に格下げ**する。

---

## 4. データフロー

### 4.1 精度モード

```
PDF ファイル
  │
  ▼
[pipeline/preprocessor.py] PDF → PNG ページ画像
  │
  ▼
[pipeline/splitter.py] 見開きスキャン検出 → 左右分割（必要なら）
  │
  ▼
[pipeline/classifier.py] 文書種別判定（Claude API、軽量）
  │   └─ 結果：document_type = "koyomi"
  ▼
[engines/claude_engine.py] 構造化抽出
  │   ├─ prompts/koyomi.md をロード
  │   ├─ knowledge/kanshi.json + gengou.json を context に注入
  │   ├─ Extended Thinking 有効化
  │   └─ JSON で構造化データ取得
  ▼
[pipeline/validator.py] 検証
  │   ├─ 暦表: 日数=月の日数？干支60組順序？九星循環？
  │   └─ NG → engines.claude_engine で再抽出（プロンプト調整）
  ▼
[pipeline/corrector.py] 辞書補正
  │   └─ 旧字体・誤読パターンの修正
  ▼
[exporters/*] JSON / XLSX / DOCX 出力
```

### 4.2 ハイブリッドモード

```
PDF → PNG → 見開き分割（精度モードと同じ）
  │
  ▼
[engines/paddle_engine.py] PaddleOCR で一次抽出
  │   └─ 各セルの confidence スコア取得
  ▼
[engines/hybrid_engine.py] 信頼度評価
  │   ├─ confidence ≥ 閾値（例: 0.85）→ そのまま採用
  │   └─ confidence < 閾値 → 該当領域を Claude に再質問
  ▼
[pipeline/validator.py] + [pipeline/corrector.py]
  ▼
[exporters/*] 出力
```

### 4.3 高速・オフラインモード

```
PDF → PNG → PaddleOCR → 辞書補正 → 出力
（Claude API は呼ばない）
```

---

## 5. ドメイン知識ベースの設計

### 5.1 knowledge/kanshi.json

```json
{
  "version": "1.0",
  "description": "六十干支（甲子〜癸亥の60組）",
  "items": [
    {
      "index": 1,
      "kanji": "甲子",
      "yomi": "きのえね",
      "kan": "甲",
      "shi": "子",
      "gogyou": "木",
      "common_misreads": ["甲了", "甲于"]
    },
    {
      "index": 2,
      "kanji": "乙丑",
      "yomi": "きのとうし",
      "kan": "乙",
      "shi": "丑",
      "gogyou": "木",
      "common_misreads": []
    }
    // ... 全60組
  ]
}
```

`common_misreads` は実際の OCR 誤認識パターンを蓄積していく。これが PaddleOCR の辞書補正と Claude のプロンプト両方で使われる。

### 5.2 knowledge/gengou.json

```json
{
  "version": "1.0",
  "items": [
    {
      "name": "正保",
      "yomi": "しょうほう",
      "start_year": 1644,
      "end_year": 1648,
      "common_variants": ["正寳", "正寶"],
      "common_misreads": ["延保", "正保"]
    }
    // ... 江戸時代主要元号
  ]
}
```

### 5.3 knowledge/loader.py

```python
from functools import lru_cache
from pathlib import Path
import json

KNOWLEDGE_DIR = Path(__file__).parent

@lru_cache(maxsize=None)
def load_kanshi() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "kanshi.json").read_text(encoding="utf-8"))["items"]

@lru_cache(maxsize=None)
def load_gengou() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "gengou.json").read_text(encoding="utf-8"))["items"]

# プロンプトに注入する用のテキスト整形
def format_kanshi_for_prompt() -> str:
    items = load_kanshi()
    return "\n".join(f"{x['index']}. {x['kanji']}（{x['yomi']}）" for x in items)
```

---

## 6. プロンプト設計

### 6.1 prompts/koyomi.md（暦表専用）

```markdown
# Task

この画像は江戸時代〜近代の【暦表（こよみ・カレンダー）】のスキャン画像です。
構造化された JSON 形式で正確に抽出してください。

# 文書の特徴

- 縦書き、右→左に読む
- 各日（1〜31）について、干支と九星が記載されている
- 上部に「節気・土旺」欄がある
- ページ上部に元号・年・月名が書かれている

# ドメイン知識（参考）

## 干支60組（必ずこの順序で循環する）
{KANSHI_LIST}

## 元号
{GENGOU_LIST}

## 九星表記
- 数字 + 単位（日/月/火/水/木/金/土）
- 例：水1、木2、金3

# 出力フォーマット（JSON のみ）

{
  "document_type": "koyomi",
  "year": "平成42年（2030年）",
  "year_kanshi": "庚戌",
  "months": [
    {
      "month": "1月",
      "month_kanshi": "己丑",
      "kyoku": "陰8局",
      "kyuusei": "3碧",
      "sekki": [
        {"name": "小寒", "date": "1/5", "time": "22:23"},
        {"name": "大寒", "date": "1/20", "time": "15:17", "doou": "4806"}
      ],
      "days": [
        {"day": 1, "kanshi": "辛丑", "kyuusei": "水2"},
        {"day": 2, "kanshi": "壬寅", "kyuusei": "木3"}
      ]
    }
  ]
}

# 厳守ルール

1. 元号・干支・旧字体は変換せずそのまま記載
2. 不確定な文字は "[?]" で囲む（推測で埋めない）
3. 干支は60組の順序を必ず守る（順序が崩れていたら誤認識を疑い再確認）
4. 1ヶ月の日数（28-31日）と整合する数だけ days を出力
5. JSON 以外の説明文は出力しない
```

`{KANSHI_LIST}` と `{GENGOU_LIST}` は `prompts/loader.py` でランタイム展開する。

### 6.2 prompts/loader.py

```python
from pathlib import Path
from knowledge.loader import format_kanshi_for_prompt, format_gengou_for_prompt

PROMPTS_DIR = Path(__file__).parent

def load_prompt(name: str, **context) -> str:
    """プロンプトテンプレートをロードしてコンテキストを注入"""
    template = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    default_context = {
        "KANSHI_LIST": format_kanshi_for_prompt(),
        "GENGOU_LIST": format_gengou_for_prompt(),
    }
    default_context.update(context)
    return template.format(**default_context)
```

---

## 7. 検証ロジック設計

### 7.1 暦表用バリデータ

```python
# pipeline/validator.py
from datetime import date

def validate_koyomi(result: dict) -> list[str]:
    """暦表抽出結果の検証。エラーリストを返す（空なら OK）"""
    errors = []

    # 日数チェック
    for m in result["months"]:
        month_num = int(m["month"].rstrip("月"))
        days_count = len(m["days"])
        # 簡易チェック：1月=31, 2月=28/29, ...
        expected = days_in_month(result["year"], month_num)
        if days_count != expected:
            errors.append(f"{m['month']}: 日数 {days_count} ≠ 期待値 {expected}")

    # 干支60組の連続性チェック
    all_kanshi = []
    for m in result["months"]:
        for d in m["days"]:
            all_kanshi.append(d["kanshi"])
    if not is_kanshi_continuous(all_kanshi):
        errors.append("干支の連続性に異常あり")

    return errors

def is_kanshi_continuous(kanshi_list: list[str]) -> bool:
    """干支リストが60組順序を保っているか"""
    from knowledge.loader import load_kanshi
    table = {x["kanji"]: x["index"] for x in load_kanshi()}
    indices = [table.get(k) for k in kanshi_list]
    if None in indices:
        return False
    for i in range(len(indices) - 1):
        # 60→1 の循環を許容
        expected_next = (indices[i] % 60) + 1
        if indices[i + 1] != expected_next:
            return False
    return True
```

### 7.2 検証 NG 時の再抽出

```python
# pipeline/extractor.py
def extract_with_validation(engine, image_paths, doc_type, max_retries=2):
    for attempt in range(max_retries + 1):
        result = engine.extract(image_paths, doc_type)
        errors = validate(result, doc_type)
        if not errors:
            return result
        # NG → エラー情報をプロンプトに含めて再抽出
        engine.set_retry_context(errors=errors, previous_result=result)
    # 最終的に NG でも結果を返す（エラー情報付き）
    return result
```

---

## 8. UI 統合（launcher.py）

### 8.1 モード選択 UI

設定パネルの最上部に「モード」ラジオボタンを追加：

```
┌─────────────────────────────────────┐
│ モード（処理方針）                   │
│ ○ 精度優先（Claude API）             │
│ ● ハイブリッド ★推奨                │
│ ○ 高速・オフライン（PaddleOCR）      │
│                                       │
│ 文書種別                             │
│ ○ 自動判定 ● 暦表 ○ 台帳 ○ 本文     │
│                                       │
│ 言語: 日本語                         │
│ DPI: 300                             │
│ ...                                  │
└─────────────────────────────────────┘
```

モードによって表示・非表示する項目：

- 精度モード選択時：「Claude モデル選択」（Opus 4.7 / Sonnet 4.6）
- オフラインモード選択時：「Paddle エンジン詳細設定」
- ハイブリッドモード選択時：「信頼度閾値」スライダー（0.7〜0.95）

---

## 9. 削除しないが格下げするコード

以下は**残す**が、エントリポイント（`ocr.py`）からの呼び出しは v2 のエンジン抽象化レイヤー経由になる：

- `frame_detector.py` → `engines/paddle_engine.py` の内部で使用
- `layout_analyzer.py` → 同上
- `table_extractor.py` → ロジック分離（OCR は engine、エクスポートは exporters）
- `image_preprocessor.py` → `pipeline/preprocessor.py` に移動

---

## 10. テスト戦略

### 10.1 精度評価フレームワーク

`tests/accuracy_eval.py` でモード別の精度を測定する：

```python
# 正解データを読み込んで CER（文字誤認率）を測る
def evaluate_mode(mode: str, test_files: list[Path]) -> dict:
    results = {}
    for f in test_files:
        actual = run_ocr(f, mode=mode)
        expected = load_ground_truth(f)
        cer = calc_cer(actual, expected)
        results[f.name] = cer
    return {
        "mode": mode,
        "files": results,
        "average_cer": sum(results.values()) / len(results),
    }
```

### 10.2 受け入れ精度（目標値）

| 文書種別 | モード | 目標 CER |
|---|---|---|
| 暦表 | 精度モード | < 1% |
| 暦表 | ハイブリッド | < 3% |
| 暦表 | オフライン | < 10% |
| 台帳 | 精度モード | < 3% |
| 台帳 | ハイブリッド | < 8% |
| 本文 | 精度モード | < 5% |

---

## 11. コスト試算

### 11.1 Claude API（Opus 4.7）

- 入力: ページ画像 ≈ 3,000〜5,000 トークン
- 出力: 構造化 JSON ≈ 2,000〜4,000 トークン
- ドメイン知識 context ≈ 2,000 トークン

1ページあたり概算：
- 入力: 7,000 × $15/MTok = $0.105
- 出力: 3,000 × $75/MTok = $0.225
- 合計: 約 $0.33/ページ（精度モード）

### 11.2 ハイブリッドモードの節約効果

PaddleOCR で 80% のセルを処理 → 20% のみ Claude に再質問
→ 約 $0.07/ページ（精度モードの 1/5）

### 11.3 暦表11ファイルの想定コスト

```
精度モード:    11ファイル × 1ページ × $0.33 = $3.6
ハイブリッド:  11ファイル × 1ページ × $0.07 = $0.8
オフライン:    無料（ただし精度低下）
```

---

## 12. 既存リソースとの関係

### 12.1 マスターSの既存ワークフロー

DonCorleone エコシステムとの整合：

- ワークフロー: `1 issue → 1 branch → 1 PR`
- 言語分離: 会話は日本語、Claude Code は英語
- 環境: Python 3.11.9（pyenv local）

このリアーキテクチャもこのワークフローに従う（TASKS.md 参照）。

### 12.2 関連スキルとの接続

`~/claudecode/workspace/skills/` のうち以下が活用可能：

- `product-strategist`: モード設計の妥当性レビュー
- `design-director`: launcher.py の UI レビュー

---

## 13. リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| Claude API 障害 | 精度モード使用不可 | オフラインモードでフォールバック |
| API キー漏洩 | 課金リスク | `.env` 必須、`.gitignore` 確認、Anthropic Console で使用上限設定 |
| ドメイン知識の不完全さ | 検証で誤検知 | `common_misreads` を運用で蓄積 |
| 既存ユーザーの破壊変更 | v1 利用者が困る | v1 互換モード（`--mode v1`）を1リリース分は残す |
| ハイブリッドの閾値チューニング | 過剰な API 呼び出し | UI でユーザー調整可能、デフォルト 0.85 |

---

## 14. 完了の定義

このリアーキテクチャは以下が全て満たされたら完了とする：

1. 3モード全てが動作する
2. 暦表11ファイルで精度モードが目標 CER < 1% を達成
3. v1 から v2 への移行ガイドが README に記載されている
4. `tests/accuracy_eval.py` がモード別精度比較を出力できる
5. ARCHITECTURE.md / TASKS.md / PROGRESS.md が最新状態
6. すべての変更が main にマージされ、リリースタグ `v2.0.0` が付いている

---

## 15. 次のステップ

→ `TASKS.md` を読んでフェーズ1のタスクから着手すること
