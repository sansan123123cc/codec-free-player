"""UI 부품: 아이콘, 시크바(미리보기·챕터·A-B·북마크 표시), 컨트롤바, 시작 화면."""
import math
import os

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QTimer, QPoint
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QIcon, QPixmap, QFont,
                           QFontMetrics, QLinearGradient, QBrush)
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QLabel, QSlider,
                               QPushButton, QListWidget, QListWidgetItem, QSizePolicy, QFrame)

ACCENT = QColor("#ff5c8a")
FG = QColor("#e8e8ee")
DIM = QColor("#9a9aa8")
BG = "#15151b"


def fmt_time(sec, force_hours=False):
    if sec is None or sec != sec or sec < 0:
        sec = 0
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h or force_hours:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ------------------------------------------------------------------ 아이콘
def make_icon(kind, color=FG, size=40):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    s = size / 24.0
    p.scale(s, s)
    pen = QPen(c, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def poly(*pts):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        path.closeSubpath()
        p.drawPath(path)

    if kind == "play":
        poly((7, 4.5), (19.5, 12), (7, 19.5))
    elif kind == "pause":
        p.drawRoundedRect(QRectF(6, 4.5, 4, 15), 1, 1)
        p.drawRoundedRect(QRectF(14, 4.5, 4, 15), 1, 1)
    elif kind == "stop":
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 1.5, 1.5)
    elif kind == "prev":
        p.drawRect(QRectF(5, 5, 2.4, 14))
        poly((19, 5), (8.5, 12), (19, 19))
    elif kind == "next":
        p.drawRect(QRectF(16.6, 5, 2.4, 14))
        poly((5, 5), (15.5, 12), (5, 19))
    elif kind in ("vol", "mute", "vol_low"):
        poly((3, 9), (7, 9), (12, 4.5), (12, 19.5), (7, 15), (3, 15))
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        if kind == "mute":
            p.drawLine(QPointF(15.5, 9), QPointF(21, 15))
            p.drawLine(QPointF(21, 9), QPointF(15.5, 15))
        else:
            p.drawArc(QRectF(9, 8, 8, 8), -50 * 16, 100 * 16)
            if kind == "vol":
                p.drawArc(QRectF(7, 4.5, 14, 15), -50 * 16, 100 * 16)
    elif kind in ("fullscreen", "unfullscreen"):
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        if kind == "fullscreen":
            for a, b, cc in (((4, 9), (4, 4), (9, 4)), ((15, 4), (20, 4), (20, 9)),
                             ((20, 15), (20, 20), (15, 20)), ((9, 20), (4, 20), (4, 15))):
                p.drawPolyline([QPointF(*a), QPointF(*b), QPointF(*cc)])
        else:
            for a, b, cc in (((4, 9), (9, 9), (9, 4)), ((15, 4), (15, 9), (20, 9)),
                             ((20, 15), (15, 15), (15, 20)), ((9, 20), (9, 15), (4, 15))):
                p.drawPolyline([QPointF(*a), QPointF(*b), QPointF(*cc)])
    elif kind == "playlist":
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        for y in (6, 11, 16):
            p.drawLine(QPointF(4, y), QPointF(14, y))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        poly((16, 12), (21, 15.5), (16, 19))
    elif kind == "menu":
        for x in (5, 12, 19):
            p.drawEllipse(QPointF(x, 12), 2, 2)
    elif kind == "camera":
        path = QPainterPath()
        path.addRoundedRect(QRectF(3, 7, 18, 12.5), 2.5, 2.5)
        path.addRect(QRectF(8, 4.5, 8, 3))
        p.drawPath(path)
        p.setBrush(QColor(BG))
        p.drawEllipse(QPointF(12, 13.2), 3.8, 3.8)
        p.setBrush(c)
        p.drawEllipse(QPointF(12, 13.2), 2.2, 2.2)
    elif kind == "cc":
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(3, 5.5, 18, 13), 2.5, 2.5)
        f = QFont("Arial", 7, QFont.Bold)
        p.setFont(f)
        p.drawText(QRectF(3, 5.5, 18, 13), Qt.AlignCenter, "CC")
    elif kind == "open":
        path = QPainterPath()
        path.moveTo(3, 6)
        path.lineTo(9, 6)
        path.lineTo(11, 8)
        path.lineTo(21, 8)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "repeat":
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawPolyline([QPointF(5, 13), QPointF(5, 8), QPointF(18, 8)])
        p.drawPolyline([QPointF(19, 11), QPointF(19, 16), QPointF(6, 16)])
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        poly((17, 5), (21, 8), (17, 11))
        poly((7, 13), (3, 16), (7, 19))
    elif kind == "app":
        g = QLinearGradient(0, 0, 24, 24)
        g.setColorAt(0, QColor("#ff7aa2"))
        g.setColorAt(1, QColor("#8a5cff"))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(1, 1, 22, 22), 6, 6)
        p.setBrush(QColor("white"))
        poly((9, 6.5), (18, 12), (9, 17.5))
    p.end()
    return QIcon(pm)


