# Claude Code への引き継ぎサマリ

> **作成日**: 2026-05-07
> **作成者**: Web Claude（Opus 4.7）+ マスターS
> **対象**: Claude Code（VS Code拡張 / Terminal）

---

## このファイルを最初に読むこと

このリアーキテクチャプロジェクトは以下の3点セットで構成されている：

1. **`ARCHITECTURE.md`** ─ 設計思想・モジュール構成・データフロー
2. **`TASKS.md`** ─ フェーズ別タスクリスト・受け入れ基準
3. **`HANDOVER.md`** ─ 本ファイル（コンテキストと指示書）

実装着手前に、上記3ファイルすべてを読むこと。

---

## 1. プロジェクトの背景

### 1.1 リポジトリ
`https://github.com/soichi1006ai/ocr` を v1（PaddleOCR中心）から v2（Claude API中心 + ハイブリッド）へ全面リアーキテクチャする。

### 1.2 きっかけ
マスターSが暦表PDF11ファイルをExcel変換しようとした際に、現行のClaude API版の精度が低く、Web版Claudeの精度に遠く及ばないことが判明。原因を分析した結果、構造的な設計問題が見つかった。

### 1.3 マスターSの判断
- ツールの位置づけ: **両立モード（精度 / オフライン / ハイブリッド）**
- オフライン動作: **必要（ハイブリッド案）**
- スケジュール: **長期品質優先（12〜13週）**
- Claudeモデル: **Opus 4.7（精度重視）**
- 引き継ぎ: **設計書とタスクリストの両方**
- ブランチ粒度: **設計のみ、実装は別途**

---

## 2. 大事な大原則（必読）

### 2.1 マスターSの開発規律
- **1 issue → 1 branch → 1 PR**（厳守）
- **言語分離**: 会話は日本語、Claude Code は英語
- **Python 3.11.9**（pyenv local 設定済み）
- **環境**: macOS / Mac開発、Vercelデプロイ知識あり

### 2.2 v1 を破壊しない
- v1 の `main` を `v1.0.0` タグで保護
- v2 開発は `v2-dev` ブランチで実施
- 全体完了まで `main` にはマージしない

### 2.3 ドメイン知識を最初に作る
フェーズ1（ドメイン知識ベース）が**全ての土台**。
ここをサボると後段の精度が出ない。
プロンプト・検証・補正のすべてがこの知識を参照する。

### 2.4 「OCR」ではなく「文書理解」
PaddleOCR系の「文字を1文字ずつ認識する」発想を捨て、Claudeに「画像を理解させて構造化データを返させる」発想で設計する。

---

## 3. 着手手順

### ステップ1: 環境準備
```bash
cd ~/path/to/ocr
git checkout main
git pull
git tag v1.0.0  # v1 の最終形を保護
git push --tags

git checkout -b v2-dev
git push -u origin v2-dev
```

### ステップ2: ARCHITECTURE.md / TASKS.md / HANDOVER.md をリポジトリにコミット
本3ファイルをリポジトリ直下に配置：
```bash
cp /path/to/ARCHITECTURE.md .
cp /path/to/TASKS.md .
cp /path/to/HANDOVER.md .
git add ARCHITECTURE.md TASKS.md HANDOVER.md
git commit -m "docs: v2 architecture, tasks, and handover documents"
git push origin v2-dev
```

### ステップ3: フェーズ0から順に着手
TASKS.md のフェーズ0から順番に。フェーズを飛ばさない。

各タスクは：
1. 受け入れ基準を確認
2. feature ブランチを切る
3. テストを先に書く
4. 実装
5. PR を v2-dev に向けて作成
6. PROGRESS.md と TASKS.md のチェックボックスを更新

---

## 4. API キーの取得と設定

```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# 実際の .env（ .gitignore 済み）
cp .env.example .env
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

Anthropic Console で月額使用上限を設定（推奨 $50/月）。

---

## 5. テストデータ

### 5.1 既知のテストPDF
- `doc00792520260430181242.pdf` ─ v1で使用済みの日本語縦書き・英語混在PDF
- `doc00794320260507095906.pdf` ─ 暦表（平成42年/2030年/庚戌）見開き

### 5.2 ground_truth の作り方
1. Web版 Claude（claude.ai）に PDF をアップロード
2. ARCHITECTURE.md §6.1 の暦表プロンプトをそのまま投入
3. 返ってきた JSON を `tests/ground_truth/` に保存
4. 目視で確認・修正

---

## 6. 本ドキュメントとの不整合があった場合

優先順位：
1. **マスターSの指示** が最優先
2. **ARCHITECTURE.md** の設計思想
3. **TASKS.md** の具体的タスク
4. **本ファイル**（HANDOVER.md）

不整合に気づいたら作業を止めて確認すること。

---

## 7. よくある罠（先回り注意）

### 7.1 Claude API の構造化出力
`json_object` モードや `response_format` は Anthropic API には**ない**。
プロンプトで「JSON のみ返せ」と指示し、コード側で堅牢にパースする必要がある。
コードブロック（```json ... ```）で包まれている可能性があるため、`raw.split("```")[1].lstrip("json")` のような前処理が必要。

### 7.2 Extended Thinking の仕様
`thinking={"type": "enabled", "budget_tokens": 4000}` を `messages.create()` に渡す。
ただし `max_tokens` は `budget_tokens + 出力想定` 以上にする必要がある。
budget_tokens を超えた場合の挙動も確認すること。

### 7.3 画像サイズ制限
Claude API の画像上限は 5MB。`_b64_image()` の既存ロジック（解像度保持・JPEG変換）を継承すること。リサイズが先に走ると精度が落ちる。

### 7.4 PaddleOCR 環境問題
v1 で散々ハマった通り、PaddleOCR 2.7.3 + Python 3.11.9 + numpy<2 の固定が必須。
`requirements-local.txt` でこれを明示する。

---

## 8. リリース時の最終チェックリスト

v2.0.0 リリース前の確認項目：

- [ ] 3モードすべてが動作する
- [ ] 暦表11ファイルで精度モードが CER < 1% を達成
- [ ] tests/accuracy_eval.py がモード別精度比較を出力できる
- [ ] launcher.py の新UIが動作する
- [ ] README.md / ARCHITECTURE.md / TASKS.md / PROGRESS.md が最新
- [ ] .env が gitignore されている
- [ ] v1 互換モード（必要なら）が動く
- [ ] GitHub Releases にリリースノートがある

---

## 9. マスターSの連絡先

実装中の判断に迷ったら、PR コメント or Issue でマスターSに確認。
Don Corleone エコシステム経由で同期される。

---

## 10. 終わりに

このリアーキテクチャは「江戸時代古文書OCRの決定版」を目指す野心的なプロジェクト。
品質優先のため、急がないこと。各フェーズで丁寧に検証してから次に進むこと。

頑張れ、Claude Code。
