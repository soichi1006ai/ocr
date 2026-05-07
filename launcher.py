from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QMimeData, QUrl, QProcess
)
from PyQt6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QPalette, QFont, QIcon,
    QPixmap, QPainter, QPen
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QProgressBar, QGroupBox,
    QRadioButton, QButtonGroup, QCheckBox, QLineEdit, QSpinBox,
    QScrollArea, QFrame, QSizePolicy, QTextEdit, QSplitter,
    QComboBox, QMessageBox
)


# ────────────────────────────────────────────────
#  OCR Worker Thread
# ────────────────────────────────────────────────

class OCRWorker(QThread):
    progress_line = pyqtSignal(str)       # stdout/stderr line
    file_started  = pyqtSignal(str, int)  # (filepath, index 1-based)
    file_done     = pyqtSignal(str, bool, str)  # (filepath, success, message)
    all_done      = pyqtSignal()

    def __init__(
        self,
        files: list[Path],
        engine: str,
        dpi: int,
        output_dir: Path,
        ocr_py: Path,
        spread: bool = False,
        formats: list[str] | None = None,
        api_key: str = "",
        document_type: str = "auto",
        model: str = "",
        confidence_threshold: float = 0.85,
    ) -> None:
        super().__init__()
        self._files = files
        self._engine = engine
        self._dpi = dpi
        self._output_dir = output_dir
        self._ocr_py = ocr_py
        self._spread = spread
        self._formats = formats or ["txt", "xlsx", "docx"]
        self._api_key = api_key
        self._document_type = document_type
        self._model = model
        self._confidence_threshold = confidence_threshold
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        # poppler / homebrew のパスを確実に含める（デスクトップ起動時は PATH が限定的）
        import os
        env = os.environ.copy()
        extra = ["/usr/local/bin", "/opt/homebrew/bin", "/opt/homebrew/sbin"]
        existing = set(env.get("PATH", "").split(":"))
        prepend = [p for p in extra if p not in existing]
        if prepend:
            env["PATH"] = ":".join(prepend) + ":" + env.get("PATH", "")

        for i, file_path in enumerate(self._files, start=1):
            if self._cancelled:
                break
            self.file_started.emit(str(file_path), i)
            stem = file_path.stem
            out_dir = self._output_dir / stem
            out_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                sys.executable,
                str(self._ocr_py),
                str(file_path),
                "--output", str(out_dir),
                "--dpi",    str(self._dpi),
                "--engine", self._engine,
            ]
            if self._spread:
                cmd.append("--spread")
            if self._formats:
                cmd += ["--formats"] + self._formats
            if self._api_key:
                cmd += ["--api-key", self._api_key]
            if self._document_type != "auto":
                cmd += ["--document-type", self._document_type]
            if self._model:
                cmd += ["--model", self._model]
            if self._engine == "hybrid":
                cmd += ["--confidence-threshold", str(self._confidence_threshold)]
            self.progress_line.emit(f"実行: {' '.join(str(c) for c in cmd[-6:])}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    cwd=str(self._ocr_py.parent),
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip()
                    if line and not line.startswith("[2026") and "ppocr DEBUG" not in line:
                        self.progress_line.emit(line)
                proc.wait()
                if proc.returncode == 0:
                    self.file_done.emit(str(file_path), True, f"→ {out_dir}")
                else:
                    self.file_done.emit(str(file_path), False, f"失敗 (終了コード {proc.returncode})")
            except Exception as exc:
                self.file_done.emit(str(file_path), False, str(exc))

        self.all_done.emit()


# ────────────────────────────────────────────────
#  File Chip Widget
# ────────────────────────────────────────────────

class FileChip(QFrame):
    removed = pyqtSignal(str)  # file path

    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = file_path
        self.setObjectName("FileChip")
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        name = Path(file_path).name
        lbl = QLabel(name)
        lbl.setFont(QFont("Helvetica Neue", 11))
        lbl.setToolTip(file_path)
        layout.addWidget(lbl)

        btn = QPushButton("✕")
        btn.setFixedSize(18, 18)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.removed.emit(self._path))
        layout.addWidget(btn)

    def path(self) -> str:
        return self._path


