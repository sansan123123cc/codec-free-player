"""설정 · 이어보기 기록 · 최근 파일 저장소 (JSON, %APPDATA%\\CodecFreePlayer)."""
import json
import os
import sys
import threading
import time

from version import APP_ID


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, APP_ID)
    os.makedirs(d, exist_ok=True)
    return d


def default_shot_dir():
    pics = os.path.join(os.path.expanduser("~"), "Pictures")
    if not os.path.isdir(pics):
        pics = os.path.expanduser("~")
    return os.path.join(pics, "코덱무관플레이어")


DEFAULTS = {
    # 일반
    "single_instance": True,
    "resume_mode": "auto",          # auto | ask | off
    "auto_folder_playlist": True,   # 파일 하나 열면 같은 폴더 영상들을 재생목록에 추가
    "autoplay_next": True,
    "click_to_pause": True,
    "wheel_action": "volume",       # volume | seek
    "esc_quits": True,              # 전체화면 아닐 때 Esc = 종료 (예전 버전 동작)
    "fit_window_on_open": True,
    "remember_window": True,
    "check_updates": True,
    "always_on_top": "never",       # never | always | playing
    "repeat": "off",                # off | one | all
    "shuffle": False,
    "seek_small": 5,
    "seek_large": 30,
    # 영상
    "hwdec": True,
    "deinterlace": "auto",
    "shot_dir": "",
    "shot_format": "png",
    "shot_with_subs": True,
    "thumbnails": True,
    "ytdl_quality": "1080",         # best | 2160 | 1440 | 1080 | 720 | 480
    # 소리
    "volume": 80,
    "muted": False,
    "volume_max": 200,
    "audio_preset": "off",
    "audio_channels": "auto",
    "eq": [0] * 10,
    "audio_lang": "ko,kor,kr,ja,jpn,en,eng",
    # 자막
    "sub_auto": True,
    "sub_lang": "ko,kor,kr,en,eng",
    "sub_font": "Malgun Gothic",
    "sub_size": 46,
    "sub_color": "#FFFFFF",
    "sub_border_color": "#000000",
    "sub_border": 3.0,
    "sub_bold": True,
    "sub_back_box": False,
    "sub_pos": 100,
    # 창
    "geometry": None,
    "playlist_visible": False,
    "playlist_width": 280,
}


class Store:
    def __init__(self):
        self.dir = data_dir()
        self.path_settings = os.path.join(self.dir, "settings.json")
        self.path_history = os.path.join(self.dir, "history.json")
        self.lock = threading.Lock()
        self.s = dict(DEFAULTS)
        self.s.update(self._load(self.path_settings, {}))
        h = self._load(self.path_history, {})
        self.positions = h.get("positions", {})   # path -> {pos, dur, t}
        self.recent = h.get("recent", [])         # [path]
        self.bookmarks = h.get("bookmarks", {})   # path -> [[sec, label]]
        self.session = h.get("session", {})       # 마지막 재생 상태 (업데이트 후 복원용)

    @staticmethod
    def _load(path, fallback):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return fallback

    @staticmethod
    def _save(path, data):
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            pass

    def __getitem__(self, k):
        return self.s.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.s[k] = v

    def save(self):
        with self.lock:
            self._save(self.path_settings, self.s)
            self._save(self.path_history, {
                "positions": self.positions,
                "recent": self.recent,
                "bookmarks": self.bookmarks,
                "session": self.session,
            })

    # ---- 이어보기 ----
    def get_resume(self, path):
        e = self.positions.get(path)
        return e.get("pos") if e else None

    def set_resume(self, path, pos, dur):
        if not path:
            return
        if pos is None or dur is None or dur <= 0:
            return
        if pos < 10 or pos > dur - 15:
            self.positions.pop(path, None)
            return
        self.positions[path] = {"pos": round(pos, 2), "dur": round(dur, 2), "t": int(time.time())}
        if len(self.positions) > 800:
            old = sorted(self.positions.items(), key=lambda kv: kv[1].get("t", 0))
            for k, _ in old[: len(self.positions) - 800]:
                self.positions.pop(k, None)

    # ---- 최근 파일 ----
    def add_recent(self, path):
        if path in self.recent:
            self.recent.remove(path)
        self.recent.insert(0, path)
        del self.recent[25:]

    # ---- 북마크 ----
    def get_bookmarks(self, path):
        return sorted(self.bookmarks.get(path, []), key=lambda b: b[0])

    def add_bookmark(self, path, sec, label):
        lst = self.bookmarks.setdefault(path, [])
        lst.append([round(sec, 2), label])

    def remove_bookmark(self, path, idx):
        lst = self.get_bookmarks(path)
        if 0 <= idx < len(lst):
            lst.pop(idx)
            self.bookmarks[path] = lst
            if not lst:
                self.bookmarks.pop(path, None)