class IconButton(QToolButton):
    def __init__(self, kind, tip="", parent=None, size=34):
        super().__init__(parent)
        self.kind = kind
        self.setIcon(make_icon(kind))
        self.setIconSize(QSize(int(size * 0.62), int(size * 0.62)))
        self.setFixedSize(size, size)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(True)

    def set_kind(self, kind, color=FG):
        if kind != self.kind or color != FG:
            self.kind = kind
            self.setIcon(make_icon(kind, color))


# ------------------------------------------------------------------ 썸네일 팝업
class ThumbPopup(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.img = None
        self.text = ""
        self.sub = ""
        self.setStyleSheet("background:#000;")

    def set_content(self, img, text, sub=""):
        self.img = img
        self.text = text
        self.sub = sub
        w = img.width() if img is not None else 0
        fm = QFontMetrics(self._font())
        tw = max(fm.horizontalAdvance(text), fm.horizontalAdvance(sub) if sub else 0) + 20
        w = max(w + 4, tw, 70)
        h = (img.height() + 4 if img is not None else 0) + (24 if not sub else 42)
        self.resize(w, h)
        self.update()

    def _font(self):
        f = QFont(self.font())
        f.setPointSize(10)
        f.setBold(True)
        return f

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 10, 14))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        y = 2
        if self.img is not None:
            x = (self.width() - self.img.width()) // 2
            p.drawImage(x, y, self.img)
            y += self.img.height() + 2
        p.setFont(self._font())
        p.setPen(QColor("white"))
        if self.sub:
            f2 = QFont(self._font())
            f2.setBold(False)
            f2.setPointSize(9)
            p.setFont(f2)
            p.setPen(QColor("#ffd0de"))
            p.drawText(QRectF(4, y, self.width() - 8, 20), Qt.AlignCenter,
                       QFontMetrics(f2).elidedText(self.sub, Qt.ElideRight, self.width() - 10))
            y += 18
            p.setFont(self._font())
            p.setPen(QColor("white"))
        p.drawText(QRectF(0, y, self.width(), 22), Qt.AlignCenter, self.text)


