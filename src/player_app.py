"""코덱무관플레이어 메인 창 — mpv(libmpv) 엔진 + Qt 화면."""
import os
import random
import re
import subprocess
import sys
import tempfile
import time

from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QUrl, QSize, QRect
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication, QDesktopServices, QImage, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QSplitter,
                               QMenu, QFileDialog, QInputDialog, QMessageBox, QProgressDialog,
                               QApplication, QListWidgetItem, QTabWidget)

import mpv

from dialogs import (SettingsDialog, MediaInfoDialog, SliderPanel, ShortcutsDialog, EQ_BANDS, EQ_PRESETS,
                     about_text)
from keys import NORMALIZED, normalize, qt_event_to_mpv, mpv_binding_names
import shutil

from store import default_shot_dir, data_dir
from thumbs import Thumbnailer
from updater import Updater, run_installer, ToolFetcher, update_ytdlp_async
from version import APP_NAME, VERSION
from widgets import (ControlBar, PlaylistPanel, WelcomePage, ThumbPopup, make_icon, fmt_time, build_style,
                     ACCENT, FG, DIM)

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m2ts", ".mts",
              ".mpg", ".mpeg", ".vob", ".ogv", ".3gp", ".3g2", ".rm", ".rmvb", ".asf", ".divx", ".f4v",
              ".y4m", ".dv", ".mxf", ".hevc", ".h264", ".h265", ".264", ".265", ".av1", ".ivf", ".gif"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".ape", ".alac", ".ac3",
              ".dts", ".mka", ".tta", ".wv", ".aiff", ".aif", ".mid", ".midi"}