# ────────────────────────────────────────────────
#  Drop Zone Widget
# ────────────────────────────────────────────────

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)  # list[str]

    SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hovering = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("⬆")
        icon_lbl.setFont(QFont("Helvetica Neue", 32))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setObjectName("DropIcon")
        layout.addWidget(icon_lbl)

        hint = QLabel("PDF / PNG / JPG / TIFF をここにドロップ")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFont(QFont("Helvetica Neue", 12))
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        browse_btn = QPushButton("ファイルを選択")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse)
        btn_layout.addWidget(browse_btn)
        layout.addLayout(btn_layout)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "ファイルを選択", str(Path.home()),
            "対応ファイル (*.pdf *.png *.jpg *.jpeg *.tiff *.tif)"
        )
        if paths:
            self.files_dropped.emit(paths)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(Path(p).suffix.lower() in self.SUPPORTED for p in paths):
                event.acceptProposedAction()
                self._set_hover(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._set_hover(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_hover(False)
        paths = [
            u.toLocalFile()
            for u in event.mimeData().urls()
            if Path(u.toLocalFile()).suffix.lower() in self.SUPPORTED
        ]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def _set_hover(self, hovering: bool) -> None:
        self._hovering = hovering
        self.setProperty("hovering", hovering)
        self.style().unpolish(self)
        self.style().polish(self)


# ────────────────────────────────────────────────
#  Main Window
# ────────────────────────────────────────────────

class MainWindow(QMainWindow):
    OCR_PY = Path(__file__).parent / "ocr.py"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCR Launcher")
        self.setMinimumWidth(560)
        self.resize(620, 760)
        self._files: list[str] = []
        self._chips: dict[str, FileChip] = {}
        self._worker: Optional[OCRWorker] = None
        self._running = False
        self._completed = 0

        self._build_ui()
        self._apply_stylesheet()

    # ── UI Construction ──────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("OCR Launcher")
        title.setFont(QFont("Helvetica Neue", 18, QFont.Weight.Bold))
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()
        vbox.addLayout(header)

        # Drop zone
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._add_files)
        vbox.addWidget(self._drop_zone)

        # File chip area
        chip_scroll = QScrollArea()
        chip_scroll.setObjectName("ChipArea")
        chip_scroll.setWidgetResizable(True)
        chip_scroll.setFixedHeight(72)
        chip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        chip_container = QWidget()
        chip_container.setObjectName("ChipContainer")
        self._chip_layout = QHBoxLayout(chip_container)
        self._chip_layout.setContentsMargins(8, 8, 8, 8)
        self._chip_layout.setSpacing(6)
        self._chip_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._empty_label = QLabel("ファイルが選択されていません")
        self._empty_label.setObjectName("EmptyHint")
        self._chip_layout.addWidget(self._empty_label)

        chip_scroll.setWidget(chip_container)
        vbox.addWidget(chip_scroll)

        # Settings group
        settings = QGroupBox("設定")
        settings.setObjectName("SettingsGroup")
        sbox = QVBoxLayout(settings)
        sbox.setSpacing(10)

        # モード
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("モード")
        mode_lbl.setFixedWidth(80)
        mode_row.addWidget(mode_lbl)
        self._mode_group = QButtonGroup(self)
        self._offline_radio = QRadioButton("オフライン")
        self._hybrid_radio  = QRadioButton("ハイブリッド ★")
        self._cloud_radio   = QRadioButton("精度")
        self._hybrid_radio.setChecked(True)
        self._mode_group.addButton(self._offline_radio, 0)
        self._mode_group.addButton(self._hybrid_radio,  1)
        self._mode_group.addButton(self._cloud_radio,   2)
        for r in (self._offline_radio, self._hybrid_radio, self._cloud_radio):
            mode_row.addWidget(r)
        mode_row.addStretch()
        sbox.addLayout(mode_row)

        # 文書種別
        doctype_row = QHBoxLayout()
        doctype_lbl = QLabel("文書種別")
        doctype_lbl.setFixedWidth(80)
        doctype_row.addWidget(doctype_lbl)
        self._doctype_group = QButtonGroup(self)
        self._dt_auto    = QRadioButton("自動")
        self._dt_koyomi  = QRadioButton("暦表")
        self._dt_daichou = QRadioButton("台帳")
        self._dt_honbun  = QRadioButton("本文")
        self._dt_auto.setChecked(True)
        for i, r in enumerate((self._dt_auto, self._dt_koyomi, self._dt_daichou, self._dt_honbun)):
            self._doctype_group.addButton(r, i)
            doctype_row.addWidget(r)
        doctype_row.addStretch()
        sbox.addLayout(doctype_row)

        # 信頼度閾値（ハイブリッドモード時のみ表示）
        from PyQt6.QtWidgets import QSlider
        self._threshold_widget = QWidget()
        threshold_row = QHBoxLayout(self._threshold_widget)
        threshold_row.setContentsMargins(0, 0, 0, 0)
        threshold_lbl = QLabel("信頼度閾値")
        threshold_lbl.setFixedWidth(80)
        threshold_row.addWidget(threshold_lbl)
        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(50, 99)
        self._threshold_slider.setValue(85)
        self._threshold_slider.setFixedWidth(160)
        self._threshold_val_lbl = QLabel("0.85")
        self._threshold_val_lbl.setFixedWidth(36)
        self._threshold_slider.valueChanged.connect(
            lambda v: self._threshold_val_lbl.setText(f"{v/100:.2f}")
        )
        threshold_row.addWidget(self._threshold_slider)
        threshold_row.addWidget(self._threshold_val_lbl)
        threshold_row.addStretch()
        sbox.addWidget(self._threshold_widget)

        # モデル選択（精度モード時のみ表示）
        self._model_widget = QWidget()
        model_row = QHBoxLayout(self._model_widget)
        model_row.setContentsMargins(0, 0, 0, 0)
        model_lbl = QLabel("モデル")
        model_lbl.setFixedWidth(80)
        model_row.addWidget(model_lbl)
        self._model_combo = QComboBox()
        self._model_combo.addItem("Opus 4.7（高精度）",   "claude-opus-4-7")
        self._model_combo.addItem("Sonnet 4.6（高速）", "claude-sonnet-4-6")
        self._model_combo.setFixedWidth(200)
        model_row.addWidget(self._model_combo)
        model_row.addStretch()
        sbox.addWidget(self._model_widget)

        # API キー（ハイブリッド or 精度モード時のみ表示）
        self._apikey_widget = QWidget()
        self._apikey_row = QHBoxLayout(self._apikey_widget)
        self._apikey_row.setContentsMargins(0, 0, 0, 0)
        apikey_lbl = QLabel("API Key")
        apikey_lbl.setFixedWidth(80)
        self._apikey_row.addWidget(apikey_lbl)
        self._apikey_edit = QLineEdit()
        self._apikey_edit.setPlaceholderText("sk-ant-... （空欄の場合は環境変数 ANTHROPIC_API_KEY を使用）")
        self._apikey_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._apikey_row.addWidget(self._apikey_edit)
        sbox.addWidget(self._apikey_widget)

        # モード切替で表示を更新
        self._mode_group.buttonToggled.connect(lambda *_: self._update_mode_ui())
        self._update_mode_ui()

        # DPI
        dpi_row = QHBoxLayout()
        dpi_lbl = QLabel("DPI")
        dpi_lbl.setFixedWidth(80)
        dpi_row.addWidget(dpi_lbl)
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setValue(300)
        self._dpi_spin.setSuffix(" dpi")
        self._dpi_spin.setFixedWidth(100)
        dpi_row.addWidget(self._dpi_spin)
        dpi_row.addStretch()
        sbox.addLayout(dpi_row)

        # 見開き分割
        spread_row = QHBoxLayout()
        spread_lbl = QLabel("見開き")
        spread_lbl.setFixedWidth(80)
        spread_row.addWidget(spread_lbl)
        self._spread_check = QCheckBox("左右に分割して各ページを独立補正（見開きスキャン用）")
        spread_row.addWidget(self._spread_check)
        spread_row.addStretch()
        sbox.addLayout(spread_row)

        # Output dir
        out_row = QHBoxLayout()
        out_lbl = QLabel("出力先")
        out_lbl.setFixedWidth(80)
        out_row.addWidget(out_lbl)
        self._output_edit = QLineEdit()
        self._output_edit.setText(str(Path.home() / "ocr_output"))
        self._output_edit.setPlaceholderText("出力フォルダパス")
        out_row.addWidget(self._output_edit)
        out_browse = QPushButton("参照")
        out_browse.setFixedWidth(52)
        out_browse.clicked.connect(self._browse_output)
        out_row.addWidget(out_browse)
        sbox.addLayout(out_row)

        # 出力形式
        fmt_row = QHBoxLayout()
        fmt_lbl = QLabel("出力形式")
        fmt_lbl.setFixedWidth(80)
        fmt_row.addWidget(fmt_lbl)
        self._fmt_txt  = QCheckBox("TXT")
        self._fmt_xlsx = QCheckBox("Excel (xlsx)")
        self._fmt_docx = QCheckBox("Word (docx)")
        self._fmt_txt.setChecked(True)
        self._fmt_xlsx.setChecked(True)
        self._fmt_docx.setChecked(True)
        for cb in (self._fmt_txt, self._fmt_xlsx, self._fmt_docx):
            fmt_row.addWidget(cb)
        fmt_row.addStretch()
        sbox.addLayout(fmt_row)

        vbox.addWidget(settings)

        # Log area
        log_group = QGroupBox("ログ")
        log_group.setObjectName("LogGroup")
        log_vbox = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Menlo", 11))
        self._log.setMinimumHeight(160)
        self._log.setObjectName("LogArea")
        log_vbox.addWidget(self._log)
        vbox.addWidget(log_group)

        # Progress + Start button
        footer = QVBoxLayout()
        footer.setSpacing(8)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m ファイル")
        self._progress.setFixedHeight(18)
        self._progress.setVisible(False)
        footer.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("StatusLabel")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.addWidget(self._status_lbl)

        # インラインバリデーションエラー表示
        self._validation_lbl = QLabel("")
        self._validation_lbl.setObjectName("ValidationLabel")
        self._validation_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._validation_lbl.setWordWrap(True)
        self._validation_lbl.setVisible(False)
        footer.addWidget(self._validation_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._clear_btn = QPushButton("クリア")
        self._clear_btn.setObjectName("ClearBtn")
        self._clear_btn.setFixedWidth(80)
        self._clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self._clear_btn)

        self._open_btn = QPushButton("結果を開く")
        self._open_btn.setObjectName("OpenBtn")
        self._open_btn.setFixedWidth(100)
        self._open_btn.setFixedHeight(36)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_output)
        self._open_btn.setVisible(False)
        btn_row.addWidget(self._open_btn)

        self._start_btn = QPushButton("OCR 開始")
        self._start_btn.setObjectName("StartBtn")
        self._start_btn.setFixedWidth(120)
        self._start_btn.setFixedHeight(36)
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._toggle_run)
        btn_row.addWidget(self._start_btn)
        footer.addLayout(btn_row)

        vbox.addLayout(footer)

    # ── File Management ──────────────────────────

    def _add_files(self, paths: list[str]) -> None:
        added = 0
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                chip = FileChip(p)
                chip.removed.connect(self._remove_file)
                self._chips[p] = chip
                self._chip_layout.addWidget(chip)
                added += 1
        if added:
            self._empty_label.setVisible(False)
        self._update_start_btn()

    def _remove_file(self, path: str) -> None:
        if path in self._files:
            self._files.remove(path)
        if path in self._chips:
            chip = self._chips.pop(path)
            self._chip_layout.removeWidget(chip)
            chip.deleteLater()
        if not self._files:
            self._empty_label.setVisible(True)
        self._update_start_btn()

    def _clear_all(self) -> None:
        for path in list(self._files):
            self._remove_file(path)
        self._log.clear()
        self._status_lbl.setText("")

    # ── Settings ─────────────────────────────────

    def _browse_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "出力フォルダを選択", self._output_edit.text())
        if d:
            self._output_edit.setText(d)

    def _update_mode_ui(self) -> None:
        is_hybrid  = self._hybrid_radio.isChecked()
        is_cloud   = self._cloud_radio.isChecked()
        is_offline = self._offline_radio.isChecked()
        self._threshold_widget.setVisible(is_hybrid)
        self._model_widget.setVisible(is_cloud)
        self._apikey_widget.setVisible(not is_offline)

    def _selected_engine(self) -> str:
        if self._cloud_radio.isChecked():  return "claude"
        if self._hybrid_radio.isChecked(): return "hybrid"
        return "paddleocr"

    def _selected_document_type(self) -> str:
        mapping = {0: "auto", 1: "koyomi", 2: "daichou", 3: "honbun"}
        return mapping.get(self._doctype_group.checkedId(), "auto")

    def _selected_model(self) -> str:
        if self._cloud_radio.isChecked():
            return self._model_combo.currentData() or ""
        return ""

    def _selected_confidence(self) -> float:
        return self._threshold_slider.value() / 100.0

    def _selected_api_key(self) -> str:
        return self._apikey_edit.text().strip()

    def _selected_formats(self) -> list[str]:
        fmt = []
        if self._fmt_txt.isChecked():  fmt.append("txt")
        if self._fmt_xlsx.isChecked(): fmt.append("xlsx")
        if self._fmt_docx.isChecked(): fmt.append("docx")
        return fmt

    # ── Run Control ──────────────────────────────

    def _toggle_run(self) -> None:
        if self._running:
            self._cancel()
        else:
            self._start()

    def _show_validation_error(self, msg: str) -> None:
        self._validation_lbl.setText(f"⚠ {msg}")
        self._validation_lbl.setVisible(True)

    def _clear_validation_error(self) -> None:
        self._validation_lbl.setVisible(False)
        self._validation_lbl.setText("")

    def _estimate_cost(self, engine: str, n_files: int) -> str:
        """クラウドAPIの概算コストを返す（参考値）"""
        # 1画像あたりの概算トークン数（入力1600 + 出力200）
        tokens_per_image = 1800
        if engine == "claude":
            model = self._selected_model()
            # $/MTok: Opus 4.7=15, Sonnet 4.6=3
            price_per_mtok = 15.0 if "opus" in model else 3.0
            cost_usd = n_files * tokens_per_image / 1_000_000 * price_per_mtok
        elif engine == "hybrid":
            # Claude 使用率を約35%と仮定、Sonnet相当
            cost_usd = n_files * 0.35 * tokens_per_image / 1_000_000 * 3.0
        else:
            return ""
        return f"推定 API コスト: ~${cost_usd:.3f} USD（{n_files} ページ、参考値）"

    def _start(self) -> None:
        self._clear_validation_error()
        if not self._files:
            self._show_validation_error("処理するファイルを選択してください。")
            return
        if not self._selected_formats():
            self._show_validation_error("出力形式を1つ以上選択してください。")
            return
        out_dir = Path(self._output_edit.text().strip())
        if not out_dir.parent.exists():
            self._show_validation_error(f"出力先の親ディレクトリが存在しません: {out_dir.parent}")
            return

        self._running = True
        self._completed = 0
        self._open_btn.setVisible(False)
        self._start_btn.setText("キャンセル")
        self._start_btn.setObjectName("CancelBtn")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)
        self._clear_btn.setEnabled(False)
        total = len(self._files)
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._log.clear()
        engine = self._selected_engine()
        doc_type = self._selected_document_type()
        self._log_line(f"モード: {engine}  文書種別: {doc_type}  DPI: {self._dpi_spin.value()}")
        if engine == "hybrid":
            self._log_line(f"信頼度閾値: {self._selected_confidence():.2f}")
        if engine in ("claude", "hybrid"):
            self._log_line(f"モデル: {self._selected_model() or 'Sonnet 4.6'}")
            cost_str = self._estimate_cost(engine, total)
            if cost_str:
                self._log_line(cost_str)
        self._log_line(f"出力先: {out_dir}")
        self._log_line("─" * 50)

        self._worker = OCRWorker(
            files=[Path(p) for p in self._files],
            engine=engine,
            dpi=self._dpi_spin.value(),
            output_dir=out_dir,
            ocr_py=self.OCR_PY,
            spread=self._spread_check.isChecked(),
            formats=self._selected_formats(),
            api_key=self._selected_api_key(),
            document_type=doc_type,
            model=self._selected_model(),
            confidence_threshold=self._selected_confidence(),
        )
        self._worker.progress_line.connect(self._log_line)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._log_line("── キャンセルしました ──")
        self._finish_ui()

    def _on_file_started(self, filepath: str, index: int) -> None:
        total = len(self._files)
        name = Path(filepath).name
        self._status_lbl.setText(f"[{index}/{total}] {name} を処理中...")
        self._log_line(f"\n▶ [{index}/{total}] {name}")

    def _on_file_done(self, filepath: str, success: bool, message: str) -> None:
        name = Path(filepath).name
        mark = "✓" if success else "✗"
        self._log_line(f"{mark} {name}  {message}")
        self._completed += 1
        self._progress.setValue(self._completed)

    def _on_all_done(self) -> None:
        self._log_line("\n" + "─" * 50)
        self._log_line("すべての処理が完了しました。")
        self._status_lbl.setText("完了 ✓")
        self._open_btn.setVisible(True)
        self._finish_ui()

    def _finish_ui(self) -> None:
        self._running = False
        self._start_btn.setText("OCR 開始")
        self._start_btn.setObjectName("StartBtn")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)
        self._clear_btn.setEnabled(True)
        self._progress.setVisible(False)

    def _open_output(self) -> None:
        out_dir = Path(self._output_edit.text().strip())
        import subprocess as _sp
        _sp.Popen(["open", str(out_dir)])

    def _update_start_btn(self) -> None:
        self._start_btn.setEnabled(bool(self._files))

    def _log_line(self, text: str) -> None:
        self._log.append(text)
        sb = self._log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    # ── Stylesheet ───────────────────────────────

    def _apply_stylesheet(self) -> None:
        # Detect system dark mode via palette
        bg = self.palette().color(QPalette.ColorRole.Window)
        is_dark = bg.lightness() < 128

        if is_dark:
            base_bg      = "#1e1e2e"
            surface      = "#2a2a3e"
            border       = "#44475a"
            accent       = "#7c3aed"
            accent_hover = "#6d28d9"
            accent_fg    = "#ffffff"
            text_main    = "#e2e2e8"
            text_muted   = "#888899"
            chip_bg      = "#353550"
            log_bg       = "#141420"
            cancel_bg    = "#dc2626"
        else:
            base_bg      = "#f5f5fa"
            surface      = "#ffffff"
            border       = "#d1d1dd"
            accent       = "#6d28d9"
            accent_hover = "#5b21b6"
            accent_fg    = "#ffffff"
            text_main    = "#18181b"
            text_muted   = "#71717a"
            chip_bg      = "#ede9fe"
            log_bg     = "#f8f8fc"
            cancel_bg  = "#ef4444"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {base_bg};
                color: {text_main};
                font-family: "Helvetica Neue", "Hiragino Sans", "Yu Gothic", sans-serif;
            }}
            QLabel#Title {{
                color: {text_main};
            }}
            QGroupBox {{
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
                font-size: 12px;
                color: {text_muted};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 4px;
            }}
            QFrame#DropZone {{
                border: 2px dashed {border};
                border-radius: 12px;
                background-color: {surface};
            }}
            QFrame#DropZone[hovering="true"] {{
                border-color: {accent};
                background-color: {"#2e2a4e" if is_dark else "#f0ebff"};
            }}
            QLabel#DropIcon {{
                color: {accent};
            }}
            QPushButton#BrowseBtn {{
                background-color: transparent;
                color: {accent};
                border: 1px solid {accent};
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 12px;
            }}
            QPushButton#BrowseBtn:hover {{
                background-color: {accent};
                color: {accent_fg};
            }}
            QScrollArea#ChipArea {{
                border: 1px solid {border};
                border-radius: 8px;
                background-color: {surface};
            }}
            QWidget#ChipContainer {{
                background-color: {surface};
            }}
            QFrame#FileChip {{
                background-color: {chip_bg};
                border: 1px solid {accent};
                border-radius: 14px;
                color: {accent};
            }}
            QLabel#EmptyHint {{
                color: {text_muted};
                font-size: 12px;
            }}
            QRadioButton, QCheckBox {{
                spacing: 6px;
                color: {text_main};
            }}
            QRadioButton::indicator, QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid {border};
                background: {surface};
            }}
            QRadioButton::indicator:checked {{
                background: {accent};
                border-color: {accent};
            }}
            QCheckBox::indicator {{
                border-radius: 4px;
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border-color: {accent};
            }}
            QLineEdit, QSpinBox, QComboBox {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {text_main};
                selection-background-color: {accent};
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border-color: {accent};
            }}
            QPushButton {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 12px;
                color: {text_main};
            }}
            QPushButton:hover {{
                border-color: {accent};
                color: {accent};
            }}
            QPushButton#StartBtn {{
                background-color: {accent};
                color: {accent_fg};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#StartBtn:hover {{
                background-color: {"#6d28d9" if not is_dark else "#8b5cf6"};
                color: {accent_fg};
            }}
            QPushButton#StartBtn:disabled {{
                background-color: {border};
                color: {text_muted};
            }}
            QPushButton#CancelBtn {{
                background-color: {cancel_bg};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#ClearBtn {{
                font-size: 12px;
            }}
            QPushButton#OpenBtn {{
                background-color: {accent};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#OpenBtn:hover {{
                background-color: {accent_hover};
            }}
            QProgressBar {{
                border: 1px solid {border};
                border-radius: 4px;
                background-color: {border};
                text-align: center;
                font-size: 11px;
                color: {text_main};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 3px;
            }}
            QTextEdit#LogArea {{
                background-color: {log_bg};
                border: 1px solid {border};
                border-radius: 6px;
                color: {text_main};
                font-family: "Menlo", "Consolas", monospace;
                font-size: 11px;
            }}
            QLabel#StatusLabel {{
                color: {text_muted};
                font-size: 12px;
            }}
            QLabel#ValidationLabel {{
                color: #e05555;
                font-size: 12px;
                padding: 4px 8px;
                border: 1px solid #e05555;
                border-radius: 4px;
                background-color: rgba(224, 85, 85, 0.08);
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar:horizontal {{
                height: 8px;
                background: transparent;
            }}
            QScrollBar::handle:horizontal {{
                background: {border};
                border-radius: 4px;
                min-width: 20px;
            }}
        """)
        self._update_start_btn()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("OCR Launcher")
    app.setApplicationVersion("1.0.0")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
