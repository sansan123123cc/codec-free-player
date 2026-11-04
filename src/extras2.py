"""v2.2 기능: 자막 번역, 부드러운 움직임(프레임 보간), 음악 모드, 유튜브 연결, 시작 화면 꾸미기."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

from PySide6.QtCore import Qt, QObject, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QIcon, QImage, QGuiApplication, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                               QLabel, QComboBox, QMenu, QMessageBox, QFileDialog, QCheckBox, QButtonGroup, QFormLayout,
                               QDialogButtonBox)

import features as F
import widgets as W
from store import data_dir
from extras_ui import _gtx

NOWIN = 0x08000000 if sys.platform == "win32" else 0
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "sami", "stl"}


# ------------------------------------------------------------------ 자막 읽기 / 번역
def _clean_ass(t):
    t = re.sub(r"\{[^}]*\}", "", t)
    return t.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ").strip()


def _ts(sec):
    sec = max(0.0, sec)
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_time(s):
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    v = 0.0
    for p in parts:
        v = v * 60 + float(p)
    return v


def read_sub_file(path):
    """외부 자막 파일 -> [(시작, 끝, 글)]"""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949", "utf-16", "shift_jis", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    ext = os.path.splitext(path)[1].lower()
    cues = []
    if ext in (".ass", ".ssa"):
        fmt = None
        for line in text.splitlines():
            if line.startswith("Format:") and fmt is None and "Start" in line:
                fmt = [x.strip().lower() for x in line[7:].split(",")]
            if line.startswith("Dialogue:") and fmt:
                vals = line[9:].split(",", len(fmt) - 1)
                d = dict(zip(fmt, vals))
                txt = _clean_ass(d.get("text", ""))
                if txt:
                    cues.append((_parse_time(d["start"]), _parse_time(d["end"]), txt))
    elif ext in (".smi", ".sami"):
        syncs = re.findall(r"<sync\s+start\s*=\s*(\d+)[^>]*>(.*?)(?=<sync|</body|$)", text, re.I | re.S)
        for i, (ms, body) in enumerate(syncs):
            body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
            body = re.sub(r"<[^>]+>", "", body).replace("&nbsp;", " ").strip()
            if body:
                end = int(syncs[i + 1][0]) if i + 1 < len(syncs) else int(ms) + 3000
                cues.append((int(ms) / 1000, end / 1000, body))
    else:  # srt / vtt
        for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
            lines = [l for l in block.splitlines() if l.strip()]
            for i, l in enumerate(lines):
                m = re.match(r"\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", l)
                if m:
                    txt = re.sub(r"<[^>]+>", "", "\n".join(lines[i + 1:])).strip()
                    if txt:
                        cues.append((_parse_time(m.group(1)), _parse_time(m.group(2)), txt))
                    break
    return cues


def read_embedded_subs(path, ff_index, codec):
    """영상 안에 든 글자 자막 -> [(시작, 끝, 글)] (PyAV 로 패킷만 읽음)"""
    import av
    c = av.open(path)
    st = c.streams[ff_index]
    cues = []
    for p in c.demux(st):
        if p.size == 0 or p.pts is None:
            continue
        data = bytes(p)
        if codec == "mov_text" and len(data) >= 2:
            n = int.from_bytes(data[:2], "big")
            data = data[2:2 + n]
        t = data.decode("utf-8", "replace")
        if codec in ("ass", "ssa"):
            t = _clean_ass(t.split(",", 8)[-1])
        else:
            t = re.sub(r"<[^>]+>", "", t).strip()
        start = float(p.pts * p.time_base)
        dur = float((p.duration or 0) * p.time_base) or 3.0
        if t:
            cues.append((start, start + dur, t))
    c.close()
    cues.sort(key=lambda x: x[0])
    return cues


def translate_cues(cues, sl, tl, progress=None):
    texts = [c[2].replace("\n", " ") for c in cues]
    out = [None] * len(texts)
    i = 0
    while i < len(texts):
        j, size = i, 0
        while j < len(texts) and size + len(texts[j]) < 3500 and j - i < 80:
            size += len(texts[j]) + 1
            j += 1
        j = max(j, i + 1)
        chunk = texts[i:j]
        try:
            tr = _gtx("\n".join(chunk), sl, tl).split("\n")
        except Exception:
            tr = []
        if len(tr) == len(chunk):
            out[i:j] = [t.strip() for t in tr]
        else:
            for k in range(i, j):
                try:
                    out[k] = _gtx(texts[k], sl, tl).strip()
                except Exception:
                    out[k] = texts[k]
                time.sleep(0.05)
        i = j
        if progress:
            progress(i * 100 / len(texts), f"번역 중 {i}/{len(texts)}줄")
        time.sleep(0.15)
    return [(c[0], c[1], t or c[2]) for c, t in zip(cues, out)]


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as fh:
        for n, (a, b, t) in enumerate(cues, 1):
            fh.write(f"{n}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n")
    return path


# ------------------------------------------------------------------ 음악 모드 그래프
def viz_graph(kind, aid, cover_vid, accent):
    col = "0x" + QColor(accent).name()[1:]
    if kind == "waves":
        viz = f"showwaves=s=1280x720:mode=cline:rate=30:colors={col}|0xa07cff:scale=sqrt"
    elif kind == "spectrum":
        viz = "showspectrum=s=1280x720:mode=combined:color=intensity:slide=scroll:scale=log:fps=30"
    else:
        viz = "showcqt=s=1280x720:fps=30:bar_g=2:sono_g=4:axis=0:count=2"
    if cover_vid:
        return (f"[aid{aid}]asplit[ao][a2];[a2]{viz},format=yuv420p[viz];"
                f"[vid{cover_vid}]scale=w=-2:h=360,format=yuva420p[cov];"
                f"[viz][cov]overlay=x=(W-w)/2:y=(H-h)/2-80:eof_action=repeat[vo]")
    return f"[aid{aid}]asplit[ao][a2];[a2]{viz}[vo]"


# ------------------------------------------------------------------ 유튜브
YT_FEEDS = [
    ("search", "검색"),
    ("https://www.youtube.com/feed/subscriptions", "구독"),
    ("https://www.youtube.com/playlist?list=WL", "나중에 볼 동영상"),
    ("https://www.youtube.com/playlist?list=LL", "좋아요 표시한 동영상"),
    ("https://www.youtube.com/feed/history", "시청 기록"),
]
BROWSERS = [("whale", "네이버 웨일"), ("chrome", "크롬"), ("edge", "엣지"), ("firefox", "파이어폭스")]


def cookie_args(cfg):
    if not cfg:
        return []
    kind, _, val = cfg.partition(":")
    if kind == "browser":
        return ["--cookies-from-browser", val]
    if kind == "file" and os.path.isfile(val):
        return ["--cookies", val]
    return []


class YtFetcher(QObject):
    done = Signal(int, list, str)        # request id, entries, error
    thumb = Signal(str, QImage)

    def __init__(self, exe):
        super().__init__()
        self.exe = exe
        self.req = 0
        self.thumb_cache = {}

    def fetch(self, target, count, cookies):
        self.req += 1
        rid = self.req
        threading.Thread(target=self._run, args=(rid, target, count, cookies), daemon=True).start()
        return rid

    def _run(self, rid, target, count, cookies):
        try:
            args = [self.exe, "--flat-playlist", "-J", "--no-warnings", "--ignore-errors",
                    "--playlist-end", str(count)] + cookie_args(cookies) + [target]
            p = subprocess.run(args, capture_output=True, timeout=120, creationflags=NOWIN,
                               text=True, encoding="utf-8", errors="replace")
            if p.returncode != 0 and not p.stdout.strip():
                err = (p.stderr or "").strip().splitlines()
                raise RuntimeError(err[-1] if err else f"yt-dlp 오류 {p.returncode}")
            d = json.loads(p.stdout)
            entries = []
            for e in d.get("entries") or []:
                if not e:
                    continue
                vid = e.get("id") or ""
                url = e.get("url") or ""
                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={vid}"
                if "/channel/" in url or "/playlist?" in url and "watch" not in url:
                    kind = "list"
                else:
                    kind = "video"
                entries.append({
                    "id": vid, "url": url, "title": e.get("title") or vid, "kind": kind,
                    "channel": e.get("channel") or e.get("uploader") or "",
                    "duration": e.get("duration"), "views": e.get("view_count"),
                    "live": e.get("live_status") == "is_live",
                })
            self.done.emit(rid, entries, "")
        except Exception as ex:
            self.done.emit(rid, [], str(ex))

    def load_thumb(self, vid):
        if not vid or vid in self.thumb_cache:
            return
        self.thumb_cache[vid] = None

        def run():
            try:
                req = urllib.request.Request(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg", headers={"User-Agent": "Mozilla/5.0"})
                data = urllib.request.urlopen(req, timeout=15).read()
                img = QImage.fromData(data)
                if not img.isNull():
                    self.thumb.emit(vid, img.scaled(192, 108, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()


def _fmt_views(v):
    if not v:
        return ""
    if v >= 100_000_000:
        return f"조회수 {v / 100_000_000:.1f}억회"
    if v >= 10_000:
        return f"조회수 {v / 10_000:.1f}만회"
    return f"조회수 {v:,}회"


class YouTubeDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.store = win.store
        self.setWindowTitle("유튜브")
        self.resize(760, 640)
        self.setModal(False)
        exe = win.ytdlp_path()
        self.fx = YtFetcher(exe)
        self.fx.done.connect(self._done)
        self.fx.thumb.connect(self._thumb)
        self.count = 30
        self.cur_req = 0
        self.target = None
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText("유튜브 검색어, 또는 영상·재생목록·채널 주소")
        self.q.returnPressed.connect(self.search)
        b = QPushButton("검색")
        b.clicked.connect(self.search)
        top.addWidget(self.q, 1)
        top.addWidget(b)
        v.addLayout(top)
        tabs = QHBoxLayout()
        self.tab_btns = []
        for key, label in YT_FEEDS:
            tb = QPushButton(label)
            tb.setObjectName("chip")
            tb.setCheckable(True)
            tb.clicked.connect(lambda _=False, k=key: self.open_feed(k))
            tabs.addWidget(tb)
            self.tab_btns.append((key, tb))
        tabs.addStretch(1)
        v.addLayout(tabs)
        acc = QHBoxLayout()
        self.acc_label = QLabel()
        self.acc_label.setObjectName("dim")
        ab = QPushButton("계정 연결…")
        ab.clicked.connect(self.connect_account)
        acc.addWidget(self.acc_label, 1)
        acc.addWidget(ab)
        v.addLayout(acc)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        v.addWidget(self.status)
        self.list = QListWidget()
        self.list.setIconSize(QSize(160, 90))
        self.list.setSpacing(2)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda it: self.play(it))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._ctx)
        v.addWidget(self.list, 1)
        bot = QHBoxLayout()
        hint = QLabel("더블클릭: 재생 · 우클릭: 재생목록에 추가 / 링크 복사")
        hint.setObjectName("dim")
        self.more = QPushButton("더 보기")
        self.more.clicked.connect(self.load_more)
        self.more.setEnabled(False)
        bot.addWidget(hint, 1)
        bot.addWidget(self.more)
        v.addLayout(bot)
        self._refresh_account()
        if not exe:
            self.status.setText("yt-dlp 가 없어 유튜브 기능을 쓸 수 없어요 (설치 버전에서 사용 가능)")

    def _refresh_account(self):
        c = self.store["yt_cookies"]
        if not c:
            self.acc_label.setText("계정: 연결 안 됨 — 검색은 그냥 되고, 구독·나중에 볼 동영상은 계정 연결이 필요해요")
        else:
            kind, _, val = c.partition(":")
            name = dict(BROWSERS).get(val, val) if kind == "browser" else os.path.basename(val)
            self.acc_label.setText(f"계정: {name} 에서 로그인 정보 사용 중")

    def _set_tab(self, key):
        for k, b in self.tab_btns:
            b.setChecked(k == key)
            self.win._set_chip(b, k == key)

    def search(self):
        t = self.q.text().strip()
        if not t:
            return
        self._set_tab("search")
        if re.match(r"https?://", t):
            if "list=" in t or "/@" in t or "/channel/" in t or "/c/" in t or "/user/" in t:
                self._load(t)
            else:
                self.win.open_paths([t])
            return
        self._load(f"ytsearch{self.count}:{t}")

    def open_feed(self, key):
        self._set_tab(key)
        if key == "search":
            self.q.setFocus()
            return
        if not self.store["yt_cookies"]:
            self.status.setText("이 목록은 계정 연결이 필요해요 → '계정 연결…'")
            self.list.clear()
            return
        self.count = 30
        self._load(key)

    def _load(self, target, keep=False):
        if not self.fx.exe:
            return
        self.target = target
        if not keep:
            self.count = 30
        self.status.setText("불러오는 중…")
        self.more.setEnabled(False)
        tgt = target
        if target.startswith("ytsearch"):
            tgt = re.sub(r"^ytsearch\d+:", f"ytsearch{self.count}:", target)
        self.cur_req = self.fx.fetch(tgt, self.count, self.store["yt_cookies"])

    def load_more(self):
        if self.target:
            self.count += 30
            self._load(self.target, keep=True)

    def _done(self, rid, entries, err):
        if rid != self.cur_req:
            return
        if err:
            low = err.lower()
            tip = ""
            if "cookie" in low or "dpapi" in low or "decrypt" in low or "could not copy" in low:
                tip = ("\n→ 브라우저에서 로그인 정보를 못 읽었어요. 브라우저를 완전히 닫고 다시 해 보거나, "
                       "'계정 연결 → cookies.txt 파일' 방법을 써 주세요.")
            self.status.setText(f"불러오기 실패: {err[:200]}{tip}")
            return
        self.list.clear()
        for e in entries:
            meta = []
            if e["channel"]:
                meta.append(e["channel"])
            if e["live"]:
                meta.append("🔴 라이브")
            elif e["duration"]:
                meta.append(W.fmt_time(e["duration"]))
            if e["views"]:
                meta.append(_fmt_views(e["views"]))
            it = QListWidgetItem(f"{e['title']}\n{'  ·  '.join(meta)}")
            it.setData(Qt.UserRole, e)
            it.setSizeHint(QSize(0, 98))
            img = self.fx.thumb_cache.get(e["id"])
            if img is not None:
                it.setIcon(QIcon(QPixmap.fromImage(img)))
            else:
                it.setIcon(self._placeholder())
                self.fx.load_thumb(e["id"])
            self.list.addItem(it)
        self.status.setText(f"{len(entries)}개")
        self.more.setEnabled(len(entries) >= self.count)

    def _placeholder(self):
        if not hasattr(self, "_ph"):
            pm = QPixmap(192, 108)
            pm.fill(QColor(40, 40, 50))
            self._ph = QIcon(pm)
        return self._ph

    def _thumb(self, vid, img):
        self.fx.thumb_cache[vid] = img
        for i in range(self.list.count()):
            it = self.list.item(i)
            e = it.data(Qt.UserRole)
            if e and e["id"] == vid:
                it.setIcon(QIcon(QPixmap.fromImage(img)))

    def play(self, it, append=False):
        e = it.data(Qt.UserRole)
        if not e:
            return
        if e["kind"] == "list":
            self.q.setText(e["url"])
            self._load(e["url"])
            return
        self.win.open_paths([e["url"]], append=append)
        if not append:
            self.win.raise_()

    def _ctx(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        e = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("재생", lambda: self.play(it))
        m.addAction("재생목록에 추가", lambda: self.play(it, append=True))
        sel = self.list.selectedItems()
        if len(sel) > 1:
            m.addAction(f"선택한 {len(sel)}개 재생목록에 추가",
                        lambda: self.win.open_paths([s.data(Qt.UserRole)["url"] for s in sel], append=True))
        m.addAction("링크 복사", lambda: QGuiApplication.clipboard().setText(e["url"]))
        m.addAction("브라우저에서 열기", lambda: webbrowser.open(e["url"]))
        m.exec(self.list.mapToGlobal(pos))

    def connect_account(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("유튜브 계정 연결")
        v = QVBoxLayout(dlg)
        t = QLabel("브라우저에 로그인된 유튜브 계정을 플레이어가 같이 쓰게 해요.\n"
                   "비밀번호는 묻지 않고, 로그인 정보는 이 PC 안에서만 쓰여요.\n\n"
                   "방법 1) 브라우저에서 바로 — 크롬·엣지·웨일은 보안 정책 때문에 브라우저를 닫아야 하거나 실패할 수 있어요.\n"
                   "방법 2) cookies.txt 파일 — 브라우저 확장 'Get cookies.txt LOCALLY'로 youtube.com 쿠키를 저장한 파일을 고르면\n"
                   "            가장 확실해요.")
        t.setWordWrap(True)
        v.addWidget(t)
        f = QFormLayout()
        cb = QComboBox()
        for k, name in BROWSERS:
            cb.addItem(name, k)
        row = QHBoxLayout()
        bb1 = QPushButton("이 브라우저로 연결")
        row.addWidget(cb, 1)
        row.addWidget(bb1)
        f.addRow("방법 1", row)
        bb2 = QPushButton("cookies.txt 파일 고르기…")
        f.addRow("방법 2", bb2)
        v.addLayout(f)
        h = QHBoxLayout()
        off = QPushButton("연결 끊기")
        close = QPushButton("닫기")
        h.addWidget(off)
        h.addStretch(1)
        h.addWidget(close)
        v.addLayout(h)

        def set_cfg(cfg):
            self.store["yt_cookies"] = cfg
            self.store.save()
            self.win.apply_ytdl_options()
            self._refresh_account()
            dlg.accept()
            if cfg:
                self.open_feed("https://www.youtube.com/feed/subscriptions")

        def pick_file():
            p, _ = QFileDialog.getOpenFileName(dlg, "cookies.txt 고르기", os.path.expanduser("~/Downloads"),
                                               "쿠키 파일 (*.txt);;모든 파일 (*.*)")
            if p:
                dst = os.path.join(data_dir(), "yt_cookies.txt")
                try:
                    shutil.copyfile(p, dst)
                except Exception:
                    dst = p
                set_cfg("file:" + dst)
        bb1.clicked.connect(lambda: set_cfg("browser:" + cb.currentData()))
        bb2.clicked.connect(pick_file)
        off.clicked.connect(lambda: set_cfg(""))
        close.clicked.connect(dlg.reject)
        dlg.exec()


# ------------------------------------------------------------------ 메인 창에 붙이는 부분
class ExtrasMixin2:
    def init_extras2(self):
        self.music_on = False
        self.yt_dlg = None
        self.apply_interpolation(quiet=True)
        self.apply_ytdl_options()
        self.apply_welcome_bg()

    # ---------- 공통
    def ytdlp_path(self):
        from player_app import find_tool
        return find_tool("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp") or shutil.which("yt-dlp")

    def apply_ytdl_options(self):
        opts = {"no-playlist": ""}
        cfg = self.store["yt_cookies"] or ""
        # 재생에는 cookies.txt 파일만 사용 (브라우저 직접 읽기는 브라우저가 켜져 있으면 실패해서 재생까지 막힐 수 있음)
        args = cookie_args(cfg) if cfg.startswith("file:") else []
        if args:
            opts[args[0].lstrip("-")] = args[1]
        if not self._set("ytdl-raw-options", opts):
            self._set("ytdl-raw-options", "no-playlist=")

    # ---------- 부드러운 움직임
    def apply_interpolation(self, quiet=False):
        on = bool(self.store["interpolation"])
        if on:
            self._set("video-sync", "display-resample")
            self._set("interpolation", True)
            self._set("tscale", "oversample")
        else:
            self._set("interpolation", False)
            self._set("video-sync", "audio")
        if not quiet:
            self.osd("부드러운 움직임 " + ("켬 (모니터 주사율에 맞춰 보간)" if on else "끔"), 2000)

    def toggle_interpolation(self):
        self.store["interpolation"] = not self.store["interpolation"]
        self.apply_interpolation()

    # ---------- 음악 모드
    def extras2_before_load(self):
        if self.music_on:
            self._set("lavfi-complex", "")
            self.music_on = False

    def extras2_file_loaded(self):
        kind = self.store["music_viz"]
        if kind == "off" or self.music_on:
            return
        tracks = self._get("track-list", []) or []
        vids = [t for t in tracks if t.get("type") == "video"]
        real = [t for t in vids if not (t.get("albumart") or t.get("image"))]
        auds = [t for t in tracks if t.get("type") == "audio"]
        if real or not auds:
            return
        aid = self._get("aid", None)
        if type(aid) is not int:
            sel = [t for t in auds if t.get("selected")]
            aid = (sel or auds)[0]["id"]
        cover = vids[0]["id"] if vids else None
        ok = self._set("lavfi-complex", viz_graph(kind, aid, cover, self.store["accent"]))
        if not ok and cover:
            ok = self._set("lavfi-complex", viz_graph(kind, aid, None, self.store["accent"]))
        if ok:
            self.music_on = True
            meta = self._get("metadata", {}) or {}
            lower = {str(k).lower(): v for k, v in meta.items()}
            title = lower.get("title") or os.path.basename(self.current or "")
            artist = lower.get("artist") or lower.get("album_artist") or ""
            self.osd(f"♪ {artist + ' - ' if artist else ''}{title}", 4000)
            if self.store["fit_window_on_open"]:
                self.pending_fit = True

    def set_music_viz(self, kind):
        self.store["music_viz"] = kind
        if self.music_on:
            if kind == "off":
                self._set("lavfi-complex", "")
                self.music_on = False
            else:
                self.music_on = False
                self.extras2_file_loaded()
        elif self.loaded:
            self.extras2_file_loaded()
        self.osd("음악 모드 화면: " + dict(MUSIC_LABELS).get(kind, kind))

    # ---------- 자막 번역
    def translate_current_sub(self):
        if not self.loaded or not self.current:
            return
        sid = self._get("sid", "no")
        tr = next((t for t in self.tracks("sub") if t.get("id") == sid), None)
        if tr is None:
            QMessageBox.information(self, "자막 번역", "번역할 자막을 먼저 켜 주세요.\n(자막 → 자막 트랙에서 고르기, 자막이 없으면 '자동 자막 만들기')")
            return
        codec = (tr.get("codec") or "").lower()
        ext_file = tr.get("external-filename")
        if not ext_file and codec not in TEXT_SUB_CODECS:
            QMessageBox.information(self, "자막 번역", f"이 자막({codec})은 그림으로 된 자막이라 번역할 수 없어요.\n"
                                                    "'자동 자막 만들기'로 한국어 자막을 만들어 보세요.")
            return
        if "://" in (ext_file or "") or ("://" in self.current and not ext_file):
            QMessageBox.information(self, "자막 번역", "인터넷 영상의 자막은 아직 번역할 수 없어요.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("자막 번역")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"번역할 자막: {self.track_label(tr)}"))
        f = QFormLayout()
        sl = QComboBox()
        for code, name in (("auto", "자동 감지"), ("en", "영어"), ("ja", "일본어"), ("zh-CN", "중국어"), ("es", "스페인어"),
                           ("fr", "프랑스어"), ("de", "독일어")):
            sl.addItem(name, code)
        tl = QComboBox()
        for code, name in (("ko", "한국어"), ("en", "영어"), ("ja", "일본어")):
            tl.addItem(name, code)
        both = QCheckBox("원문 자막도 같이 보기 (위: 원문 / 아래: 번역)")
        both.setChecked(True)
        f.addRow("원래 언어", sl)
        f.addRow("바꿀 언어", tl)
        v.addLayout(f)
        v.addWidget(both)
        note = QLabel("구글 무료 번역을 써요 (인터넷 필요). 번역된 자막은 영상 옆에 .ko.srt 로 저장돼요.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("번역하기")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if not dlg.exec():
            return
        src_lang, dst_lang, show_both = sl.currentData(), tl.currentData(), both.isChecked()
        video = self.current
        base = os.path.splitext(video)[0]
        out = f"{base}.translated.{dst_lang}.srt"
        if not os.access(os.path.dirname(video) or ".", os.W_OK):
            out = os.path.join(data_dir(), "subs", os.path.basename(out))
            os.makedirs(os.path.dirname(out), exist_ok=True)
        orig_id = tr.get("id")

        def work(job):
            job.report(2, "자막 읽는 중…")
            if ext_file:
                cues = read_sub_file(ext_file)
            else:
                cues = read_embedded_subs(video, int(tr.get("ff-index")), codec)
            if not cues:
                raise RuntimeError("자막 내용을 읽지 못했어요")
            res = translate_cues(cues, src_lang, dst_lang, lambda p, t: job.report(5 + p * 0.93, t))
            write_srt(res, out)
            return out

        def done(path):
            self.load_sub(path)
            if show_both and type(orig_id) is int:
                self._set("secondary-sid", orig_id)
            self.osd("자막 번역 완료!", 2500)
        self.run_job(F.Job(work), "자막 번역 중", done)

    # ---------- 유튜브
    def open_youtube(self):
        if self.yt_dlg is None:
            self.yt_dlg = YouTubeDialog(self)
        self.yt_dlg.show()
        self.yt_dlg.raise_()
        self.yt_dlg.activateWindow()
        self.yt_dlg.q.setFocus()

    # ---------- 시작 화면 꾸미기
    def apply_welcome_bg(self):
        p = self.store["welcome_bg"]
        self.welcome.set_background(p if p and os.path.isfile(p) else None, int(self.store["welcome_dim"]))

    def pick_welcome_bg(self):
        p, _ = QFileDialog.getOpenFileName(self, "시작 화면 그림 고르기", os.path.expanduser("~/Pictures"),
                                           "그림 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not p:
            return
        img = QImage(p)
        if img.isNull():
            QMessageBox.warning(self, "시작 화면 꾸미기", "그림을 열 수 없어요.")
            return
        if img.width() > 2560:
            img = img.scaledToWidth(2560, Qt.SmoothTransformation)
        dst = os.path.join(data_dir(), "welcome_bg.png")
        img.save(dst)
        self.store["welcome_bg"] = dst
        self.store.save()
        self.apply_welcome_bg()
        if self.loaded:
            self.osd("시작 화면 그림 바꿈 (정지하면 보여요)")

    def set_welcome_dim(self, d):
        self.store["welcome_dim"] = d
        self.apply_welcome_bg()

    def clear_welcome_bg(self):
        self.store["welcome_bg"] = ""
        self.apply_welcome_bg()

    def welcome_menu(self, parent):
        m = parent.addMenu("시작 화면 꾸미기")
        self._act(m, "배경 그림 고르기…", self.pick_welcome_bg)
        dm = m.addMenu("그림 어둡게")
        for d, label in ((0, "원본 그대로"), (30, "살짝"), (55, "보통"), (75, "많이")):
            self._act(dm, label, lambda d=d: self.set_welcome_dim(d), checked=int(self.store["welcome_dim"]) == d)
        self._act(m, "그림 지우기", self.clear_welcome_bg, enabled=bool(self.store["welcome_bg"]))
        return m

    def view_menu_extras2(self, vm):
        self._act(vm, "부드러운 움직임 (프레임 보간)", self.toggle_interpolation, checked=self.store["interpolation"])
        mm = vm.addMenu("음악 모드 화면")
        for k, label in MUSIC_LABELS:
            self._act(mm, label, lambda k=k: self.set_music_viz(k), checked=self.store["music_viz"] == k)
        self.welcome_menu(vm)


MUSIC_LABELS = [("cqt", "스펙트럼 막대"), ("waves", "파형"), ("spectrum", "스펙트로그램"), ("off", "끄기 (앨범 아트만)")]
