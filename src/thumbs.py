"""시크바 미리보기 썸네일 — PyAV로 키프레임 하나만 빠르게 디코딩."""
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

try:
    import av  # noqa
except Exception:  # PyAV 없으면 미리보기만 꺼짐
    av = None

THUMB_W = 192


class Thumbnailer(QObject):
    ready = Signal(str, int, QImage)   # path, bucket, image

    def __init__(self):
        super().__init__()
        self.path = None
        self.cache = {}
        self.want = None
        self.cv = threading.Condition()
        self.alive = True
        self.container = None
        self.stream = None
        self.bucket_sec = 2
        threading.Thread(target=self._run, daemon=True).start()

    def available(self):
        return av is not None

    def set_file(self, path, duration=None):
        with self.cv:
            if path == self.path:
                return
            self.path = path
            self.cache = {}
            self.want = None
            if duration and duration > 0:
                self.bucket_sec = max(1, int(duration / 300))
            else:
                self.bucket_sec = 2
            self.cv.notify()

    def bucket(self, sec):
        return int(sec // self.bucket_sec)

    def get(self, sec):
        """캐시에 있으면 바로 QImage, 없으면 None을 돌려주고 백그라운드 요청."""
        if av is None or not self.path:
            return None
        b = self.bucket(sec)
        img = self.cache.get(b)
        if img is not None:
            return img
        with self.cv:
            self.want = (self.path, b)
            self.cv.notify()
        return None

    def stop(self):
        with self.cv:
            self.alive = False
            self.cv.notify()

    # ---- worker ----
    def _open(self, path):
        self._close()
        if path.startswith(("http://", "https://", "rtmp://", "rtsp://", "ytdl://")):
            return False
        try:
            self.container = av.open(path, options={"probesize": "5000000"})
            vs = [s for s in self.container.streams if s.type == "video"
                  and not (s.disposition and getattr(s.disposition, "attached_pic", False))]
            if not vs:
                self._close()
                return False
            self.stream = vs[0]
            self.stream.thread_type = "AUTO"
            self.stream.codec_context.skip_frame = "NONKEY"
            self.opened_path = path
            return True
        except Exception:
            self._close()
            return False

    def _close(self):
        try:
            if self.container:
                self.container.close()
        except Exception:
            pass
        self.container = None
        self.stream = None
        self.opened_path = None

    def _decode(self, sec):
        st = self.stream
        tb = st.time_base
        target = int(sec / tb) if tb else int(sec * 1_000_000)
        if st.start_time is not None:
            target += st.start_time
        self.container.seek(target, stream=st, backward=True, any_frame=False)
        for frame in self.container.decode(st):
            w = THUMB_W
            h = max(2, int(round(frame.height * w / max(1, frame.width) * self._sar(frame) / 2)) * 2)
            rgb = frame.reformat(width=w, height=h, format="rgb24")
            arr = rgb.to_ndarray()
            img = QImage(arr.data, w, h, arr.strides[0], QImage.Format_RGB888).copy()
            return img
        return None

    @staticmethod
    def _sar(frame):
        try:
            sar = frame.sample_aspect_ratio
            if sar and sar.numerator and sar.denominator:
                return float(sar.denominator) / float(sar.numerator)
        except Exception:
            pass
        return 1.0

    def _run(self):
        self.opened_path = None
        while True:
            with self.cv:
                while self.alive and self.want is None:
                    self.cv.wait()
                if not self.alive:
                    self._close()
                    return
                path, b = self.want
                self.want = None
            if path != self.path:
                continue
            try:
                if self.opened_path != path and not self._open(path):
                    continue
                img = self._decode(b * self.bucket_sec + self.bucket_sec / 2)
                if img is not None and path == self.path:
                    self.cache[b] = img
                    if len(self.cache) > 400:
                        self.cache.pop(next(iter(self.cache)))
                    self.ready.emit(path, b, img)
            except Exception:
                self._close()