# ------------------------------------------------------------------ 시크바
class SeekBar(QWidget):
    seek_requested = Signal(float, bool)   # sec, final(=정확 탐색)
    hover_changed = Signal(object, QPoint)  # sec or None, global pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.duration = 0.0
        self.pos_sec = 0.0
        self.cache_end = None
        self.chapters = []     # [(sec, title)]
        self.bookmarks = []    # [sec]
        self.ab = (None, None)
        self.hover_x = None
        self.dragging = False

    def set_state(self, pos, dur, cache_end=None):
        changed = False
        if dur is not None and abs((dur or 0) - self.duration) > 0.01:
            self.duration = dur or 0.0
            changed = True
        if not self.dragging and pos is not None and abs(pos - self.pos_sec) > 0.01:
            self.pos_sec = pos
            changed = True
        if cache_end != self.cache_end:
            self.cache_end = cache_end
            changed = True
        if changed:
            self.update()

    def _track(self):
        return QRectF(8, self.height() / 2 - 2, self.width() - 16, 4)

    def sec_at(self, x):
        t = self._track()
        if self.duration <= 0:
            return None
        r = min(1.0, max(0.0, (x - t.left()) / max(1, t.width())))
        return r * self.duration

    def x_at(self, sec):
        t = self._track()
        if self.duration <= 0:
            return t.left()
        return t.left() + t.width() * min(1.0, max(0.0, sec / self.duration))

    def chapter_at(self, sec):
        title = ""
        for s, ttl in self.chapters:
            if s <= sec:
                title = ttl
        return title

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._track()
        hover = self.hover_x is not None or self.dragging
        if hover:
            t = t.adjusted(0, -1.5, 0, 1.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 50))
        p.drawRoundedRect(t, 2, 2)
        if self.duration > 0:
            if self.cache_end:
                ce = self.x_at(self.cache_end)
                p.setBrush(QColor(255, 255, 255, 70))
                p.drawRoundedRect(QRectF(t.left(), t.top(), ce - t.left(), t.height()), 2, 2)
            if self.hover_x is not None:
                p.setBrush(QColor(255, 255, 255, 60))
                hx = min(max(self.hover_x, t.left()), t.right())
                p.drawRect(QRectF(t.left(), t.top(), hx - t.left(), t.height()))
            a, b = self.ab
            if a is not None:
                xa = self.x_at(a)
                xb = self.x_at(b) if b is not None else xa + 2
                p.setBrush(QColor(120, 200, 255, 140))
                p.drawRect(QRectF(xa, t.top() - 3, max(2, xb - xa), t.height() + 6))
            x = self.x_at(self.pos_sec)
            p.setBrush(ACCENT)
            p.drawRoundedRect(QRectF(t.left(), t.top(), x - t.left(), t.height()), 2, 2)
            # 챕터 경계 (트랙에 작은 틈)
            p.setBrush(QColor(BG))
            for s, _ in self.chapters:
                if s > 0.5:
                    cx = self.x_at(s)
                    p.drawRect(QRectF(cx - 1, t.top(), 2, t.height()))
            # 북마크
            p.setBrush(QColor("#ffd34d"))
            for s in self.bookmarks:
                bx = self.x_at(s)
                path = QPainterPath(QPointF(bx, t.top() - 1))
                path.lineTo(bx - 4, t.top() - 7)
                path.lineTo(bx + 4, t.top() - 7)
                path.closeSubpath()
                p.drawPath(path)
            if hover:
                p.setBrush(ACCENT)
                p.drawEllipse(QPointF(x, t.center().y()), 7, 7)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.duration > 0:
            self.dragging = True
            s = self.sec_at(e.position().x())
            if s is not None:
                self.pos_sec = s
                self.seek_requested.emit(s, False)
            self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self.hover_x = x
        s = self.sec_at(x)
        if self.dragging and s is not None:
            self.pos_sec = s
            self.seek_requested.emit(s, False)
        gp = self.mapToGlobal(QPoint(int(self.x_at(s) if s is not None else x), 0))
        self.hover_changed.emit(s, gp)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            s = self.sec_at(e.position().x())
            if s is not None:
                self.pos_sec = s
                self.seek_requested.emit(s, True)
            self.update()

    def leaveEvent(self, e):
        self.hover_x = None
        self.hover_changed.emit(None, QPoint())
        self.update()


# ------------------------------------------------------------------ 볼륨 슬라이더
class VolumeSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 200)
        self.setFixedWidth(96)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / max(1, self.width())
            self.setValue(int(round(v)))
            e.accept()
        super().mousePressEvent(e)


# ------------------------------------------------------------------ 컨트롤바
class ControlBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlBar")
        self.setFocusPolicy(Qt.NoFocus)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 2, 8, 6)
        v.setSpacing(0)
        self.seek = SeekBar()
        v.addWidget(self.seek)
        h = QHBoxLayout()
        h.setSpacing(2)
        v.addLayout(h)
        self.b_prev = IconButton("prev", "이전 파일 (PgUp)")
        self.b_play = IconButton("play", "재생 / 일시정지 (Space, K)", size=40)
        self.b_next = IconButton("next", "다음 파일 (PgDn)")
        self.b_stop = IconButton("stop", "정지")
        self.b_vol = IconButton("vol", "음소거 (M)")
        self.vol = VolumeSlider()
        self.vol_label = QLabel("80%")
        self.vol_label.setObjectName("dim")
        self.vol_label.setFixedWidth(40)
        self.time = QPushButton("00:00 / 00:00")
        self.time.setObjectName("timeBtn")
        self.time.setFlat(True)
        self.time.setFocusPolicy(Qt.NoFocus)
        self.time.setCursor(Qt.PointingHandCursor)
        self.time.setToolTip("클릭: 남은 시간 / 전체 시간 전환")
        self.time.setMinimumWidth(QFontMetrics(QFont("Consolas", 10)).horizontalAdvance("-0:00:00 / 0:00:00") + 16)
        self.time.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.title = QLabel("")
        self.title.setObjectName("dim")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.b_ab = QPushButton("A-B")
        self.b_ab.setObjectName("chip")
        self.b_ab.setToolTip("구간 반복: [ 시작점, ] 끝점, \\ 해제")
        self.b_speed = QPushButton("1.0x")
        self.b_speed.setObjectName("chip")
        self.b_speed.setToolTip("재생 속도 (C 빠르게 / X 느리게 / Z 원래대로)")
        for b in (self.b_ab, self.b_speed):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
        self.b_repeat = IconButton("repeat", "반복 모드")
        self.b_cc = IconButton("cc", "자막 (클릭: 켜기/끄기, 우클릭: 자막 메뉴)")
        self.b_shot = IconButton("camera", "화면 캡처 (Ctrl+E)")
        self.b_list = IconButton("playlist", "재생목록 (P)")
        self.b_menu = IconButton("menu", "메뉴")
        self.b_full = IconButton("fullscreen", "전체 화면 (Enter, F)")
        for w in (self.b_prev, self.b_play, self.b_next, self.b_stop, self.b_vol, self.vol,
                  self.vol_label, self.time):
            h.addWidget(w)
        h.addSpacing(6)
        h.addWidget(self.title, 1)
        for w in (self.b_ab, self.b_speed, self.b_repeat, self.b_cc, self.b_shot, self.b_list,
                  self.b_menu, self.b_full):
            h.addWidget(w)

    def resizeEvent(self, e):
        # 창이 좁으면 덜 중요한 버튼부터 숨김
        w = e.size().width()
        for widget, minw in ((self.vol_label, 820), (self.b_stop, 760), (self.b_repeat, 720), (self.b_ab, 680),
                             (self.b_shot, 640), (self.vol, 590), (self.b_list, 560)):
            widget.setVisible(w >= minw)
        super().resizeEvent(e)


