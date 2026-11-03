"""환경설정 · 미디어 정보 · 영상 조정 · 이퀄라이저 · 단축키 도움말 창."""
import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QFormLayout,
                               QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton,
                               QLabel, QSlider, QDialogButtonBox, QFileDialog, QColorDialog,
                               QFontComboBox, QPlainTextEdit, QGridLayout, QTableWidget,
                               QTableWidgetItem, QHeaderView)

from keys import SHORTCUTS
from version import APP_NAME, VERSION


def _combo(items, current):
    c = QComboBox()
    for val, label in items:
        c.addItem(label, val)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


class ColorButton(QPushButton):
    def __init__(self, color):
        super().__init__()
        self.color = color
        self.setFixedWidth(90)
        self.clicked.connect(self.pick)
        self._paint()

    def _paint(self):
        c = QColor(self.color)
        fg = "#000" if c.lightness() > 128 else "#fff"
        self.setText(self.color.upper())
        self.setStyleSheet(f"background:{self.color}; color:{fg}; border:1px solid #555; border-radius:5px;")

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "색 고르기")
        if c.isValid():
            self.color = c.name()
            self._paint()


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("환경설정")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs)
        s = store
        self.w = {}

        # --- 일반
        g = QWidget()
        f = QFormLayout(g)
        f.setVerticalSpacing(10)
        self.w["single_instance"] = QCheckBox("파일을 더블클릭하면 이미 열린 플레이어 창에서 재생")
        self.w["resume_mode"] = _combo([("auto", "자동으로 이어보기"), ("ask", "물어보기"), ("off", "항상 처음부터")], s["resume_mode"])
        self.w["auto_folder_playlist"] = QCheckBox("파일 하나를 열면 같은 폴더의 영상도 재생목록에 추가")
        self.w["autoplay_next"] = QCheckBox("영상이 끝나면 다음 영상 자동 재생")
        self.w["click_to_pause"] = QCheckBox("영상 한 번 클릭으로 재생/일시정지 (더블클릭은 전체 화면)")
        self.w["wheel_action"] = _combo([("volume", "볼륨 조절"), ("seek", "앞뒤 탐색")], s["wheel_action"])
        self.w["esc_quits"] = QCheckBox("창 모드에서 Esc 누르면 종료 (예전 버전과 같게)")
        self.w["fit_window_on_open"] = QCheckBox("영상을 열면 창 크기를 영상에 맞춤")
        self.w["remember_window"] = QCheckBox("창 위치·크기 기억")
        self.w["always_on_top"] = _combo([("never", "사용 안 함"), ("always", "항상"), ("playing", "재생 중일 때만")], s["always_on_top"])
        self.w["check_updates"] = QCheckBox("켤 때 새 버전 자동 확인 (GitHub)")
        self.w["seek_small"] = QSpinBox()
        self.w["seek_small"].setRange(1, 60)
        self.w["seek_small"].setSuffix(" 초")
        self.w["seek_large"] = QSpinBox()
        self.w["seek_large"].setRange(5, 600)
        self.w["seek_large"].setSuffix(" 초")
        for k in ("single_instance", "auto_folder_playlist", "autoplay_next", "click_to_pause", "esc_quits",
                  "fit_window_on_open", "remember_window", "check_updates"):
            self.w[k].setChecked(bool(s[k]))
        self.w["seek_small"].setValue(int(s["seek_small"]))
        self.w["seek_large"].setValue(int(s["seek_large"]))
        f.addRow("이어보기", self.w["resume_mode"])
        f.addRow("", self.w["single_instance"])
        f.addRow("", self.w["auto_folder_playlist"])
        f.addRow("", self.w["autoplay_next"])
        f.addRow("", self.w["click_to_pause"])
        f.addRow("마우스 휠", self.w["wheel_action"])
        f.addRow("←/→ 탐색 간격", self.w["seek_small"])
        f.addRow("Ctrl+←/→ 간격", self.w["seek_large"])
        f.addRow("항상 위", self.w["always_on_top"])
        f.addRow("", self.w["esc_quits"])
        f.addRow("", self.w["fit_window_on_open"])
        f.addRow("", self.w["remember_window"])
        f.addRow("", self.w["check_updates"])
        tabs.addTab(g, "일반")

        # --- 영상
        g = QWidget()
        f = QFormLayout(g)
        f.setVerticalSpacing(10)
        self.w["hwdec"] = QCheckBox("하드웨어 가속 디코딩 (끄면 호환성↑, CPU 사용↑)")
        self.w["hwdec"].setChecked(bool(s["hwdec"]))
        self.w["deinterlace"] = _combo([("auto", "자동"), ("yes", "항상"), ("no", "끄기")], s["deinterlace"])
        self.w["thumbnails"] = QCheckBox("시크바에 마우스를 올리면 미리보기 썸네일 표시")
        self.w["thumbnails"].setChecked(bool(s["thumbnails"]))
        self.w["ytdl_quality"] = _combo([("best", "최고 화질"), ("2160", "4K까지"), ("1440", "1440p까지"),
                                         ("1080", "1080p까지"), ("720", "720p까지"), ("480", "480p까지")], s["ytdl_quality"])
        row = QHBoxLayout()
        self.w["shot_dir"] = QLineEdit(s["shot_dir"])
        self.w["shot_dir"].setPlaceholderText("기본: 사진\\코덱무관플레이어")
        b = QPushButton("찾기…")
        b.clicked.connect(self._pick_dir)
        row.addWidget(self.w["shot_dir"], 1)
        row.addWidget(b)
        self.w["shot_format"] = _combo([("png", "PNG (무손실)"), ("jpg", "JPG"), ("webp", "WEBP")], s["shot_format"])
        self.w["shot_with_subs"] = QCheckBox("캡처에 자막 포함")
        self.w["shot_with_subs"].setChecked(bool(s["shot_with_subs"]))
        f.addRow("", self.w["hwdec"])
        f.addRow("디인터레이스", self.w["deinterlace"])
        f.addRow("", self.w["thumbnails"])
        f.addRow("유튜브 화질", self.w["ytdl_quality"])
        f.addRow("캡처 저장 폴더", row)
        f.addRow("캡처 형식", self.w["shot_format"])
        f.addRow("", self.w["shot_with_subs"])
        tabs.addTab(g, "영상")

        # --- 소리
        g = QWidget()
        f = QFormLayout(g)
        f.setVerticalSpacing(10)
        self.w["volume_max"] = _combo([(100, "100%"), (150, "150%"), (200, "200%")], s["volume_max"])
        self.w["audio_lang"] = QLineEdit(s["audio_lang"])
        f.addRow("최대 볼륨", self.w["volume_max"])
        f.addRow("선호 오디오 언어", self.w["audio_lang"])
        f.addRow("", QLabel("쉼표로 구분 (예: ko,ja,en) — 여러 오디오 트랙이 있으면 이 순서로 고릅니다"))
        tabs.addTab(g, "소리")

        # --- 자막
        g = QWidget()
        f = QFormLayout(g)
        f.setVerticalSpacing(10)
        self.w["sub_auto"] = QCheckBox("영상과 이름이 비슷한 자막 파일(srt·smi·ass…) 자동으로 불러오기")
        self.w["sub_auto"].setChecked(bool(s["sub_auto"]))
        self.w["sub_lang"] = QLineEdit(s["sub_lang"])
        self.w["sub_font"] = QFontComboBox()
        self.w["sub_font"].setCurrentText(s["sub_font"])
        self.w["sub_size"] = QSpinBox()
        self.w["sub_size"].setRange(16, 120)
        self.w["sub_size"].setValue(int(s["sub_size"]))
        self.w["sub_bold"] = QCheckBox("굵게")
        self.w["sub_bold"].setChecked(bool(s["sub_bold"]))
        self.w["sub_color"] = ColorButton(s["sub_color"])
        self.w["sub_border_color"] = ColorButton(s["sub_border_color"])
        self.w["sub_border"] = QDoubleSpinBox()
        self.w["sub_border"].setRange(0, 10)
        self.w["sub_border"].setSingleStep(0.5)
        self.w["sub_border"].setValue(float(s["sub_border"]))
        self.w["sub_back_box"] = QCheckBox("자막 뒤에 반투명 배경 상자")
        self.w["sub_back_box"].setChecked(bool(s["sub_back_box"]))
        self.w["sub_pos"] = QSpinBox()
        self.w["sub_pos"].setRange(0, 150)
        self.w["sub_pos"].setValue(int(s["sub_pos"]))
        self.w["sub_pos"].setSuffix(" (100=맨 아래)")
        f.addRow("", self.w["sub_auto"])
        f.addRow("선호 자막 언어", self.w["sub_lang"])
        f.addRow("글꼴", self.w["sub_font"])
        f.addRow("크기", self.w["sub_size"])
        f.addRow("", self.w["sub_bold"])
        f.addRow("글자 색", self.w["sub_color"])
        f.addRow("테두리 색", self.w["sub_border_color"])
        f.addRow("테두리 두께", self.w["sub_border"])
        f.addRow("", self.w["sub_back_box"])
        f.addRow("세로 위치", self.w["sub_pos"])
        f.addRow("", QLabel("※ ASS 자막은 자막 파일에 들어 있는 스타일이 우선합니다"))
        tabs.addTab(g, "자막")

        # --- 파일 연결
        g = QWidget()
        lv = QVBoxLayout(g)
        lab = QLabel("설치할 때 '영상 파일 연결'을 체크했다면 탐색기의 '연결 프로그램'에 코덱무관플레이어가 들어 있어요.\n"
                     "Windows 10/11은 앱이 기본 프로그램을 마음대로 바꿀 수 없어서,\n"
                     "아래 버튼으로 Windows 설정을 연 뒤 '코덱무관플레이어'를 직접 골라 주세요.\n\n"
                     "또는 영상 파일 우클릭 → 연결 프로그램 → 다른 앱 선택 → 코덱무관플레이어 → '항상 이 앱 사용'.")
        lab.setWordWrap(True)
        lv.addWidget(lab)
        b = QPushButton("Windows 기본 앱 설정 열기")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")))
        lv.addWidget(b, 0, Qt.AlignLeft)
        b2 = QPushButton("설정·기록 폴더 열기")
        b2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(store.dir)))
        lv.addWidget(b2, 0, Qt.AlignLeft)
        lv.addStretch(1)
        tabs.addTab(g, "파일 연결")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("확인")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "캡처 저장 폴더", self.w["shot_dir"].text() or os.path.expanduser("~"))
        if d:
            self.w["shot_dir"].setText(d)

    def apply(self):
        s = self.store
        for k, w in self.w.items():
            if isinstance(w, QCheckBox):
                s[k] = w.isChecked()
            elif isinstance(w, QFontComboBox):
                s[k] = w.currentText()
            elif isinstance(w, QComboBox):
                s[k] = w.currentData()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                s[k] = w.value()
            elif isinstance(w, QLineEdit):
                s[k] = w.text().strip()
            elif isinstance(w, ColorButton):
                s[k] = w.color
        s.save()


class MediaInfoDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("미디어 정보")
        self.resize(620, 520)
        v = QVBoxLayout(self)
        ed = QPlainTextEdit(text)
        ed.setReadOnly(True)
        ed.setStyleSheet("font-family: Consolas, 'Malgun Gothic', monospace;")
        v.addWidget(ed)
        h = QHBoxLayout()
        h.addStretch(1)
        b = QPushButton("복사")
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(text))
        c = QPushButton("닫기")
        c.clicked.connect(self.accept)
        h.addWidget(b)
        h.addWidget(c)
        v.addLayout(h)


class SliderPanel(QDialog):
    """여러 개의 슬라이더로 실시간 조정하는 작은 창 (영상 조정, 이퀄라이저 공용)."""
    changed = Signal(list)

    def __init__(self, title, labels, values, rng=(-100, 100), vertical=False, presets=None, parent=None,
                 unit=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.sliders = []
        self.vals = []
        v = QVBoxLayout(self)
        grid = QGridLayout()
        v.addLayout(grid)
        for i, (lab, val) in enumerate(zip(labels, values)):
            s = QSlider(Qt.Vertical if vertical else Qt.Horizontal)
            s.setRange(*rng)
            s.setValue(int(val))
            vl = QLabel(f"{int(val)}{unit}")
            vl.setMinimumWidth(42)
            vl.setAlignment(Qt.AlignCenter)
            nl = QLabel(lab)
            nl.setAlignment(Qt.AlignCenter)
            s.valueChanged.connect(lambda x, vl=vl: (vl.setText(f"{x}{unit}"), self._emit()))
            if vertical:
                s.setMinimumHeight(170)
                grid.addWidget(vl, 0, i, Qt.AlignCenter)
                grid.addWidget(s, 1, i, Qt.AlignHCenter)
                grid.addWidget(nl, 2, i, Qt.AlignCenter)
            else:
                s.setMinimumWidth(260)
                grid.addWidget(nl, i, 0)
                grid.addWidget(s, i, 1)
                grid.addWidget(vl, i, 2)
            self.sliders.append(s)
        h = QHBoxLayout()
        if presets:
            self.preset = QComboBox()
            self.preset.addItem("프리셋…", None)
            for name, vals in presets:
                self.preset.addItem(name, vals)
            self.preset.activated.connect(self._preset)
            h.addWidget(self.preset)
        h.addStretch(1)
        r = QPushButton("초기화")
        r.clicked.connect(lambda: self.set_values([0] * len(self.sliders)))
        c = QPushButton("닫기")
        c.clicked.connect(self.close)
        h.addWidget(r)
        h.addWidget(c)
        v.addLayout(h)

    def _preset(self, i):
        vals = self.preset.itemData(i)
        if vals:
            self.set_values(vals)

    def set_values(self, vals):
        for s, x in zip(self.sliders, vals):
            s.blockSignals(True)
            s.setValue(int(x))
            s.blockSignals(False)
            s.valueChanged.emit(int(x))
        self._emit()

    def _emit(self):
        self.changed.emit([s.value() for s in self.sliders])


EQ_BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_PRESETS = [
    ("평탄", [0] * 10),
    ("저음 강화", [7, 6, 5, 3, 1, 0, 0, 0, 0, 0]),
    ("고음 강화", [0, 0, 0, 0, 0, 1, 3, 5, 6, 7]),
    ("목소리(대사) 강조", [-4, -3, -1, 1, 3, 5, 5, 3, 1, 0]),
    ("록", [5, 4, 2, -1, -2, -1, 2, 4, 5, 5]),
    ("팝", [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2]),
    ("클래식", [4, 3, 2, 1, 0, 0, 0, 1, 2, 3]),
    ("헤드폰", [3, 5, 3, -1, -2, 0, 2, 4, 5, 6]),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("단축키")
        self.resize(640, 640)
        v = QVBoxLayout(self)
        t = QTableWidget(0, 3)
        t.setHorizontalHeaderLabels(["분류", "키", "기능"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionMode(QTableWidget.NoSelection)
        t.setStyleSheet("QTableWidget{background:#1b1b22; gridline-color:#2c2c36;} QHeaderView::section{background:#23232c; padding:5px; border:none;}")
        pretty = {"SPACE": "Space", "ENTER": "Enter", "KP_ENTER": "숫자패드 Enter", "ESC": "Esc", "LEFT": "←",
                  "RIGHT": "→", "UP": "↑", "DOWN": "↓", "PGUP": "PgUp", "PGDWN": "PgDn", "HOME": "Home",
                  "TAB": "Tab", "KP_ADD": "숫자패드 +", "KP_SUBTRACT": "숫자패드 -"}
        skip = {"PLAYPAUSE", "PREV", "NEXT", "MUTE", "Shift+Alt+UP", "Shift+Alt+DOWN"}
        for keys, _, desc, grp in SHORTCUTS:
            shown = []
            for k in keys:
                if k in skip:
                    continue
                parts = k.split("+")
                parts = [pretty.get(p, p.upper() if len(p) == 1 else p) for p in parts]
                shown.append("+".join(parts))
            if keys[0] == "0":
                shown = ["0 ~ 9"]
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(grp))
            t.setItem(r, 1, QTableWidgetItem(" / ".join(shown)))
            t.setItem(r, 2, QTableWidgetItem(desc))
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        v.addWidget(t)
        v.addWidget(QLabel("마우스: 클릭 재생/정지 · 더블클릭 전체 화면 · 휠 볼륨 · Ctrl+휠 확대 · 가운데 클릭 음소거 · 우클릭 메뉴\n"
                           "* Esc 종료는 환경설정에서 끌 수 있어요."))
        c = QPushButton("닫기")
        c.clicked.connect(self.accept)
        v.addWidget(c, 0, Qt.AlignRight)


def about_text():
    return (f"<h3>{APP_NAME} {VERSION}</h3>"
            "<p>코덱 설치 없이 거의 모든 영상을 재생하는 플레이어<br>"
            "재생 엔진: mpv (libmpv) · FFmpeg · 화면: Qt</p>"
            "<p>GitHub 릴리스로 자동 업데이트됩니다.</p>")