SUB_EXTS = {".srt", ".smi", ".sami", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup", ".lrc", ".txt"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS | {".m3u", ".m3u8", ".pls", ".cue", ".iso"}
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
AUDIO_PRESETS = [
    ("off", "끄기", None),
    ("normalize", "음량 평준화 (작은 소리↑ 큰 소리↓)", "dynaudnorm=f=200:g=11:p=0.9"),
    ("night", "야간 모드 (폭발음 줄이고 대사 키우기)", "acompressor=threshold=0.05:ratio=8:attack=10:release=300:makeup=4"),
    ("voice", "목소리 강조", "highpass=f=90,equalizer=f=2500:width_type=o:width=2:g=6,equalizer=f=200:width_type=o:width=1:g=-3"),
    ("bass", "저음 강화", "bass=g=8:f=110"),
    ("surround", "가상 서라운드 (헤드폰)", "extrastereo=m=2.0"),
]


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def is_url(p):
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", p or ""))


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def tools_dir():
    d = os.path.join(data_dir(), "tools")
    os.makedirs(d, exist_ok=True)
    return d


def find_deno():
    for d in (app_dir(), getattr(sys, "_MEIPASS", app_dir()), tools_dir()):
        for n in ("deno.exe", "deno"):
            if os.path.isfile(os.path.join(d, n)):
                return os.path.join(d, n)
    return shutil.which("deno")


def find_tool(name):
    cands = [os.path.join(app_dir(), name), os.path.join(getattr(sys, "_MEIPASS", app_dir()), name)]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


class VideoHost(QWidget):
    """mpv가 직접 그리는 네이티브 창."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoHost")
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(160, 90)


class MainWindow(QMainWindow):
    sig_key = Signal(str)
    sig_loaded = Signal()
    sig_end = Signal(str, str)

    def __init__(self, store, initial_args=None, after_update=False):
        super().__init__()
        self.store = store
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon("app", size=256))
        self.setAcceptDrops(True)
        self.setStyleSheet(build_style())
        self.setMinimumSize(480, 300)

        # 상태
        self.items = []
        self.index = -1
        self.played_shuffle = set()
        self.current = None
        self.show_remaining = False
        self.eof_handled = False
        self.pending_fit = False
        self.loaded = False
        self.last_save = 0
        self.last_disk_save = time.time()
        self.end_action = "none"
        self.sleep_deadline = None
        self.mini = False
        self.mini_restore = None
        self.on_top = False
        self.fs_bar_floating = False
        self.last_mouse = QPoint()
        self.last_activity = time.time()
        self.vflip = False
        self.hflip = False
        self.adjust = [0, 0, 0, 0, 0]
        self.adjust_dlg = None
        self.eq_dlg = None
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._single_click)
        self.ask_resume_pos = None

        # ---- 화면 구성
        central = QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(1)
        self.split.setChildrenCollapsible(False)
        root.addWidget(self.split, 1)
        left = QWidget()
        self.left_layout = QVBoxLayout(left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.welcome = WelcomePage()
        self.video = VideoHost()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.video)
        self.left_layout.addWidget(self.stack, 1)
        self.bar = ControlBar()
        self.left_layout.addWidget(self.bar)
        self.split.addWidget(left)
        self.plist = PlaylistPanel()
        self.split.addWidget(self.plist)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.plist.setVisible(bool(store["playlist_visible"]))
        self.thumb_popup = ThumbPopup()
        self.thumbs = Thumbnailer()
        self.thumbs.ready.connect(self._thumb_ready)
        self.hover_sec = None
        self.hover_gpos = QPoint()

        # ---- mpv
        self.video.winId()
        self._init_mpv()

        # ---- 연결
        b = self.bar
        b.b_play.clicked.connect(self.toggle_pause)
        b.b_prev.clicked.connect(self.prev)
        b.b_next.clicked.connect(lambda: self.next(manual=True))
        b.b_stop.clicked.connect(self.stop)
        b.b_vol.clicked.connect(self.toggle_mute)
        b.vol.valueChanged.connect(self._vol_slider)
        b.time.clicked.connect(self._toggle_time_mode)
        b.b_full.clicked.connect(self.toggle_fullscreen)
        b.b_list.clicked.connect(self.toggle_playlist)
        b.b_shot.clicked.connect(lambda: self.screenshot())
        b.b_menu.clicked.connect(lambda: self.show_menu(b.b_menu.mapToGlobal(QPoint(0, 0)), above=b.b_menu))
        b.b_speed.clicked.connect(lambda: self._popup(self._speed_menu(), b.b_speed))
        b.b_ab.clicked.connect(self.ab_cycle)
        b.b_repeat.clicked.connect(self.cycle_repeat)
        b.b_cc.clicked.connect(self.toggle_sub)
        b.b_cc.setContextMenuPolicy(Qt.CustomContextMenu)
        b.b_cc.customContextMenuRequested.connect(lambda _: self._popup(self._sub_menu(), b.b_cc))
        b.seek.seek_requested.connect(self._seek_bar)
        b.seek.hover_changed.connect(self._seek_hover)
        self.welcome.open_file.connect(self.open_file_dialog)
        self.welcome.open_folder.connect(self.open_folder_dialog)
        self.welcome.open_url.connect(self.open_url_dialog)
        self.welcome.open_recent.connect(lambda p: self.open_paths([p]))
        self.welcome.setContextMenuPolicy(Qt.CustomContextMenu)
        self.welcome.customContextMenuRequested.connect(lambda pos: self.show_menu(self.welcome.mapToGlobal(pos)))
        pl = self.plist
        pl.list.itemActivated.connect(lambda it: self.play_index(pl.list.row(it)))
        pl.list.itemDoubleClicked.connect(lambda it: self.play_index(pl.list.row(it)))
        pl.list.model().rowsMoved.connect(self._playlist_reordered)
        pl.list.setContextMenuPolicy(Qt.CustomContextMenu)
        pl.list.customContextMenuRequested.connect(self._playlist_ctx)
        pl.b_add.clicked.connect(lambda: self.open_file_dialog(append=True))
        pl.b_more.clicked.connect(lambda: self._popup(self._playlist_menu(), pl.b_more))
        self.sig_key.connect(self._on_mpv_key)
        self.sig_loaded.connect(self._on_file_loaded)
        self.sig_end.connect(self._on_end_file)

        # 타이머
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(100)

        # 업데이트
        self.updater = Updater()
        self.updater.found.connect(self._update_found)
        self.updater.none.connect(lambda m: QMessageBox.information(self, "업데이트", m))
        self.updater.failed.connect(self._update_failed)
        self.updater.progress.connect(self._update_progress)
        self.updater.downloaded.connect(self._update_ready)
        self.update_dlg = None
        if store["check_updates"]:
            QTimer.singleShot(3500, lambda: self.updater.check(False))

        # 창 위치
        geo = store["geometry"]
        if store["remember_window"] and geo:
            try:
                x, y, w, h = geo
                scr = QGuiApplication.screenAt(QPoint(x + 40, y + 40))
                if scr:
                    self.setGeometry(x, y, w, h)
                else:
                    self.resize(w, h)
            except Exception:
                self.resize(1100, 680)
        else:
            self.resize(1100, 680)
        if store["playlist_visible"]:
            self.split.setSizes([self.width() - store["playlist_width"], store["playlist_width"]])
        self._refresh_welcome()
        self._refresh_repeat_icon()

        if after_update and store.session.get("path") and not initial_args:
            sess = store.session
            if time.time() - sess.get("t", 0) < 3600:
                initial_args = [sess["path"]]
        if initial_args:
            QTimer.singleShot(0, lambda: self.open_paths(initial_args))
        if after_update:
            QTimer.singleShot(1500, lambda: self.osd(f"업데이트 완료! 버전 {VERSION}", 4000))

    # ================================================================ mpv
    def _init_mpv(self):
        s = self.store
        extra = {}
        if os.environ.get("CFP_VO"):
            extra["vo"] = os.environ["CFP_VO"]
        self.m = mpv.MPV(wid=str(int(self.video.winId())), input_default_bindings=False, **extra,
                         input_vo_keyboard=True, osc=False, idle="yes", keep_open="yes",
                         log_handler=self._mpv_log, loglevel="warn")
        opts = {
            "hwdec": "auto-safe" if s["hwdec"] else "no",
            "volume-max": int(s["volume_max"]),
            "volume": min(int(s["volume"]), int(s["volume_max"])),
            "mute": bool(s["muted"]),
            "cursor-autohide": 1200,
            "sub-auto": "fuzzy" if s["sub_auto"] else "no",
            "sub-file-paths": "sub;subs;subtitles;자막",
            "slang": s["sub_lang"],
            "alang": s["audio_lang"],
            "osd-font": "Malgun Gothic",
            "osd-font-size": 34,
            "osd-border-size": 2,
            "osd-bar-h": 2.5,
            "osd-duration": 1400,
            "screenshot-format": s["shot_format"],
            "screenshot-png-compression": 4,
            "screenshot-jpeg-quality": 95,
            "demuxer-max-bytes": "200MiB",
            "demuxer-max-back-bytes": "60MiB",
            "cache": "auto",
            "drag-and-drop": "no",
            "stop-screensaver": "yes",
            "ytdl": "yes",
            "ytdl-format": self._ytdl_format(),
            "ytdl-raw-options": "no-playlist=",
            "audio-file-auto": "fuzzy",
            "audio-pitch-correction": "yes",
            "hr-seek": "default",
            "video-sync": "audio",
            "background-color": "#000000",
            "input-ar-delay": 300,
            "input-ar-rate": 25,
            "keepaspect-window": "no",
            "sub-font-provider": "auto",
            "embeddedfonts": "yes",
            "deinterlace": "yes" if s["deinterlace"] == "yes" else "no",
        }
        ytdl = find_tool("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
        if ytdl:
            opts["script-opts"] = f"ytdl_hook-ytdl_path={ytdl}"
            update_ytdlp_async(ytdl, os.path.join(data_dir(), "ytdlp_update.stamp"))
        # yt-dlp 가 Deno(유튜브 JS 해석용)를 찾을 수 있게
        os.environ["PATH"] = tools_dir() + os.pathsep + os.environ.get("PATH", "")
        for k, v in opts.items():
            self._set(k, v)
        if s["deinterlace"] == "auto":
            # 구버전 mpv는 auto 가 없음
            if not self._set("deinterlace", "auto"):
                self._set("deinterlace", "no")
        self.apply_sub_style()
        self.apply_af()
        # 키·마우스 (mpv 창에 포커스가 있을 때)
        for name, act in mpv_binding_names().items():
            try:
                self.m.register_key_binding(name, lambda st, nm, *a, act=act: self._mpv_key_cb(st, act))
            except Exception:
                pass
        for name in ("MBTN_LEFT", "MBTN_LEFT_DBL", "MBTN_RIGHT", "MBTN_MID", "WHEEL_UP", "WHEEL_DOWN",
                     "Ctrl+WHEEL_UP", "Ctrl+WHEEL_DOWN", "Shift+WHEEL_UP", "Shift+WHEEL_DOWN",
                     "MBTN_BACK", "MBTN_FORWARD", "WHEEL_LEFT", "WHEEL_RIGHT"):
            try:
                self.m.register_key_binding(name, lambda st, nm, *a, name=name: self._mpv_key_cb(st, "@" + name))
            except Exception:
                pass

        @self.m.event_callback("file-loaded")
        def _fl(e):
            self.sig_loaded.emit()

        @self.m.event_callback("end-file")
        def _ef(e):
            try:
                d = e.as_dict()
            except Exception:
                d = {}
            r = d.get("reason", b"")
            fe = d.get("file_error", b"")
            r = r.decode() if isinstance(r, bytes) else str(r)
            fe = fe.decode() if isinstance(fe, bytes) else str(fe or "")
            self.sig_end.emit(r, fe)

    def _set(self, k, v):
        try:
            self.m._set_property(k, v)
            return True
        except Exception:
            return False

    def _get(self, k, default=None):
        try:
            v = self.m._get_property(k, decoder=mpv.lazy_decoder)
            return default if v is None else v
        except Exception:
            return default

    def _mpv_log(self, level, prefix, text):
        pass

    def _mpv_key_cb(self, state, act):
        st = state[0] if state else "d"
        if act.startswith("@"):
            if st in ("d", "p"):
                self.sig_key.emit(act)
        elif st in ("d", "p", "r"):
            self.sig_key.emit(act)

    def _ytdl_format(self):
        q = self.store["ytdl_quality"]
        if q == "best":
            return "bestvideo+bestaudio/best"
        return f"bestvideo[height<=?{q}]+bestaudio/best[height<=?{q}]/best"

    def osd(self, text, ms=1500):
        try:
            self.m.command("show-text", text, str(ms))
        except Exception:
            pass

    # ================================================================ 입력
    def keyPressEvent(self, e):
        name = qt_event_to_mpv(e)
        if name:
            act = NORMALIZED.get(normalize(name))
            if act:
                self.do_action(act, name)
                e.accept()
                return
        super().keyPressEvent(e)

    def _on_mpv_key(self, act):
        if act.startswith("@"):
            self._mouse(act[1:])
        else:
            self.do_action(act, None)

    def _mouse(self, name):
        self.last_activity = time.time()
        wheel_vol = self.store["wheel_action"] == "volume"
        if name == "MBTN_LEFT":
            if self.mini:
                wh = self.windowHandle()
                if wh:
                    wh.startSystemMove()
                return
            if self.store["click_to_pause"]:
                self.click_timer.start(QApplication.doubleClickInterval())
        elif name == "MBTN_LEFT_DBL":
            self.click_timer.stop()
            if self.mini:
                self.toggle_mini()
            else:
                self.toggle_fullscreen()
        elif name == "MBTN_RIGHT":
            self.show_menu(QCursor.pos())
        elif name == "MBTN_MID":
            self.toggle_mute()
        elif name in ("WHEEL_UP", "WHEEL_DOWN"):
            up = name == "WHEEL_UP"
            if wheel_vol:
                self.change_volume(5 if up else -5)
            else:
                self.seek_rel(self.store["seek_small"] if up else -self.store["seek_small"])
        elif name in ("Shift+WHEEL_UP", "Shift+WHEEL_DOWN"):
            up = name.endswith("UP")
            if wheel_vol:
                self.seek_rel(self.store["seek_small"] if up else -self.store["seek_small"])
            else:
                self.change_volume(5 if up else -5)
        elif name in ("Ctrl+WHEEL_UP", "Ctrl+WHEEL_DOWN"):
            self.zoom(0.1 if name.endswith("UP") else -0.1)
        elif name == "MBTN_BACK":
            self.seek_rel(-10)
        elif name == "MBTN_FORWARD":
            self.seek_rel(10)

    def _single_click(self):
        if self.loaded:
            self.toggle_pause()

    def wheelEvent(self, e):
        # 시작 화면/컨트롤바 위에서도 휠로 볼륨
        dy = e.angleDelta().y()
        if dy:
            if e.modifiers() & Qt.ControlModifier:
                self.zoom(0.1 if dy > 0 else -0.1)
            else:
                self.change_volume(5 if dy > 0 else -5)

    def do_action(self, act, key=None):
        self.last_activity = time.time()
        s = self.store
        A = {
            "pause": self.toggle_pause, "fullscreen": self.toggle_fullscreen, "escape": self.escape,
            "quit": self.close, "seek_back": lambda: self.seek_rel(-s["seek_small"]),
            "seek_fwd": lambda: self.seek_rel(s["seek_small"]), "seek_back1": lambda: self.seek_rel(-1, exact=True),
            "seek_fwd1": lambda: self.seek_rel(1, exact=True), "seek_back_big": lambda: self.seek_rel(-s["seek_large"]),
            "seek_fwd_big": lambda: self.seek_rel(s["seek_large"]), "seek_back10": lambda: self.seek_rel(-10),
            "seek_fwd10": lambda: self.seek_rel(10), "frame_back": self.frame_back, "frame_step": self.frame_step,
            "seek_start": lambda: self.seek_abs(0), "chapter_prev": lambda: self.chapter(-1),
            "chapter_next": lambda: self.chapter(1), "prev": self.prev, "next": lambda: self.next(manual=True),
            "toggle_playlist": self.toggle_playlist, "vol_up": lambda: self.change_volume(5),
            "vol_down": lambda: self.change_volume(-5), "mute": self.toggle_mute, "cycle_audio": lambda: self.cycle_track("audio"),
            "audio_delay_minus": lambda: self.audio_delay(-0.1), "audio_delay_plus": lambda: self.audio_delay(0.1),
            "audio_delay_reset": lambda: self.audio_delay(None), "toggle_normalize": self.toggle_normalize,
            "speed_up": lambda: self.change_speed(0.1), "speed_down": lambda: self.change_speed(-0.1),
            "speed_reset": lambda: self.set_speed(1.0), "ab_a": self.ab_set_a, "ab_b": self.ab_set_b,
            "ab_clear": self.ab_clear, "cycle_sub": lambda: self.cycle_track("sub"), "toggle_sub": self.toggle_sub,
            "sub_delay_minus": lambda: self.sub_delay(-0.1), "sub_delay_plus": lambda: self.sub_delay(0.1),
            "sub_bigger": lambda: self.sub_scale(0.1), "sub_smaller": lambda: self.sub_scale(-0.1),
            "sub_up": lambda: self.sub_move(-2), "sub_down": lambda: self.sub_move(2),
            "screenshot": lambda: self.screenshot(), "screenshot_clip": self.screenshot_clipboard,
            "rotate": lambda: self.rotate(90), "zoom_reset": self.zoom_reset, "zoom_in": lambda: self.zoom(0.1),
            "zoom_out": lambda: self.zoom(-0.1), "on_top": lambda: self.set_on_top(not self.on_top, announce=True),
            "mini": self.toggle_mini, "stats": self.toggle_stats, "media_info": self.media_info,
            "size_50": lambda: self.window_scale(0.5), "size_100": lambda: self.window_scale(1.0),
            "size_150": lambda: self.window_scale(1.5), "size_200": lambda: self.window_scale(2.0),
            "bookmark": self.add_bookmark, "open_file": self.open_file_dialog, "open_url": self.open_url_dialog,
            "paste": self.paste, "settings": self.open_settings, "help": self.show_help,
        }
        if act == "seek_percent":
            k = (key or "0")[-1]
            if k.isdigit():
                self.seek_percent(int(k) * 10)
            return
        f = A.get(act)
        if f:
            f()

    # ================================================================ 열기 / 재생목록
    def open_file_dialog(self, append=False):
        exts = " ".join("*" + e for e in sorted(MEDIA_EXTS))
        start = os.path.dirname(self.current) if self.current and not is_url(self.current) else ""
        files, _ = QFileDialog.getOpenFileNames(self, "파일 열기", start,
                                                f"동영상/음악 ({exts});;자막 (*.srt *.smi *.ass *.ssa *.vtt *.sub);;모든 파일 (*.*)")
        if files:
            subs = [f for f in files if os.path.splitext(f)[1].lower() in SUB_EXTS]
            media = [f for f in files if f not in subs]
            if media:
                self.open_paths(media, append=append)
            for sfile in subs:
                self.load_sub(sfile)

    def open_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 열기")
        if d:
            self.open_paths([d])

    def open_url_dialog(self):
        clip = QGuiApplication.clipboard().text().strip()
        default = clip if is_url(clip) else ""
        url, ok = QInputDialog.getText(self, "주소(URL) 열기",
                                       "유튜브·트위치·치지직 등 영상 주소나 직접 링크(m3u8 등)를 넣어 주세요:", text=default)
        if ok and url.strip():
            if not find_tool("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp") and "youtu" in url:
                self.osd("yt-dlp 가 없어 유튜브 주소는 재생이 안 될 수 있어요", 3000)
            self.open_paths([url.strip()])

    def paste(self):
        md = QGuiApplication.clipboard().mimeData()
        if md and md.hasUrls():
            paths = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in md.urls()]
            self.open_paths(paths)
            return
        t = QGuiApplication.clipboard().text().strip().strip('"')
        if t and (is_url(t) or os.path.exists(t)):
            self.open_paths([t])
        else:
            self.osd("클립보드에 열 수 있는 주소나 파일이 없어요")

    def _expand(self, paths):
        out = []
        for p in paths:
            if not p:
                continue
            p = p.strip().strip('"')
            if is_url(p):
                out.append(p)
            elif os.path.isdir(p):
                found = []
                for rootd, _, files in os.walk(p):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in (VIDEO_EXTS | AUDIO_EXTS):
                            found.append(os.path.join(rootd, f))
                found.sort(key=natural_key)
                out.extend(found)
            elif os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in (".m3u", ".m3u8") and os.path.getsize(p) < 2_000_000:
                    out.extend(self._read_m3u(p) or [p])
                else:
                    out.append(os.path.abspath(p))
        return out

    def _read_m3u(self, path):
        base = os.path.dirname(path)
        res = []
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                lines = f.read().splitlines()
        except Exception:
            return None
        if any(l.startswith("#EXT-X-") for l in lines[:30]):
            return None  # HLS 스트림 → mpv 가 직접 처리
        for l in lines:
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            if not is_url(l) and not os.path.isabs(l):
                l = os.path.normpath(os.path.join(base, l))
            res.append(l)
        return res

    def open_paths(self, paths, append=False):
        subs = [p for p in paths if os.path.splitext(p)[1].lower() in SUB_EXTS and os.path.isfile(p)]
        media = [p for p in paths if p not in subs]
        if subs and not media and self.loaded:
            for sfile in subs:
                self.load_sub(sfile)
            return
        items = self._expand(media)
        if not items:
            if media:
                self.osd("열 수 있는 영상이 없어요")
            return
        if append and self.items:
            start = len(self.items)
            self.items.extend(items)
            self._refresh_playlist()
            self.osd(f"재생목록에 {len(items)}개 추가")
            if self.index < 0:
                self.play_index(start)
            return
        single = len(items) == 1 and len(media) == 1 and os.path.isfile(media[0]) and not is_url(items[0])
        if single and self.store["auto_folder_playlist"]:
            target = items[0]
            folder = os.path.dirname(target)
            try:
                sib = [os.path.join(folder, f) for f in os.listdir(folder)
                       if os.path.splitext(f)[1].lower() in VIDEO_EXTS and os.path.isfile(os.path.join(folder, f))]
            except Exception:
                sib = []
            if os.path.splitext(target)[1].lower() in VIDEO_EXTS and len(sib) > 1:
                sib.sort(key=natural_key)
                norm = [os.path.normcase(x) for x in sib]
                if os.path.normcase(target) in norm:
                    self.items = sib
                    self.played_shuffle = set()
                    self._refresh_playlist()
                    self.play_index(norm.index(os.path.normcase(target)))
                    for sfile in subs:
                        QTimer.singleShot(800, lambda sf=sfile: self.load_sub(sf))
                    return
        self.items = items
        self.played_shuffle = set()
        self._refresh_playlist()
        self.play_index(0)
        for sfile in subs:
            QTimer.singleShot(800, lambda sf=sfile: self.load_sub(sf))

    def play_index(self, i):
        if not (0 <= i < len(self.items)):
            return
        p = self.items[i]
        if (sys.platform == "win32" and is_url(p) and re.search(r"youtu\.?be|youtube\.com", p)
                and not getattr(self, "deno_asked", False) and not find_deno()):
            self.deno_asked = True
            r = QMessageBox.question(self, "유튜브 재생 준비",
                                     "유튜브 영상을 제대로 재생하려면 보조 프로그램(Deno, 약 40MB)이 한 번 필요해요.\n"
                                     "지금 받아 둘까요? (다음부터는 바로 재생돼요)",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                self._fetch_deno(lambda: self.play_index(i))
                return
        self._save_position()
        self.index = i
        self.played_shuffle.add(i)
        path = self.items[i]
        self.current = path
        self.loaded = False
        self.eof_handled = False
        self.ask_resume_pos = None
        pos = None if is_url(path) else self.store.get_resume(path)
        mode = self.store["resume_mode"]
        if pos and mode == "auto":
            self._set("start", f"{pos:.2f}")
        else:
            self._set("start", "none")
            if pos and mode == "ask":
                self.ask_resume_pos = pos
        self._set("ab-loop-a", "no")
        self._set("ab-loop-b", "no")
        self._set("loop-file", "inf" if self.store["repeat"] == "one" else "no")
        try:
            self.m.command("loadfile", path, "replace")
        except Exception as ex:
            self.osd(f"열기 실패: {ex}")
            return
        self._set("pause", False)
        self.stack.setCurrentWidget(self.video)
        self.setWindowTitle(f"{os.path.basename(path) if not is_url(path) else path} - {APP_NAME}")
        self.bar.title.setText(os.path.basename(path) if not is_url(path) else path)
        self._highlight_playlist()
        self.store.add_recent(path)
        if self.store["fit_window_on_open"]:
            self.pending_fit = True

    def _fetch_deno(self, then):
        dlg = QProgressDialog("유튜브 재생 준비 중… (Deno 받는 중)", None, 0, 100, self)
        dlg.setWindowTitle("유튜브 재생 준비")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        self.fetcher = ToolFetcher()

        def prog(got, total):
            if total:
                dlg.setValue(int(got * 100 / total))

        def ok(path):
            dlg.close()
            self.osd("유튜브 재생 준비 완료!", 2000)
            then()

        def fail(msg):
            dlg.close()
            self.osd(f"Deno 받기 실패 — 그냥 재생해 볼게요 ({msg})", 3000)
            then()
        self.fetcher.progress.connect(prog)
        self.fetcher.done.connect(ok)
        self.fetcher.failed.connect(fail)
        self.fetcher.fetch_zip_member(
            "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
            "deno.exe", tools_dir())

    def next(self, manual=False):
        if not self.items:
            return
        rep = self.store["repeat"]
        if self.store["shuffle"] and len(self.items) > 1:
            left = [i for i in range(len(self.items)) if i not in self.played_shuffle]
            if not left:
                if rep == "all" or manual:
                    self.played_shuffle = set()
                    left = [i for i in range(len(self.items)) if i != self.index]
                else:
                    return self._playlist_finished()
            return self.play_index(random.choice(left))
        n = self.index + 1
        if n >= len(self.items):
            if rep == "all" or (manual and len(self.items) > 1):
                n = 0
            else:
                if manual:
                    self.osd("마지막 파일이에요")
                    return
                return self._playlist_finished()
        self.play_index(n)

    def prev(self):
        if not self.items:
            return
        pos = self._get("time-pos", 0) or 0
        if pos > 5 and not self.store["shuffle"]:
            self.seek_abs(0)
            return
        n = self.index - 1
        if n < 0:
            n = len(self.items) - 1 if self.store["repeat"] == "all" else 0
        self.play_index(n)

    def stop(self):
        self._save_position()
        try:
            self.m.command("stop")
        except Exception:
            pass
        self.loaded = False
        self.current = None
        self.stack.setCurrentWidget(self.welcome)
        self._refresh_welcome()
        self.setWindowTitle(APP_NAME)
        self.bar.title.setText("")
        self.bar.seek.set_state(0, 0)
        self.bar.seek.chapters = []
        self.bar.seek.bookmarks = []
        self.bar.seek.ab = (None, None)
        if self.fs_bar_floating or self.isFullScreen():
            self.toggle_fullscreen()

    def _playlist_finished(self):
        act = self.end_action
        if act == "quit":
            QTimer.singleShot(500, self.close)
        elif act in ("sleep", "shutdown"):
            self._power(act)
        self.osd("재생목록 끝", 2000)

    def _power(self, act):
        self.end_action = "none"
        if sys.platform != "win32":
            self.osd(f"(Windows 전용) {act}")
            return
        if act == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "60", "/c", "코덱무관플레이어: 재생이 끝나 60초 뒤 컴퓨터를 끕니다. 취소하려면 shutdown /a"],
                             creationflags=0x08000000)
            r = QMessageBox.question(self, "컴퓨터 종료", "60초 뒤 컴퓨터가 꺼져요.\n취소할까요?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r == QMessageBox.Yes:
                subprocess.Popen(["shutdown", "/a"], creationflags=0x08000000)
        elif act == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=0x08000000)

    def _refresh_playlist(self):
        lw = self.plist.list
        lw.blockSignals(True)
        lw.clear()
        for i, p in enumerate(self.items):
            it = QListWidgetItem(f"{i + 1}. {os.path.basename(p) if not is_url(p) else p}")
            it.setToolTip(p)
            it.setData(Qt.UserRole, p)
            lw.addItem(it)
        lw.blockSignals(False)
        self.plist.count.setText(f"{len(self.items)}개")
        self._highlight_playlist()

    def _highlight_playlist(self):
        lw = self.plist.list
        for i in range(lw.count()):
            it = lw.item(i)
            f = it.font()
            f.setBold(i == self.index)
            it.setFont(f)
            it.setForeground(ACCENT if i == self.index else FG)
        if 0 <= self.index < lw.count():
            lw.scrollToItem(lw.item(self.index))

    def _playlist_reordered(self, *a):
        lw = self.plist.list
        new = [lw.item(i).data(Qt.UserRole) for i in range(lw.count())]
        cur = self.items[self.index] if 0 <= self.index < len(self.items) else None
        self.items = new
        self.index = new.index(cur) if cur in new else -1
        QTimer.singleShot(0, self._refresh_playlist)

    def _playlist_ctx(self, pos):
        lw = self.plist.list
        it = lw.itemAt(pos)
        m = QMenu(self)
        if it:
            row = lw.row(it)
            m.addAction("재생", lambda: self.play_index(row))
            m.addAction("목록에서 빼기 (Del)", self.remove_selected)
            p = it.data(Qt.UserRole)
            if not is_url(p):
                m.addAction("탐색기에서 보기", lambda: self.reveal(p))
            m.addSeparator()
        for a in self._playlist_menu().actions():
            m.addAction(a)
        m.exec(lw.mapToGlobal(pos))

    def _playlist_menu(self):
        m = QMenu(self)
        m.addAction("파일 추가…", lambda: self.open_file_dialog(append=True))
        m.addAction("폴더 추가…", self._add_folder)
        m.addAction("선택 항목 빼기", self.remove_selected)
        m.addAction("이름순 정렬", self._sort_playlist)
        m.addAction("섞기", self._shuffle_list)
        m.addAction("목록 비우기", self._clear_playlist)
        m.addSeparator()
        m.addAction("재생목록 저장 (m3u)…", self._save_m3u)
        m.addAction("재생목록 불러오기…", self._load_m3u)
        return m

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 추가")
        if d:
            self.open_paths([d], append=True)

    def remove_selected(self):
        rows = sorted({self.plist.list.row(i) for i in self.plist.list.selectedItems()}, reverse=True)
        cur = self.items[self.index] if 0 <= self.index < len(self.items) else None
        for r in rows:
            self.items.pop(r)
        self.index = self.items.index(cur) if cur in self.items else -1
        self._refresh_playlist()

    def _sort_playlist(self):
        cur = self.items[self.index] if 0 <= self.index < len(self.items) else None
        self.items.sort(key=lambda p: natural_key(os.path.basename(p)))
        self.index = self.items.index(cur) if cur in self.items else -1
        self._refresh_playlist()

    def _shuffle_list(self):
        cur = self.items[self.index] if 0 <= self.index < len(self.items) else None
        random.shuffle(self.items)
        self.index = self.items.index(cur) if cur in self.items else -1
        self._refresh_playlist()

    def _clear_playlist(self):
        self.items = [self.current] if self.current else []
        self.index = 0 if self.current else -1
        self._refresh_playlist()

    def _save_m3u(self):
        if not self.items:
            return
        f, _ = QFileDialog.getSaveFileName(self, "재생목록 저장", "재생목록.m3u8", "재생목록 (*.m3u8 *.m3u)")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n" + "\n".join(self.items) + "\n")
            self.osd("재생목록 저장됨")

    def _load_m3u(self):
        f, _ = QFileDialog.getOpenFileName(self, "재생목록 불러오기", "", "재생목록 (*.m3u8 *.m3u)")
        if f:
            self.open_paths([f])

    def reveal(self, path):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def toggle_playlist(self):
        if self.isFullScreen() or self.mini:
            return
        vis = not self.plist.isVisible()
        if vis:
            w = self.store["playlist_width"] or 280
            self.plist.setVisible(True)
            self.split.setSizes([max(200, self.split.width() - w), w])
        else:
            self.store["playlist_width"] = self.plist.width()
            self.plist.setVisible(False)
        self.store["playlist_visible"] = vis

    # ================================================================ 이벤트
    def _on_file_loaded(self):
        self.loaded = True
        self.eof_handled = False
        self._set("start", "none")
        if not self.ask_resume_pos:
            self._set("pause", False)
        title = self._get("media-title", "") or os.path.basename(self.current or "")
        if self.current and is_url(self.current):
            self.setWindowTitle(f"{title} - {APP_NAME}")
            self.bar.title.setText(title)
        dur = self._get("duration", 0) or 0
        if self.store["thumbnails"] and self.current and not is_url(self.current):
            self.thumbs.set_file(self.current, dur)
        else:
            self.thumbs.set_file(None)
        self._refresh_markers()
        if self.ask_resume_pos:
            pos = self.ask_resume_pos
            self.ask_resume_pos = None
            self._set("pause", True)
            r = QMessageBox.question(self, "이어보기", f"지난번에 {fmt_time(pos)} 까지 봤어요.\n이어서 볼까요?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                self.seek_abs(pos)
            self._set("pause", False)
        elif self.current and not is_url(self.current) and self.store.get_resume(self.current) \
                and self.store["resume_mode"] == "auto":
            self.osd(f"이어보기 {fmt_time(self.store.get_resume(self.current))}  ·  처음부터: Home", 2500)
        # 볼륨 등 UI
        self.bar.vol.setMaximum(int(self.store["volume_max"]))
        self._apply_video_state()
        if self.store["always_on_top"] == "playing":
            self.set_on_top(True)

    def _on_end_file(self, reason, err):
        if reason == "error":
            name = os.path.basename(self.current or "") if not is_url(self.current or "") else (self.current or "")
            self.osd(f"재생할 수 없는 파일이에요: {name} ({err})", 3500)
            self.loaded = False
            if self.items and self.index < len(self.items) - 1 and self.store["autoplay_next"]:
                QTimer.singleShot(1200, lambda: self.next())

    def _handle_eof(self):
        self.eof_handled = True
        if self.current and not is_url(self.current):
            self.store.positions.pop(self.current, None)
        if self.store["repeat"] == "one":
            return
        if self.store["autoplay_next"] or self.store["repeat"] == "all":
            if self.index < len(self.items) - 1 or self.store["repeat"] == "all" or self.store["shuffle"]:
                QTimer.singleShot(300, lambda: self.next())
                return
        self._playlist_finished()

    def _poll(self):
        b = self.bar
        pause = bool(self._get("pause", False))
        pos = self._get("time-pos", None)
        dur = self._get("duration", None)
        idle = bool(self._get("idle-active", True))
        b.b_play.set_kind("play" if (pause or idle) else "pause")
        vol = self._get("volume", 0) or 0
        mute = bool(self._get("mute", False))
        if not b.vol.isSliderDown() and int(vol) != b.vol.value():
            b.vol.blockSignals(True)
            b.vol.setValue(int(vol))
            b.vol.blockSignals(False)
        b.vol_label.setText("음소거" if mute else f"{int(vol)}%")
        b.b_vol.set_kind("mute" if mute or vol == 0 else ("vol_low" if vol < 50 else "vol"))
        spd = self._get("speed", 1.0) or 1.0
        b.b_speed.setText(f"{spd:.2f}".rstrip("0").rstrip(".") + "x" if abs(spd - 1) > 1e-3 else "1.0x")
        self._set_chip(b.b_speed, abs(spd - 1) > 1e-3)
        a = self._get("ab-loop-a", "no")
        bb = self._get("ab-loop-b", "no")
        a = a if isinstance(a, (int, float)) else None
        bb = bb if isinstance(bb, (int, float)) else None
        b.seek.ab = (a, bb)
        b.b_ab.setText("A-B" if a is None else ("A-" if bb is None else "A-B ↻"))
        self._set_chip(b.b_ab, a is not None)
        subvis = bool(self._get("sub-visibility", True))
        has_sub = self._get("sid", False) not in (False, "no", None)
        b.b_cc.set_kind("cc", ACCENT if (subvis and has_sub) else (FG if subvis else DIM))
        cache_end = None
        if self.current and is_url(self.current):
            ct = self._get("demuxer-cache-time", None)
            if isinstance(ct, (int, float)):
                cache_end = ct
        b.seek.set_state(pos or 0, dur or 0, cache_end)
        if dur:
            if self.show_remaining and pos is not None:
                t = f"-{fmt_time(dur - pos, dur >= 3600)} / {fmt_time(dur)}"
            else:
                t = f"{fmt_time(pos, dur >= 3600)} / {fmt_time(dur)}"
        else:
            t = f"{fmt_time(pos)}" if pos else "00:00 / 00:00"
        if b.time.text() != t:
            b.time.setText(t)
        # 끝 감지 (keep-open)
        if self.loaded and not self.eof_handled and self._get("eof-reached", False):
            self._handle_eof()
        # 창 맞춤 (영상 크기를 알게 된 뒤)
        if self.pending_fit and self.loaded:
            dw = self._get("dwidth", None)
            if dw:
                self.pending_fit = False
                if not (self.isFullScreen() or self.isMaximized() or self.mini):
                    self.window_scale(None)
        # 이어보기 위치 저장
        now = time.time()
        if self.loaded and now - self.last_save > 5:
            self.last_save = now
            self._save_position(pos, dur)
            if now - self.last_disk_save > 30:
                self.last_disk_save = now
                self.store.save()
        # 취침 타이머
        if self.sleep_deadline and now >= self.sleep_deadline:
            self.sleep_deadline = None
            self._set("pause", True)
            self.osd("취침 타이머: 일시정지했어요", 4000)
            if self.end_action != "none":
                self._power(self.end_action) if self.end_action in ("sleep", "shutdown") else self.close()
        # 항상 위 (재생 중일 때만)
        if self.store["always_on_top"] == "playing" and not self.mini:
            want = self.loaded and not pause
            if want != self.on_top:
                self.set_on_top(want)
        # 전체 화면 컨트롤바 자동 숨김
        cp = QCursor.pos()
        if cp != self.last_mouse:
            self.last_mouse = cp
            self.last_activity = now
        if self.fs_bar_floating:
            over_bar = self.bar.geometry().contains(cp)
            if now - self.last_activity < 2.2 or over_bar or pause:
                if not self.bar.isVisible():
                    self._place_fs_bar()
                    self.bar.show()
                    self._sub_margin(True)
            elif self.bar.isVisible() and not b.seek.dragging:
                self.bar.hide()
                self.thumb_popup.hide()
                self._sub_margin(False)

    def _set_chip(self, w, active):
        val = "true" if active else "false"
        if w.property("active") != val:
            w.setProperty("active", val)
            w.style().unpolish(w)
            w.style().polish(w)

    def _save_position(self, pos=None, dur=None):
        if not self.current or is_url(self.current) or not self.loaded:
            return
        if pos is None:
            pos = self._get("time-pos", None)
        if dur is None:
            dur = self._get("duration", None)
        self.store.set_resume(self.current, pos, dur)
        self.store.session = {"path": self.current, "pos": pos, "t": int(time.time())}

    def _refresh_markers(self):
        sb = self.bar.seek
        chs = self._get("chapter-list", []) or []
        sb.chapters = [(c.get("time", 0), c.get("title", "") or f"챕터 {i + 1}") for i, c in enumerate(chs)]
        sb.bookmarks = [b[0] for b in self.store.get_bookmarks(self.current)] if self.current else []
        sb.update()

    def _refresh_welcome(self):
        self.welcome.set_recent(self.store.recent, self.store.positions)

    # ================================================================ 재생 조작
    def toggle_pause(self):
        if not self.loaded:
            if self.items and self.index >= 0 and not self.current:
                self.play_index(self.index)
            elif not self.items:
                self.open_file_dialog()
            return
        if self._get("eof-reached", False):
            self.seek_abs(0)
            self._set("pause", False)
            self.eof_handled = False
            return
        p = not self._get("pause", False)
        self._set("pause", p)
        self.osd("일시정지" if p else "재생", 700)

    def seek_rel(self, sec, exact=False):
        if not self.loaded:
            return
        try:
            self.m.command("seek", str(sec), "relative+exact" if exact else "relative")
            self.eof_handled = False
            self.osd(("▶▶ " if sec > 0 else "◀◀ ") + f"{abs(sec):g}초", 600)
        except Exception:
            pass

    def seek_abs(self, sec, exact=True):
        if not self.loaded:
            return
        try:
            self.m.command("seek", str(max(0, sec)), "absolute+exact" if exact else "absolute+keyframes")
            self.eof_handled = False
        except Exception:
            pass

    def seek_percent(self, pct):
        if not self.loaded:
            return
        try:
            self.m.command("seek", str(pct), "absolute-percent+exact")
            self.eof_handled = False
            self.osd(f"{pct}% 지점", 700)
        except Exception:
            pass

    def _seek_bar(self, sec, final):
        self.seek_abs(sec, exact=final)

    def frame_step(self):
        if self.loaded:
            self.m.command("frame-step")
            self.osd("다음 프레임", 500)

    def frame_back(self):
        if self.loaded:
            self.m.command("frame-back-step")
            self.osd("이전 프레임", 500)

    def chapter(self, d):
        chs = self._get("chapter-list", []) or []
        if not chs:
            self.osd("챕터가 없는 영상이에요")
            return
        try:
            self.m.command("add", "chapter", str(d))
            c = self._get("chapter", 0) or 0
            title = chs[c].get("title", "") if 0 <= c < len(chs) else ""
            self.osd(f"챕터 {c + 1}/{len(chs)}  {title}")
        except Exception:
            pass

    def goto_time_dialog(self):
        if not self.loaded:
            return
        t, ok = QInputDialog.getText(self, "시간으로 이동", "이동할 시간 (예: 1:23:45, 12:30, 90):",
                                     text=fmt_time(self._get("time-pos", 0)))
        if ok and t.strip():
            try:
                parts = [float(x) for x in t.strip().split(":")]
                sec = 0
                for p in parts:
                    sec = sec * 60 + p
                self.seek_abs(sec)
            except ValueError:
                self.osd("시간 형식이 이상해요")

    def change_volume(self, d):
        v = (self._get("volume", 0) or 0) + d
        v = max(0, min(int(self.store["volume_max"]), v))
        self._set("volume", v)
        if d > 0 and self._get("mute", False):
            self._set("mute", False)
        self.store["volume"] = v
        self.osd(f"볼륨 {int(v)}%", 700)

    def _vol_slider(self, v):
        self._set("volume", v)
        self.store["volume"] = v
        if v > 0 and self._get("mute", False):
            self._set("mute", False)

    def toggle_mute(self):
        m = not self._get("mute", False)
        self._set("mute", m)
        self.store["muted"] = m
        self.osd("음소거" if m else "소리 켬", 700)

    def set_speed(self, v):
        v = max(0.1, min(8.0, round(v, 2)))
        self._set("speed", v)
        self.osd(f"속도 {v:g}x", 800)

    def change_speed(self, d):
        self.set_speed((self._get("speed", 1.0) or 1.0) + d)

    def _toggle_time_mode(self):
        self.show_remaining = not self.show_remaining

    # A-B 반복
    def ab_set_a(self):
        if not self.loaded:
            return
        t = self._get("time-pos", 0)
        self._set("ab-loop-a", t)
        self._set("ab-loop-b", "no")
        self.osd(f"구간 반복 A = {fmt_time(t)}  (끝점은 ])")

    def ab_set_b(self):
        if not self.loaded:
            return
        a = self._get("ab-loop-a", "no")
        t = self._get("time-pos", 0)
        if not isinstance(a, (int, float)):
            self.osd("먼저 [ 로 시작점(A)을 찍어 주세요")
            return
        if t <= a:
            self.osd("끝점은 시작점보다 뒤여야 해요")
            return
        self._set("ab-loop-b", t)
        self.osd(f"구간 반복 {fmt_time(a)} ~ {fmt_time(t)}")

    def ab_clear(self):
        self._set("ab-loop-a", "no")
        self._set("ab-loop-b", "no")
        self.osd("구간 반복 해제")

    def ab_cycle(self):
        a = self._get("ab-loop-a", "no")
        b = self._get("ab-loop-b", "no")
        if not isinstance(a, (int, float)):
            self.ab_set_a()
        elif not isinstance(b, (int, float)):
            self.ab_set_b()
        else:
            self.ab_clear()

    def cycle_repeat(self):
        order = ["off", "all", "one"]
        r = order[(order.index(self.store["repeat"]) + 1) % 3] if self.store["repeat"] in order else "off"
        self.set_repeat(r)

    def set_repeat(self, r):
        self.store["repeat"] = r
        self._set("loop-file", "inf" if r == "one" else "no")
        self._refresh_repeat_icon()
        self.osd({"off": "반복 끔", "all": "전체 반복", "one": "한 개 반복"}[r])

    def _refresh_repeat_icon(self):
        r = self.store["repeat"]
        self.bar.b_repeat.set_kind("repeat", DIM if r == "off" else ACCENT)
        self.bar.b_repeat.setToolTip({"off": "반복: 끔", "all": "반복: 전체", "one": "반복: 한 개"}[r] + " (클릭해서 바꾸기)")

    def toggle_shuffle(self):
        self.store["shuffle"] = not self.store["shuffle"]
        self.played_shuffle = {self.index}
        self.osd("무작위 재생 켬" if self.store["shuffle"] else "무작위 재생 끔")

    # 트랙
    def tracks(self, kind):
        return [t for t in (self._get("track-list", []) or []) if t.get("type") == kind]

    @staticmethod
    def track_label(t):
        parts = []
        if t.get("title"):
            parts.append(t["title"])
        if t.get("lang"):
            parts.append(f"[{t['lang']}]")
        codec = t.get("codec", "")
        if codec:
            parts.append(codec)
        if t.get("type") == "audio" and t.get("demux-channel-count"):
            parts.append(f"{t['demux-channel-count']}ch")
        if t.get("external"):
            parts.append("(외부 파일)")
        if t.get("default"):
            parts.append("· 기본")
        return f"#{t.get('id')}  " + " ".join(parts)

    def cycle_track(self, kind):
        prop = "aid" if kind == "audio" else "sid"
        tr = self.tracks(kind)
        if not tr:
            self.osd("오디오 트랙이 없어요" if kind == "audio" else "자막이 없어요 (자막 파일을 끌어다 놓아 보세요)")
            return
        try:
            self.m.command("cycle", prop)
        except Exception:
            pass
        cur = self._get(prop, "no")
        sel = next((t for t in self.tracks(kind) if t.get("id") == cur), None)
        name = "오디오" if kind == "audio" else "자막"
        self.osd(f"{name}: " + (self.track_label(sel) if sel else "끔"))

    def set_track(self, prop, tid):
        self._set(prop, tid)

    def toggle_sub(self):
        v = not self._get("sub-visibility", True)
        self._set("sub-visibility", v)
        self.osd("자막 보이기" if v else "자막 숨기기")

    def load_sub(self, path=None):
        if not path:
            start = os.path.dirname(self.current) if self.current and not is_url(self.current) else ""
            path, _ = QFileDialog.getOpenFileName(self, "자막 불러오기", start,
                                                  "자막 (*.srt *.smi *.sami *.ass *.ssa *.vtt *.sub *.idx *.sup *.lrc);;모든 파일 (*.*)")
        if path and self.loaded:
            try:
                self.m.command("sub-add", path, "select")
                self.osd(f"자막 불러옴: {os.path.basename(path)}")
            except Exception as e:
                self.osd(f"자막을 불러오지 못했어요: {e}")

    def sub_delay(self, d):
        v = round((self._get("sub-delay", 0) or 0) + d, 2)
        self._set("sub-delay", v)
        self.osd(f"자막 싱크 {v:+.1f}초")

    def audio_delay(self, d):
        v = 0 if d is None else round((self._get("audio-delay", 0) or 0) + d, 2)
        self._set("audio-delay", v)
        self.osd(f"소리 싱크 {v:+.1f}초")

    def sub_scale(self, d):
        v = round(max(0.3, min(4.0, (self._get("sub-scale", 1.0) or 1.0) + d)), 2)
        self._set("sub-scale", v)
        self.osd(f"자막 크기 {int(v * 100)}%")

    def sub_move(self, d):
        v = int(max(0, min(150, (self._get("sub-pos", 100) or 100) + d)))
        self._set("sub-pos", v)
        self.osd(f"자막 위치 {v}")

    def apply_sub_style(self):
        s = self.store
        self._set("sub-font", s["sub_font"])
        self._set("sub-font-size", int(s["sub_size"]))
        self._set("sub-color", s["sub_color"])
        self._set("sub-border-color", s["sub_border_color"])
        if not self._set("sub-outline-size", float(s["sub_border"])):
            self._set("sub-border-size", float(s["sub_border"]))
        self._set("sub-bold", bool(s["sub_bold"]))
        self._set("sub-pos", int(s["sub_pos"]))
        if s["sub_back_box"]:
            self._set("sub-back-color", "#99000000")
            if not self._set("sub-border-style", "background-box"):
                self._set("sub-shadow-offset", 0)
        else:
            self._set("sub-back-color", "#00000000")
            self._set("sub-border-style", "outline-and-shadow")
        self._set("sub-auto", "fuzzy" if s["sub_auto"] else "no")
        self._set("slang", s["sub_lang"])
        self._set("alang", s["audio_lang"])

    # 소리 효과
    def apply_af(self):
        s = self.store
        filters = []
        pre = next((p for p in AUDIO_PRESETS if p[0] == s["audio_preset"]), None)
        if pre and pre[2]:
            filters.append(pre[2])
        eq = s["eq"] or [0] * 10
        for f, g in zip(EQ_BANDS, eq):
            if g:
                filters.append(f"equalizer=f={f}:width_type=o:width=1:g={g}")
        self._set("audio-channels", s["audio_channels"] or "auto")
        af = f"lavfi=[{','.join(filters)}]" if filters else ""
        if not self._set("af", af):
            self._set("af", "")

    def set_audio_preset(self, key):
        self.store["audio_preset"] = key
        self.apply_af()
        label = next((p[1] for p in AUDIO_PRESETS if p[0] == key), key)
        self.osd(f"음향 효과: {label}")

    def toggle_normalize(self):
        self.set_audio_preset("off" if self.store["audio_preset"] == "normalize" else "normalize")

    def open_eq(self):
        if self.eq_dlg is None:
            labels = [f"{f // 1000}k" if f >= 1000 else str(f) for f in EQ_BANDS]
            self.eq_dlg = SliderPanel("이퀄라이저", labels, self.store["eq"] or [0] * 10, rng=(-12, 12),
                                      vertical=True, presets=EQ_PRESETS, parent=self, unit="dB")
            self.eq_dlg.changed.connect(self._eq_changed)
        self.eq_dlg.show()
        self.eq_dlg.raise_()

    def _eq_changed(self, vals):
        self.store["eq"] = vals
        self.apply_af()

    # 영상
    def _apply_video_state(self):
        names = ["brightness", "contrast", "saturation", "gamma", "hue"]
        for n, v in zip(names, self.adjust):
            self._set(n, int(v))

    def open_adjust(self):
        if self.adjust_dlg is None:
            self.adjust_dlg = SliderPanel("영상 조정", ["밝기", "대비", "채도", "감마", "색조"], self.adjust, parent=self)
            self.adjust_dlg.changed.connect(self._adjust_changed)
        self.adjust_dlg.show()
        self.adjust_dlg.raise_()

    def _adjust_changed(self, vals):
        self.adjust = vals
        self._apply_video_state()

    def set_aspect(self, a):
        self._set("keepaspect", True)
        self._set("panscan", 0.0)
        if a == "stretch":
            self._set("keepaspect", False)
            self.osd("화면 비율: 창에 맞춰 늘이기")
        elif a == "fill":
            self._set("panscan", 1.0)
            self.osd("화면 비율: 꽉 채우기(가장자리 잘림)")
        else:
            self._set("video-aspect-override", a)
            self.osd("화면 비율: " + ("원본" if a in ("-1", "no") else a))

    def rotate(self, d, absolute=False):
        cur = 0 if absolute else (self._get("video-rotate", 0) or 0)
        v = (cur + d) % 360
        self._set("video-rotate", v)
        self.osd(f"회전 {v}°")

    def _apply_flip(self):
        vf = []
        if self.hflip:
            vf.append("hflip")
        if self.vflip:
            vf.append("vflip")
        self._set("vf", ",".join(vf))

    def toggle_hflip(self):
        self.hflip = not self.hflip
        self._apply_flip()
        self.osd("좌우 반전 " + ("켬" if self.hflip else "끔"))

    def toggle_vflip(self):
        self.vflip = not self.vflip
        self._apply_flip()
        self.osd("상하 반전 " + ("켬" if self.vflip else "끔"))

    def zoom(self, d):
        v = round((self._get("video-zoom", 0) or 0) + d, 2)
        self._set("video-zoom", v)
        self.osd(f"확대 {int(2 ** v * 100)}%", 700)

    def pan(self, dx, dy):
        self._set("video-pan-x", round((self._get("video-pan-x", 0) or 0) + dx, 3))
        self._set("video-pan-y", round((self._get("video-pan-y", 0) or 0) + dy, 3))

    def zoom_reset(self):
        for k, v in (("video-zoom", 0), ("video-pan-x", 0), ("video-pan-y", 0), ("video-rotate", 0), ("panscan", 0.0)):
            self._set(k, v)
        self._set("video-aspect-override", "-1")
        self._set("keepaspect", True)
        self.hflip = self.vflip = False
        self._apply_flip()
        self.osd("화면 초기화")

    def set_deinterlace(self, v):
        if not self._set("deinterlace", v):
            self._set("deinterlace", "yes" if v == "auto" else v)
        self.store["deinterlace"] = v
        self.osd("디인터레이스: " + {"auto": "자동", "yes": "켬", "no": "끔"}[v])

    def toggle_hwdec(self):
        self.store["hwdec"] = not self.store["hwdec"]
        self._set("hwdec", "auto-safe" if self.store["hwdec"] else "no")
        self.osd("하드웨어 가속 " + ("켬" if self.store["hwdec"] else "끔 (호환 모드)"))

    def toggle_stats(self):
        try:
            self.m.command("script-binding", "stats/display-stats-toggle")
        except Exception:
            self.osd("통계 기능을 쓸 수 없어요")

    # 캡처
    def _shot_dir(self):
        d = self.store["shot_dir"] or default_shot_dir()
        os.makedirs(d, exist_ok=True)
        return d

    def screenshot(self, subs=None):
        if not self.loaded:
            return
        if subs is None:
            subs = self.store["shot_with_subs"]
        base = os.path.splitext(os.path.basename(self.current or "capture"))[0] if not is_url(self.current or "") else \
            re.sub(r'[\\/:*?"<>|]+', "_", (self._get("media-title", "") or "capture"))[:60]
        t = self._get("time-pos", 0) or 0
        h, r = divmod(int(t), 3600)
        mi, se = divmod(r, 60)
        ms = int((t - int(t)) * 1000)
        name = f"{base}_{h:02d}{mi:02d}{se:02d}.{ms:03d}.{self.store['shot_format']}"
        path = os.path.join(self._shot_dir(), name)
        try:
            self.m.command("screenshot-to-file", path, "subtitles" if subs else "video")
            self.osd(f"캡처 저장: {name}", 2000)
        except Exception as e:
            self.osd(f"캡처 실패: {e}")

    def screenshot_clipboard(self):
        if not self.loaded:
            return
        tmp = os.path.join(tempfile.gettempdir(), "cfp_clip.png")
        try:
            self.m.command("screenshot-to-file", tmp, "subtitles" if self.store["shot_with_subs"] else "video")
            img = QImage(tmp)
            if not img.isNull():
                QGuiApplication.clipboard().setImage(img)
                self.osd("화면을 클립보드에 복사했어요 (Ctrl+V로 붙여넣기)", 2000)
        except Exception as e:
            self.osd(f"복사 실패: {e}")

    # 북마크
    def add_bookmark(self):
        if not self.loaded or not self.current:
            return
        t = self._get("time-pos", 0) or 0
        self.store.add_bookmark(self.current, t, fmt_time(t))
        self._refresh_markers()
        self.osd(f"북마크 추가: {fmt_time(t)}")

    # ================================================================ 창
    def toggle_fullscreen(self):
        if self.mini:
            self.toggle_mini()
        if self.isFullScreen():
            self._float_bar(False)
            self.showNormal()
            if self.store["playlist_visible"]:
                self.plist.setVisible(True)
        else:
            self.plist.setVisible(False)
            self.showFullScreen()
            QTimer.singleShot(50, lambda: self._float_bar(True))

    def _float_bar(self, on):
        if on == self.fs_bar_floating:
            return
        self.fs_bar_floating = on
        if on:
            self.left_layout.removeWidget(self.bar)
            self.bar.setParent(self, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
            self.bar.setAttribute(Qt.WA_ShowWithoutActivating)
            self.bar.b_full.set_kind("unfullscreen")
            self._place_fs_bar()
            self.bar.show()
            self._sub_margin(True)
            self.last_activity = time.time()
        else:
            self._sub_margin(False)
            self.bar.hide()
            self.bar.setParent(None)
            self.bar.setWindowFlags(Qt.Widget)
            self.left_layout.addWidget(self.bar)
            self.bar.b_full.set_kind("fullscreen")
            self.bar.show()

    def _sub_margin(self, bar_shown):
        """전체 화면에서 컨트롤바가 보이면 자막을 바 위로 올림 (유튜브처럼)."""
        if bar_shown and self.height() > 0:
            self._set("sub-margin-y", int(22 + self.bar.height() * 720 / self.height()))
        else:
            self._set("sub-margin-y", 22)

    def _place_fs_bar(self):
        g = self.geometry()
        h = self.bar.sizeHint().height()
        self.bar.setGeometry(g.x(), g.y() + g.height() - h, g.width(), h)

    def escape(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
        elif self.mini:
            self.toggle_mini()
        elif self.store["esc_quits"]:
            self.close()

    def window_scale(self, factor):
        """factor=None 이면 화면에 맞게 자동."""
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.isMaximized():
            self.showNormal()
        dw = self._get("dwidth", None)
        dh = self._get("dheight", None)
        if not dw or not dh:
            return
        scr = (self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()).availableGeometry()
        extra_w = self.width() - self.video.width()
        extra_h = self.height() - self.video.height()
        frame_w = self.frameGeometry().width() - self.width()
        frame_h = self.frameGeometry().height() - self.height()
        maxw = scr.width() * 0.9 - extra_w - frame_w
        maxh = scr.height() * 0.9 - extra_h - frame_h
        if factor is None:
            k = min(1.0, maxw / dw, maxh / dh)
            w, h = dw * k, dh * k
            if w < 800:
                k2 = min(800 / w, maxw / w, maxh / h)
                w, h = w * k2, h * k2
        else:
            w, h = dw * factor, dh * factor
            if w > maxw or h > maxh:
                k = min(maxw / w, maxh / h)
                w, h = w * k, h * k
            self.osd(f"창 크기 {int(factor * 100)}%")
        nw, nh = int(w + extra_w), int(h + extra_h)
        g = self.geometry()
        cx, cy = g.center().x(), g.center().y()
        x = max(scr.left(), min(cx - nw // 2, scr.right() - nw - frame_w))
        y = max(scr.top() + frame_h, min(cy - nh // 2, scr.bottom() - nh))
        self.setGeometry(x, y, nw, nh)

    def toggle_mini(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
        if not self.mini:
            self.mini = True
            self.mini_restore = (self.geometry(), self.plist.isVisible(), self.isMaximized())
            if self.isMaximized():
                self.showNormal()
            self.plist.setVisible(False)
            self.bar.setVisible(False)
            scr = (self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()).availableGeometry()
            dw = self._get("dwidth", 16) or 16
            dh = self._get("dheight", 9) or 9
            w = 480
            h = int(w * dh / dw)
            self.setMinimumSize(200, 110)
            self.setGeometry(scr.right() - w - 24, scr.bottom() - h - 24, w, h)
            self.set_on_top(True)
            self.osd("미니 플레이어 · 끌어서 옮기기 · 더블클릭/i 로 돌아가기", 2500)
        else:
            self.mini = False
            geo, pl, maxed = self.mini_restore or (None, False, False)
            self.bar.setVisible(True)
            self.plist.setVisible(pl)
            self.setMinimumSize(480, 300)
            if geo:
                self.setGeometry(geo)
            if maxed:
                self.showMaximized()
            self.set_on_top(self.store["always_on_top"] == "always")

    def set_on_top(self, on, announce=False):
        self.on_top = on
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
                SWP = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, SWP)
            except Exception:
                pass
        else:
            wh = self.windowHandle()
            if wh:
                wh.setFlag(Qt.WindowStaysOnTopHint, on)
        if announce:
            self.store["always_on_top"] = "always" if on else "never"
            self.osd("항상 위 " + ("켬" if on else "끔"))

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange and not self.isFullScreen() and self.fs_bar_floating:
            self._float_bar(False)

    def moveEvent(self, e):
        super().moveEvent(e)
        if self.fs_bar_floating:
            self._place_fs_bar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fs_bar_floating:
            self._place_fs_bar()

    # ================================================================ 시크바 미리보기
    def _seek_hover(self, sec, gpos):
        self.hover_sec = sec
        self.hover_gpos = gpos
        if sec is None or not self.loaded:
            self.thumb_popup.hide()
            return
        img = self.thumbs.get(sec) if self.store["thumbnails"] else None
        self._show_thumb(img)

    def _thumb_ready(self, path, bucket, img):
        if self.hover_sec is not None and path == self.current and self.thumbs.bucket(self.hover_sec) == bucket:
            self._show_thumb(img)

    def _show_thumb(self, img):
        sec = self.hover_sec
        if sec is None:
            return
        chap = self.bar.seek.chapter_at(sec)
        self.thumb_popup.set_content(img, fmt_time(sec, (self.bar.seek.duration or 0) >= 3600), chap)
        pw, ph = self.thumb_popup.width(), self.thumb_popup.height()
        x = self.hover_gpos.x() - pw // 2
        scr = QGuiApplication.screenAt(self.hover_gpos) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        x = max(g.left() + 2, min(x, g.right() - pw - 2))
        y = self.hover_gpos.y() - ph - 8
        self.thumb_popup.move(x, y)
        if not self.thumb_popup.isVisible():
            self.thumb_popup.show()

    # ================================================================ 드래그 앤 드롭
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        paths = []
        if md.hasUrls():
            paths = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in md.urls()]
        elif md.hasText():
            paths = [md.text().strip()]
        append = bool(e.modifiers() & Qt.ControlModifier) or (self.plist.isVisible() and
                                                               self.plist.geometry().contains(self.plist.parentWidget().mapFrom(self, e.position().toPoint())))
        self.activateWindow()
        self.open_paths(paths, append=append)

    def handle_message(self, args):
        """다른 실행(파일 더블클릭)에서 넘어온 인자."""
        files = [a for a in args if a and not a.startswith("--")]
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if files:
            self.open_paths(files, append="--append" in args)

    # ================================================================ 메뉴
    def _popup(self, menu, anchor):
        pos = anchor.mapToGlobal(QPoint(0, 0))
        menu.adjustSize()
        menu.exec(QPoint(pos.x(), pos.y() - menu.sizeHint().height()))

    def show_menu(self, gpos, above=None):
        m = self.build_menu()
        if above is not None:
            m.adjustSize()
            gpos = QPoint(gpos.x(), gpos.y() - m.sizeHint().height())
        m.exec(gpos)

    def _act(self, menu, text, fn, shortcut=None, checked=None, enabled=True):
        a = QAction(text, menu)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutVisibleInContextMenu(True)
            a.setShortcutContext(Qt.WidgetShortcut)
        if checked is not None:
            a.setCheckable(True)
            a.setChecked(bool(checked))
        a.setEnabled(enabled)
        a.triggered.connect(lambda *_: fn())
        menu.addAction(a)
        return a

    def _speed_menu(self, parent=None):
        m = QMenu("재생 속도", parent or self)
        cur = self._get("speed", 1.0) or 1.0
        for sp in SPEEDS:
            self._act(m, f"{sp:g}x" + ("  (보통)" if sp == 1 else ""), lambda sp=sp: self.set_speed(sp),
                      checked=abs(cur - sp) < 1e-3)
        m.addSeparator()
        self._act(m, "빠르게 +0.1", lambda: self.change_speed(0.1), "C")
        self._act(m, "느리게 -0.1", lambda: self.change_speed(-0.1), "X")
        self._act(m, "직접 입력…", self._speed_input)
        return m

    def _speed_input(self):
        v, ok = QInputDialog.getDouble(self, "재생 속도", "배속 (0.1 ~ 8):", self._get("speed", 1.0) or 1.0, 0.1, 8.0, 2)
        if ok:
            self.set_speed(v)

    def _track_menu(self, title, kind, prop, allow_off=True, parent=None):
        m = QMenu(title, parent or self)
        cur = self._get(prop, "no")
        tr = self.tracks(kind)
        if allow_off:
            self._act(m, "끄기", lambda: self.set_track(prop, "no"), checked=cur in ("no", False, None))
        for t in tr:
            self._act(m, self.track_label(t), lambda tid=t["id"]: self.set_track(prop, tid), checked=cur == t["id"])
        if not tr:
            a = m.addAction("(트랙 없음)")
            a.setEnabled(False)
        return m

    def _sub_menu(self, parent=None):
        m = QMenu("자막", parent or self)
        m.addMenu(self._track_menu("자막 트랙", "sub", "sid", parent=m))
        m.addMenu(self._track_menu("보조 자막 (이중 자막)", "sub", "secondary-sid", parent=m))
        self._act(m, "자막 파일 불러오기…", lambda: self.load_sub())
        self._act(m, "자막 보이기", self.toggle_sub, "V", checked=self._get("sub-visibility", True))
        m.addSeparator()
        d = self._get("sub-delay", 0) or 0
        sm = m.addMenu(f"자막 싱크 ({d:+.1f}초)")
        self._act(sm, "빠르게 -0.1초", lambda: self.sub_delay(-0.1), "Alt+Left")
        self._act(sm, "늦게 +0.1초", lambda: self.sub_delay(0.1), "Alt+Right")
        self._act(sm, "빠르게 -1초", lambda: self.sub_delay(-1))
        self._act(sm, "늦게 +1초", lambda: self.sub_delay(1))
        self._act(sm, "초기화", lambda: (self._set("sub-delay", 0), self.osd("자막 싱크 0")))
        zm = m.addMenu("크기 / 위치")
        self._act(zm, "크게", lambda: self.sub_scale(0.1), "Alt+Up")
        self._act(zm, "작게", lambda: self.sub_scale(-0.1), "Alt+Down")
        self._act(zm, "위로", lambda: self.sub_move(-2), "Alt+Shift+Up")
        self._act(zm, "아래로", lambda: self.sub_move(2), "Alt+Shift+Down")
        self._act(zm, "기본값", lambda: (self._set("sub-scale", 1.0), self._set("sub-pos", int(self.store["sub_pos"])),
                                       self.osd("자막 크기·위치 기본값")))
        self._act(m, "자막 모양 설정…", lambda: self.open_settings(tab=3))
        return m

    def build_menu(self):
        m = QMenu(self)
        loaded = self.loaded
        # 열기
        om = m.addMenu("열기")
        self._act(om, "파일 열기…", self.open_file_dialog, "Ctrl+O")
        self._act(om, "폴더 열기…", self.open_folder_dialog)
        self._act(om, "주소(URL) 열기… (유튜브 등)", self.open_url_dialog, "Ctrl+U")
        self._act(om, "클립보드에서 열기", self.paste, "Ctrl+V")
        self._act(om, "자막 파일 불러오기…", lambda: self.load_sub(), enabled=loaded)
        rm = om.addMenu("최근 파일")
        for p in self.store.recent[:15]:
            self._act(rm, (os.path.basename(p) if not is_url(p) else p)[:70], lambda p=p: self.open_paths([p]))
        if self.store.recent:
            rm.addSeparator()
            self._act(rm, "목록 지우기", lambda: (self.store.recent.clear(), self._refresh_welcome()))
        if self.current and not is_url(self.current):
            self._act(om, "탐색기에서 현재 파일 보기", lambda: self.reveal(self.current))
        m.addSeparator()
        # 재생
        pm = m.addMenu("재생")
        self._act(pm, "재생 / 일시정지", self.toggle_pause, "Space")
        self._act(pm, "정지", self.stop)
        self._act(pm, "이전 파일", self.prev, "PgUp")
        self._act(pm, "다음 파일", lambda: self.next(manual=True), "PgDown")
        self._act(pm, "시간으로 이동…", self.goto_time_dialog, enabled=loaded)
        self._act(pm, "다음 프레임", self.frame_step, ".", enabled=loaded)
        self._act(pm, "이전 프레임", self.frame_back, ",", enabled=loaded)
        pm.addSeparator()
        pm.addMenu(self._speed_menu(pm))
        abm = pm.addMenu("구간 반복 (A-B)")
        self._act(abm, "시작점 A", self.ab_set_a, "[", enabled=loaded)
        self._act(abm, "끝점 B", self.ab_set_b, "]", enabled=loaded)
        self._act(abm, "해제", self.ab_clear, "\\")
        rpm = pm.addMenu("반복")
        for k, t in (("off", "반복 안 함"), ("all", "전체 반복"), ("one", "한 개 반복")):
            self._act(rpm, t, lambda k=k: self.set_repeat(k), checked=self.store["repeat"] == k)
        self._act(pm, "무작위 재생", self.toggle_shuffle, checked=self.store["shuffle"])
        chs = self._get("chapter-list", []) or []
        if chs:
            cm = pm.addMenu(f"챕터 ({len(chs)})")
            cur = self._get("chapter", -1)
            for i, c in enumerate(chs):
                self._act(cm, f"{fmt_time(c.get('time', 0))}  {c.get('title', '') or f'챕터 {i + 1}'}",
                          lambda i=i: self._set("chapter", i), checked=i == cur)
        bm = pm.addMenu("북마크")
        self._act(bm, "현재 위치 북마크", self.add_bookmark, "B", enabled=loaded)
        bms = self.store.get_bookmarks(self.current) if self.current else []
        if bms:
            bm.addSeparator()
            for i, (sec, label) in enumerate(bms):
                self._act(bm, f"▶ {label}", lambda sec=sec: self.seek_abs(sec))
            dm = bm.addMenu("북마크 지우기")
            for i, (sec, label) in enumerate(bms):
                self._act(dm, label, lambda i=i: (self.store.remove_bookmark(self.current, i), self._refresh_markers()))
        em = pm.addMenu("재생이 끝나면")
        for k, t in (("none", "아무것도 안 함"), ("quit", "플레이어 종료"), ("sleep", "컴퓨터 절전"), ("shutdown", "컴퓨터 끄기")):
            self._act(em, t, lambda k=k: self._set_end_action(k), checked=self.end_action == k)
        stm = pm.addMenu("취침 타이머" + (f" ({int((self.sleep_deadline - time.time()) / 60) + 1}분 남음)" if self.sleep_deadline else ""))
        self._act(stm, "끄기", lambda: self._sleep(None), checked=self.sleep_deadline is None)
        for mins in (15, 30, 45, 60, 90, 120):
            self._act(stm, f"{mins}분 뒤 일시정지", lambda mins=mins: self._sleep(mins))
        # 화면
        vm = m.addMenu("화면")
        self._act(vm, "전체 화면", self.toggle_fullscreen, "Enter", checked=self.isFullScreen())
        self._act(vm, "미니 플레이어 (PIP)", self.toggle_mini, "I", checked=self.mini)
        atm = vm.addMenu("항상 위")
        for k, t in (("never", "사용 안 함"), ("always", "항상"), ("playing", "재생 중일 때만")):
            self._act(atm, t, lambda k=k: self._set_on_top_mode(k), checked=self.store["always_on_top"] == k)
        wm = vm.addMenu("창 크기")
        for f, key in ((0.5, "Alt+1"), (1.0, "Alt+2"), (1.5, "Alt+3"), (2.0, "Alt+4")):
            self._act(wm, f"{int(f * 100)}%", lambda f=f: self.window_scale(f), key, enabled=loaded)
        self._act(wm, "화면에 맞춤", lambda: self.window_scale(None), enabled=loaded)
        arm = vm.addMenu("화면 비율")
        for v, t in (("-1", "원본"), ("16:9", "16:9"), ("4:3", "4:3"), ("21:9", "21:9"), ("2.35:1", "2.35:1 (시네마)"),
                     ("1:1", "1:1"), ("9:16", "9:16 (세로)"), ("fill", "꽉 채우기 (가장자리 잘림)"), ("stretch", "창에 맞춰 늘이기")):
            self._act(arm, t, lambda v=v: self.set_aspect(v))
        rom = vm.addMenu("회전 / 반전")
        rot = self._get("video-rotate", 0) or 0
        for d in (0, 90, 180, 270):
            self._act(rom, f"{d}°", lambda d=d: self.rotate(d, absolute=True), checked=rot == d)
        rom.addSeparator()
        self._act(rom, "좌우 반전", self.toggle_hflip, checked=self.hflip)
        self._act(rom, "상하 반전", self.toggle_vflip, checked=self.vflip)
        zm = vm.addMenu("확대 / 이동")
        self._act(zm, "확대", lambda: self.zoom(0.1), "Ctrl+=")
        self._act(zm, "축소", lambda: self.zoom(-0.1), "Ctrl+-")
        self._act(zm, "왼쪽으로", lambda: self.pan(0.05, 0))
        self._act(zm, "오른쪽으로", lambda: self.pan(-0.05, 0))
        self._act(zm, "위로", lambda: self.pan(0, 0.05))
        self._act(zm, "아래로", lambda: self.pan(0, -0.05))
        self._act(zm, "초기화", self.zoom_reset, "Ctrl+0")
        self._act(vm, "영상 조정 (밝기·대비·채도)…", self.open_adjust)
        dim = vm.addMenu("디인터레이스")
        for k, t in (("auto", "자동"), ("yes", "켬"), ("no", "끔")):
            self._act(dim, t, lambda k=k: self.set_deinterlace(k), checked=self.store["deinterlace"] == k)
        self._act(vm, "하드웨어 가속", self.toggle_hwdec, checked=self.store["hwdec"])
        self._act(vm, "재생 통계 (화면 위)", self.toggle_stats, "Tab", enabled=loaded)
        # 소리
        am = m.addMenu("소리")
        am.addMenu(self._track_menu("오디오 트랙", "audio", "aid", allow_off=False, parent=am))
        self._act(am, "음소거", self.toggle_mute, "M", checked=self._get("mute", False))
        self._act(am, "볼륨 +5", lambda: self.change_volume(5), "Up")
        self._act(am, "볼륨 -5", lambda: self.change_volume(-5), "Down")
        afm = am.addMenu("음향 효과")
        for k, t, _ in AUDIO_PRESETS:
            self._act(afm, t, lambda k=k: self.set_audio_preset(k), checked=self.store["audio_preset"] == k)
        self._act(am, "이퀄라이저…", self.open_eq)
        ad = self._get("audio-delay", 0) or 0
        adm = am.addMenu(f"소리 싱크 ({ad:+.1f}초)")
        self._act(adm, "빠르게 -0.1초", lambda: self.audio_delay(-0.1), "Ctrl+[")
        self._act(adm, "늦게 +0.1초", lambda: self.audio_delay(0.1), "Ctrl+]")
        self._act(adm, "초기화", lambda: self.audio_delay(None), "Ctrl+\\")
        chm = am.addMenu("채널")
        cur_ch = self.store["audio_channels"]
        for k, t in (("auto", "자동 (원본)"), ("stereo", "스테레오로 다운믹스"), ("mono", "모노")):
            self._act(chm, t, lambda k=k: self._set_channels(k), checked=cur_ch == k)
        devs = self._get("audio-device-list", []) or []
        if devs:
            dvm = am.addMenu("출력 장치")
            cur = self._get("audio-device", "auto")
            for d in devs:
                self._act(dvm, d.get("description", d.get("name")), lambda n=d.get("name"): self._set("audio-device", n),
                          checked=cur == d.get("name"))
        # 자막
        m.addMenu(self._sub_menu(m))
        # 캡처
        sm = m.addMenu("캡처")
        self._act(sm, "화면 캡처", lambda: self.screenshot(), "Ctrl+E", enabled=loaded)
        self._act(sm, "자막 없이 캡처", lambda: self.screenshot(False), enabled=loaded)
        self._act(sm, "클립보드로 복사", self.screenshot_clipboard, "Ctrl+C", enabled=loaded)
        self._act(sm, "캡처 폴더 열기", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self._shot_dir())))
        m.addSeparator()
        self._act(m, "재생목록", self.toggle_playlist, "P", checked=self.plist.isVisible())
        self._act(m, "미디어 정보", self.media_info, "Ctrl+I", enabled=loaded)
        m.addSeparator()
        self._act(m, "환경설정…", self.open_settings, "F5")
        self._act(m, "단축키 보기", self.show_help, "F1")
        self._act(m, "업데이트 확인", lambda: self.updater.check(True))
        self._act(m, f"정보 (v{VERSION})", lambda: QMessageBox.about(self, APP_NAME, about_text()))
        m.addSeparator()
        self._act(m, "종료", self.close, "Q")
        return m

    def _set_end_action(self, k):
        self.end_action = k
        self.osd("재생이 끝나면: " + {"none": "아무것도 안 함", "quit": "플레이어 종료", "sleep": "컴퓨터 절전",
                                   "shutdown": "컴퓨터 끄기"}[k], 2000)

    def _sleep(self, mins):
        self.sleep_deadline = time.time() + mins * 60 if mins else None
        self.osd(f"취침 타이머 {mins}분" if mins else "취침 타이머 끔")

    def _set_on_top_mode(self, k):
        self.store["always_on_top"] = k
        self.set_on_top(k == "always" or (k == "playing" and self.loaded and not self._get("pause", False)))

    def _set_channels(self, k):
        self.store["audio_channels"] = k
        self.apply_af()
        self.osd("채널: " + {"auto": "자동", "stereo": "스테레오", "mono": "모노"}[k])

    # ================================================================ 창들
    def open_settings(self, tab=0):
        dlg = SettingsDialog(self.store, self)
        tabs = dlg.findChildren(QTabWidget)
        if tabs and isinstance(tab, int):
            tabs[0].setCurrentIndex(tab)
        if dlg.exec():
            dlg.apply()
            s = self.store
            self._set("hwdec", "auto-safe" if s["hwdec"] else "no")
            self._set("volume-max", int(s["volume_max"]))
            self.bar.vol.setMaximum(int(s["volume_max"]))
            self._set("screenshot-format", s["shot_format"])
            self._set("ytdl-format", self._ytdl_format())
            self.set_deinterlace(s["deinterlace"])
            self.apply_sub_style()
            self._set_on_top_mode(s["always_on_top"])
            self.osd("설정 저장됨")

    def show_help(self):
        ShortcutsDialog(self).exec()

    def media_info(self):
        if not self.loaded:
            return
        g = self._get
        lines = []

        def add(k, v):
            if v not in (None, "", [], {}):
                lines.append(f"{k:<14}{v}")
        add("파일", self.current)
        add("제목", g("media-title"))
        add("컨테이너", g("file-format"))
        fs = g("file-size")
        if fs:
            add("크기", f"{fs / 1024 / 1024:.1f} MB")
        add("길이", fmt_time(g("duration", 0), True))
        lines.append("")
        vp = g("video-params", {}) or {}
        add("비디오 코덱", g("video-codec"))
        if vp:
            add("해상도", f"{vp.get('w')} x {vp.get('h')}  (표시 {g('dwidth')} x {g('dheight')})")
            add("픽셀 형식", vp.get("pixelformat"))
            add("색공간", f"{vp.get('colormatrix', '')} / {vp.get('primaries', '')} / {vp.get('gamma', '')}")
        fps = g("container-fps")
        if fps:
            add("프레임", f"{fps:.3f} fps")
        vb = g("video-bitrate")
        if vb:
            add("비디오 비트", f"{vb / 1000:.0f} kbps")
        add("하드웨어 가속", g("hwdec-current") or "사용 안 함")
        lines.append("")
        ap = g("audio-params", {}) or {}
        add("오디오 코덱", g("audio-codec"))
        if ap:
            add("샘플레이트", f"{ap.get('samplerate')} Hz")
            add("채널", f"{ap.get('channel-count')} ({ap.get('hr-channels', ap.get('channels', ''))})")
        ab = g("audio-bitrate")
        if ab:
            add("오디오 비트", f"{ab / 1000:.0f} kbps")
        lines.append("")
        lines.append("트랙")
        for t in g("track-list", []) or []:
            kind = {"video": "영상", "audio": "소리", "sub": "자막"}.get(t.get("type"), t.get("type"))
            lines.append(f"  {kind:<4}{self.track_label(t)}" + ("  ◀ 사용 중" if t.get("selected") else ""))
        chs = g("chapter-list", []) or []
        if chs:
            lines.append("")
            lines.append(f"챕터 {len(chs)}개")
        meta = g("metadata", {}) or {}
        if meta:
            lines.append("")
            lines.append("메타데이터")
            for k, v in list(meta.items())[:30]:
                lines.append(f"  {k}: {v}")
        MediaInfoDialog("\n".join(str(x) for x in lines), self).exec()

    # ================================================================ 업데이트
    def _update_found(self, ver, notes, url, size):
        box = QMessageBox(self)
        box.setWindowTitle("업데이트")
        box.setText(f"새 버전 {ver} 이 나왔어요! (지금 {VERSION})\n\n{notes[:600]}\n\n지금 업데이트할까요?\n"
                    f"보고 있던 영상은 업데이트 뒤 같은 위치에서 다시 열려요.")
        b_yes = box.addButton("지금 업데이트", QMessageBox.AcceptRole)
        box.addButton("나중에", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == b_yes:
            self.update_dlg = QProgressDialog("업데이트 받는 중…", "취소", 0, 100, self)
            self.update_dlg.setWindowTitle("업데이트")
            self.update_dlg.setWindowModality(Qt.WindowModal)
            self.update_dlg.canceled.connect(lambda: setattr(self.updater, "cancel", True))
            self.update_dlg.show()
            self.updater.download(url, size)

    def _update_progress(self, got, total):
        if self.update_dlg and total:
            self.update_dlg.setValue(int(got * 100 / total))
            self.update_dlg.setLabelText(f"업데이트 받는 중… {got / 1048576:.0f} / {total / 1048576:.0f} MB")

    def _update_failed(self, msg):
        if self.update_dlg:
            self.update_dlg.close()
            self.update_dlg = None
        QMessageBox.warning(self, "업데이트", msg)

    def _update_ready(self, path):
        if self.update_dlg:
            self.update_dlg.close()
            self.update_dlg = None
        self._save_position()
        self.store.save()
        try:
            run_installer(path)
        except Exception as e:
            QMessageBox.warning(self, "업데이트", f"설치 프로그램 실행 실패: {e}")
            return
        self.updating = True
        self.close()

    # ================================================================ 종료
    def closeEvent(self, e):
        self._save_position()
        if self.fs_bar_floating:
            self._float_bar(False)
        if self.store["remember_window"] and not self.isFullScreen() and not self.mini and not self.isMaximized():
            g = self.geometry()
            self.store["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        if self.plist.isVisible():
            self.store["playlist_width"] = self.plist.width()
        try:
            self.store["volume"] = int(self._get("volume", self.store["volume"]))
            self.store["muted"] = bool(self._get("mute", False))
        except Exception:
            pass
        if not getattr(self, "updating", False):
            self.store.session = {}
        self.store.save()
        self.thumbs.stop()
        self.thumb_popup.close()
        for d in (self.eq_dlg, self.adjust_dlg):
            if d:
                d.close()
        try:
            self.m.terminate()
        except Exception:
            pass
        super().closeEvent(e)
        QApplication.quit()