# ------------------------------------------------------------------ 재생목록
class PlaylistPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Playlist")
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        top = QHBoxLayout()
        lab = QLabel("재생목록")
        lab.setObjectName("h2")
        self.count = QLabel("")
        self.count.setObjectName("dim")
        top.addWidget(lab)
        top.addWidget(self.count)
        top.addStretch(1)
        self.b_add = QPushButton("+ 추가")
        self.b_add.setObjectName("chip")
        self.b_more = QPushButton("···")
        self.b_more.setObjectName("chip")
        for b in (self.b_add, self.b_more):
            b.setFocusPolicy(Qt.NoFocus)
            top.addWidget(b)
        v.addLayout(top)
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setFocusPolicy(Qt.ClickFocus)
        self.list.setTextElideMode(Qt.ElideMiddle)
        v.addWidget(self.list, 1)


# ------------------------------------------------------------------ 시작 화면
class WelcomePage(QWidget):
    open_file = Signal()
    open_folder = Signal()
    open_url = Signal()
    open_recent = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Welcome")
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        v.addStretch(2)
        logo = QLabel()
        logo.setPixmap(make_icon("app", size=84).pixmap(84, 84))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        t = QLabel("코덱무관플레이어")
        t.setObjectName("h1")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        s = QLabel("영상을 여기로 끌어다 놓거나 아래 버튼으로 열어 주세요\nHEVC · AV1 · VP9 · MKV · 유튜브 주소까지 코덱 걱정 없이")
        s.setObjectName("dim")
        s.setAlignment(Qt.AlignCenter)
        v.addWidget(s)
        v.addSpacing(14)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, sig in (("파일 열기  Ctrl+O", self.open_file), ("폴더 열기", self.open_folder),
                          ("주소(URL) 열기  Ctrl+U", self.open_url)):
            b = QPushButton(text)
            b.setObjectName("big")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(sig.emit)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        v.addSpacing(18)
        self.recent_title = QLabel("최근 재생")
        self.recent_title.setObjectName("h2")
        self.recent_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.recent_title)
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setFixedWidth(520)
        self.recent.setFixedHeight(180)
        self.recent.setFocusPolicy(Qt.NoFocus)
        self.recent.itemActivated.connect(lambda it: self.open_recent.emit(it.data(Qt.UserRole)))
        self.recent.itemClicked.connect(lambda it: self.open_recent.emit(it.data(Qt.UserRole)))
        rw = QHBoxLayout()
        rw.addStretch(1)
        rw.addWidget(self.recent)
        rw.addStretch(1)
        v.addLayout(rw)
        hint = QLabel("F1 단축키 보기 · 우클릭 메뉴 · F5 환경설정")
        hint.setObjectName("dim")
        hint.setAlignment(Qt.AlignCenter)
        v.addSpacing(8)
        v.addWidget(hint)
        v.addStretch(3)

    def set_recent(self, paths, positions):
        self.recent.clear()
        shown = 0
        for p in paths:
            if shown >= 8:
                break
            is_url = "://" in p
            if not is_url and not os.path.exists(p):
                continue
            name = p if is_url else os.path.basename(p)
            e = positions.get(p)
            if e and e.get("dur"):
                name += f"   ·  {fmt_time(e['pos'])} / {fmt_time(e['dur'])}에서 이어보기"
            it = QListWidgetItem(name)
            it.setToolTip(p)
            it.setData(Qt.UserRole, p)
            self.recent.addItem(it)
            shown += 1
        self.recent_title.setVisible(shown > 0)
        self.recent.setVisible(shown > 0)


STYLE = f"""
QWidget {{ color: #e8e8ee; font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans CJK KR', sans-serif; font-size: 10pt; }}
QMainWindow, #Central, #Welcome {{ background: {BG}; }}
#VideoHost {{ background: #000; }}
#ControlBar {{ background: #1b1b22; border-top: 1px solid #26262f; }}
#Playlist {{ background: #18181f; border-left: 1px solid #26262f; }}
QLabel#dim {{ color: #9a9aa8; }}
QLabel#h1 {{ font-size: 20pt; font-weight: bold; color: #fff; }}
QLabel#h2 {{ font-size: 11pt; font-weight: bold; color: #fff; }}
QToolButton {{ border: none; border-radius: 6px; background: transparent; }}
QToolButton:hover {{ background: rgba(255,255,255,0.10); }}
QPushButton#timeBtn {{ border: none; background: transparent; padding: 0 6px; font-family: Consolas, 'Malgun Gothic', monospace; color: #e8e8ee; }}
QPushButton#timeBtn:hover {{ color: #fff; }}
QPushButton#chip {{ border: 1px solid #3a3a46; border-radius: 10px; padding: 2px 9px; background: #23232c; min-height: 18px; }}
QPushButton#chip:hover {{ border-color: #ff5c8a; }}
QPushButton#chip[active="true"] {{ background: #ff5c8a; border-color: #ff5c8a; color: #fff; }}
QPushButton#big {{ border: 1px solid #3a3a46; border-radius: 10px; padding: 10px 18px; background: #23232c; font-size: 11pt; }}
QPushButton#big:hover {{ border-color: #ff5c8a; background: #2a2330; }}
QPushButton {{ border: 1px solid #3a3a46; border-radius: 6px; padding: 5px 12px; background: #23232c; }}
QPushButton:hover {{ border-color: #ff5c8a; }}
QPushButton:default {{ border-color: #ff5c8a; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 6px 6px; border-radius: 6px; }}
QListWidget::item:hover {{ background: rgba(255,255,255,0.06); }}
QListWidget::item:selected {{ background: rgba(255,92,138,0.25); color: #fff; }}
QListWidget#recent::item {{ padding: 7px 10px; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.18); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #ff5c8a; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #fff; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
QMenu {{ background: #1f1f27; border: 1px solid #33333d; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: #ff5c8a; color: #fff; }}
QMenu::item:disabled {{ color: #666; }}
QMenu::separator {{ height: 1px; background: #33333d; margin: 4px 8px; }}
QMenu::indicator {{ width: 10px; height: 10px; left: 9px; border-radius: 5px; }}
QMenu::indicator:checked {{ background: #ff5c8a; border: 1px solid #ffd0de; }}
QMenu::indicator:unchecked {{ background: transparent; }}
QDialog {{ background: #1b1b22; }}
QTabWidget::pane {{ border: 1px solid #2c2c36; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: #23232c; padding: 7px 14px; border: 1px solid #2c2c36; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #2e2e39; color: #fff; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QFontComboBox {{ background: #23232c; border: 1px solid #3a3a46; border-radius: 5px; padding: 4px 6px; selection-background-color: #ff5c8a; }}
QComboBox QAbstractItemView {{ background: #23232c; selection-background-color: #ff5c8a; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #55556a; border-radius: 4px; background: #23232c; }}
QCheckBox::indicator:hover {{ border-color: #ff5c8a; }}
QCheckBox::indicator:checked {{ background: #ff5c8a; border-color: #ff5c8a; image: url(CHECKMARK); }}
QToolTip {{ background: #111; color: #fff; border: 1px solid #444; padding: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 9px; }}
QScrollBar::handle:vertical {{ background: #3a3a46; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QProgressBar {{ border: 1px solid #3a3a46; border-radius: 5px; background: #23232c; text-align: center; }}
QProgressBar::chunk {{ background: #ff5c8a; border-radius: 4px; }}
"""


def build_style():
    """체크 표시 그림을 임시 폴더에 만들어 스타일시트에 연결."""
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "cfp_check.png").replace("\\", "/")
    try:
        pm = QPixmap(30, 30)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("white"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(7, 15.5), QPointF(12.5, 21), QPointF(23, 9)])
        p.end()
        pm.save(path, "PNG")
    except Exception:
        return STYLE.replace("image: url(CHECKMARK);", "")
    return STYLE.replace("CHECKMARK", path)
