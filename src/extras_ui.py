"""v2.1 기능을 메인 창에 붙이는 부분 (MainWindow 가 이 클래스를 같이 상속)."""
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import Qt, QTimer, QRect, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPixmap, QGuiApplication, QPen
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressDialog,
                               QMessageBox, QFileDialog, QStyledItemDelegate, QColorDialog, QFormLayout, QDialogButtonBox,
                               QStyle)

import features as F
import widgets as W
from store import data_dir

THEMES = [("#ff5c8a", "핑크"), ("#a07cff", "라벤더"), ("#4da3ff", "하늘"), ("#2ec4a6", "민트"),
          ("#ff9f43", "오렌지"), ("#ff4d5e", "레드"), ("#c8c8d2", "실버")]


def tools_dir():
    d = os.path.join(data_dir(), "tools")
    os.makedirs(d, exist_ok=True)
    return d


class PlaylistDelegate(QStyledItemDelegate):
    """재생목록 항목 아래 진행률 막대 + 다 본 영상 ✓ 표시."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        path = idx.data(Qt.UserRole)
        if not path:
            return
        r = opt.rect
        if path in self.store.watched:
            p.save()
            p.setPen(QColor("#7ee0a0"))
            p.drawText(QRect(r.right() - 26, r.top(), 22, r.height()), Qt.AlignCenter, "✓")
            p.restore()
        e = self.store.positions.get(path)
        if e and e.get("dur"):
            frac = max(0.0, min(1.0, e["pos"] / e["dur"]))
            p.save()
            y = r.bottom() - 3
            p.fillRect(QRect(r.left() + 6, y, r.width() - 12, 2), QColor(255, 255, 255, 40))
            p.fillRect(QRect(r.left() + 6, y, int((r.width() - 12) * frac), 2), W.ACCENT)
            p.restore()


class ExtrasMixin:
    # ------------------------------------------------------------ 초기화
    def init_extras(self):
        self.jobs = []
        self.remote = None
        self.amb_cur = QColor(0, 0, 0)
        self.amb_last = 0
        self.sil_fast = False
        self.sil_prev_speed = 1.0
        self.remote_last = 0
        self.plist.list.setItemDelegate(PlaylistDelegate(self.store, self.plist.list))
        self._def_scalers = {k: self._get(k) for k in ("scale", "cscale", "dscale", "deband")}
        if self.store["upscale"] != "off":
            QTimer.singleShot(0, lambda: self.set_upscale(self.store["upscale"], quiet=True))

    def extras_file_loaded(self):
        if self.store["ambient"] and self.current and "://" not in self.current:
            self.thumbs.set_file(self.current, self._get("duration", 0) or 0)

    # ------------------------------------------------------------ 주기 처리 (_poll 에서 호출)
    def extras_poll(self, now, pos, pause):
        s = self.store
        # 무음 구간 빨리 감기
        if s["skip_silence"] and self.loaded:
            md = self._get("af-metadata/sd", {}) or {}
            try:
                st_ = float(md.get("lavfi.silence_start", -1))
                en_ = float(md.get("lavfi.silence_end", -1))
            except (TypeError, ValueError):
                st_, en_ = -1, -1
            silent = st_ >= 0 and st_ > en_
            if silent and not self.sil_fast and not pause:
                self.sil_fast = True
                self.sil_prev_speed = self._get("speed", 1.0) or 1.0
                self._set("speed", max(3.0, self.sil_prev_speed))
                self.osd("무음 구간 빨리 감는 중 ▶▶", 800)
            elif not silent and self.sil_fast:
                self.sil_fast = False
                self._set("speed", self.sil_prev_speed)
        elif self.sil_fast:
            self.sil_fast = False
            self._set("speed", self.sil_prev_speed)
        # 앰비언트 모드
        if s["ambient"] and self.loaded and pos is not None:
            if now - self.amb_last > 0.4:
                self.amb_last = now
                img = self.thumbs.get(pos)
                if img is not None:
                    c = img.scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixelColor(0, 0)
                    h, sat, v, _ = c.getHsvF()
                    self.amb_target = QColor.fromHsvF(max(0, h), min(1.0, sat * 1.15), min(1.0, v * 0.42))
            t = getattr(self, "amb_target", None)
            if t is not None:
                cur = self.amb_cur
                nr = cur.redF() + (t.redF() - cur.redF()) * 0.12
                ng = cur.greenF() + (t.greenF() - cur.greenF()) * 0.12
                nb = cur.blueF() + (t.blueF() - cur.blueF()) * 0.12
                nc = QColor.fromRgbF(nr, ng, nb)
                if nc.name() != cur.name():
                    self._bg(nc.name())
                self.amb_cur = nc
        # 리모컨 상태
        if self.remote and now - self.remote_last > 0.4:
            self.remote_last = now
            title = ""
            if self.current:
                title = self._get("media-title", "") or os.path.basename(self.current)
            self.remote.state = {
                "title": title if self.loaded else "", "pos": pos or 0, "dur": self._get("duration", 0) or 0,
                "pause": bool(pause), "vol": self._get("volume", 0) or 0, "mute": bool(self._get("mute", False)),
                "speed": self._get("speed", 1.0) or 1.0,
            }

    def _bg(self, color):
        if not self._set("background-color", color):
            self._set("background", color)

    # ------------------------------------------------------------ 소리 필터 (무음 감지 붙이기)
    def extras_af(self, parts):
        if self.store["skip_silence"]:
            parts.append("@sd:lavfi=[silencedetect=n=-35dB:d=0.5]")
        return parts

    def toggle_skip_silence(self):
        self.store["skip_silence"] = not self.store["skip_silence"]
        self.apply_af()
        self.osd("무음 구간 빨리 감기 " + ("켬" if self.store["skip_silence"] else "끔"))

    def toggle_ambient(self):
        self.store["ambient"] = not self.store["ambient"]
        if self.store["ambient"]:
            self.extras_file_loaded()
            self.osd("앰비언트 모드 켬 — 영상 바깥 여백이 장면 색으로 물들어요", 2500)
        else:
            self.amb_target = None
            self.amb_cur = QColor(0, 0, 0)
            self._bg("#000000")
            self.osd("앰비언트 모드 끔")

    # ------------------------------------------------------------ 시청 기록
    def mark_watched(self, path):
        if path and "://" not in path:
            self.store.watched[path] = int(time.time())
            self.plist.list.viewport().update()

    def unmark_watched(self, path):
        self.store.watched.pop(path, None)
        self.store.positions.pop(path, None)
        self.plist.list.viewport().update()

    # ------------------------------------------------------------ 테마
    def set_theme(self, color):
        if not color:
            c = QColorDialog.getColor(QColor(self.store["accent"]), self, "테마 색 고르기")
            if not c.isValid():
                return
            color = c.name()
        self.store["accent"] = color
        W.ACCENT.setRgb(QColor(color).rgb())
        self.setStyleSheet(W.build_style(color))
        self._refresh_repeat_icon()
        self._highlight_playlist()
        self.bar.seek.update()
        self.osd("테마 색 변경")

    def theme_menu(self, parent):
        m = parent.addMenu("테마 색")
        for col, name in THEMES:
            self._act(m, name, lambda col=col: self.set_theme(col), checked=self.store["accent"].lower() == col)
        self._act(m, "직접 고르기…", lambda: self.set_theme(None))
        return m

    # ------------------------------------------------------------ 화질 올리기
    def set_upscale(self, mode, quiet=False):
        files = F.shader_files(tools_dir(), mode)
        if files is None:
            if quiet:
                return
            job = F.Job(F.fetch_shaders, tools_dir(), mode)
            self.run_job(job, "화질 필터 받는 중", lambda _: self.set_upscale(mode))
            return
        self.store["upscale"] = mode
        d = self._def_scalers
        self._set("glsl-shaders", "")
        for k in ("scale", "cscale", "dscale", "deband"):
            if d.get(k) is not None:
                self._set(k, d[k])
        if mode == "hq":
            self._set("scale", "ewa_lanczossharp")
            self._set("cscale", "ewa_lanczossharp")
            self._set("dscale", "mitchell")
            self._set("deband", True)
        elif files:
            ok = self._set("glsl-shaders", os.pathsep.join(files))
            if not ok:
                self.osd("화질 필터를 적용하지 못했어요 (그래픽 출력이 셰이더를 지원하지 않음)", 3000)
                return
        if not quiet:
            label = dict(F.UPSCALE_LABELS).get(mode, mode)
            self.osd(f"화질 올리기: {label}", 2000)

    def upscale_menu(self, parent):
        m = parent.addMenu("화질 올리기 (업스케일)")
        for k, label in F.UPSCALE_LABELS:
            self._act(m, label, lambda k=k: self.set_upscale(k), checked=self.store["upscale"] == k)
        return m

    # ------------------------------------------------------------ 백그라운드 작업 공통
    def run_job(self, job, title, on_done=None, modal=False):
        dlg = QProgressDialog(title, "취소", 0, 100, self)
        dlg.setWindowTitle(title)
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModal if modal else Qt.NonModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumWidth(380)
        dlg.show()
        self.jobs.append(job)

        def cancel():
            job.cancelled = True
            p = getattr(job, "proc", None)
            if p:
                try:
                    p.kill()
                except Exception:
                    pass

        def prog(pct, text):
            dlg.setValue(pct)
            if text:
                dlg.setLabelText(f"{title}\n{text}")

        def done(res):
            dlg.close()
            if job in self.jobs:
                self.jobs.remove(job)
            if on_done:
                on_done(res)

        def fail(msg):
            dlg.close()
            if job in self.jobs:
                self.jobs.remove(job)
            if msg != "취소됨":
                QMessageBox.warning(self, title, f"실패했어요: {msg}")
        dlg.canceled.connect(cancel)
        job.progress.connect(prog)
        job.done.connect(done)
        job.failed.connect(fail)
        job.start()
        return job

    # ------------------------------------------------------------ 구간 저장 / GIF / 장면 시트
    def _local_current(self):
        if not self.loaded or not self.current or "://" in self.current:
            self.osd("내 컴퓨터에 있는 영상에서만 쓸 수 있어요")
            return None
        return self.current

    def export_ab(self, kind):
        src = self._local_current()
        if not src:
            return
        a = self._get("ab-loop-a", "no")
        b = self._get("ab-loop-b", "no")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            QMessageBox.information(self, "구간 저장", "먼저 구간을 찍어 주세요.\n[ 키로 시작점, ] 키로 끝점을 정하면 돼요.")
            return
        if kind == "gif" and b - a > 30:
            QMessageBox.information(self, "GIF 만들기", "GIF는 30초까지만 만들 수 있어요. 앞 30초만 저장할게요.")
        base = os.path.splitext(os.path.basename(src))[0]
        name = f"{base}_{W.fmt_time(a).replace(':', '')}-{W.fmt_time(b).replace(':', '')}.{kind}"
        dst, _ = QFileDialog.getSaveFileName(self, "구간 저장", os.path.join(self._shot_dir(), name),
                                             "GIF (*.gif)" if kind == "gif" else "MP4 영상 (*.mp4)")
        if not dst:
            return
        job = F.Job(F.export_clip, src, float(a), float(b), dst, kind)
        self.run_job(job, "GIF 만드는 중" if kind == "gif" else "구간 저장 중",
                     lambda path: self._saved(path, "저장 완료"))

    def make_scene_sheet(self):
        src = self._local_current()
        if not src:
            return
        base = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(self._shot_dir(), f"{base}_장면시트.png")
        job = F.Job(F.scene_sheet, src, dst, 4, 4, 400, os.path.basename(src))
        self.run_job(job, "장면 미리보기 시트 만드는 중",
                     lambda path: (QDesktopServices.openUrl(QUrl.fromLocalFile(path)), self._saved(path, "장면 시트 저장")))

    def _saved(self, path, msg):
        self.osd(f"{msg}: {os.path.basename(path)}", 2500)
        if sys.platform == "win32":
            self.reveal(path)

    def ab_context_menu(self, pos=None):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        loaded = self.loaded
        self._act(m, "시작점 A 찍기  [", self.ab_set_a, enabled=loaded)
        self._act(m, "끝점 B 찍기  ]", self.ab_set_b, enabled=loaded)
        self._act(m, "해제  \\", self.ab_clear)
        m.addSeparator()
        self._act(m, "이 구간을 MP4로 저장…", lambda: self.export_ab("mp4"), enabled=loaded)
        self._act(m, "이 구간을 GIF로 저장…", lambda: self.export_ab("gif"), enabled=loaded)
        self._popup(m, self.bar.b_ab)

    def capture_extras(self, sm):
        loaded = self.loaded
        sm.addSeparator()
        self._act(sm, "A-B 구간을 MP4로 저장…", lambda: self.export_ab("mp4"), enabled=loaded)
        self._act(sm, "A-B 구간을 GIF로 저장…", lambda: self.export_ab("gif"), enabled=loaded)
        self._act(sm, "장면 미리보기 시트 만들기 (4x4)", self.make_scene_sheet, enabled=loaded)

    # ------------------------------------------------------------ 폰 리모컨
    def open_remote(self):
        if self.remote is None:
            try:
                self.remote = F.RemoteServer(self.store["accent"])
                self.remote.command.connect(self._remote_cmd)
                self.remote.start()
            except Exception as e:
                self.remote = None
                QMessageBox.warning(self, "폰 리모컨", f"리모컨을 켜지 못했어요: {e}")
                return
        url = self.remote.url()
        dlg = QDialog(self)
        dlg.setWindowTitle("폰 리모컨")
        v = QVBoxLayout(dlg)
        t = QLabel("폰 카메라로 QR을 찍거나 아래 주소를 폰 브라우저에 입력하세요.\n(폰과 PC가 같은 와이파이/공유기에 있어야 해요)")
        t.setWordWrap(True)
        v.addWidget(t)
        img = F.qr_image(url, 7)
        if img is not None:
            q = QLabel()
            q.setPixmap(QPixmap.fromImage(img))
            q.setAlignment(Qt.AlignCenter)
            v.addWidget(q)
        u = QLabel(f"<b>{url}</b>")
        u.setTextInteractionFlags(Qt.TextSelectableByMouse)
        u.setAlignment(Qt.AlignCenter)
        v.addWidget(u)
        note = QLabel("처음 켜면 Windows 방화벽 창이 뜰 수 있어요 → '개인 네트워크' 허용을 눌러 주세요.\n"
                      "주소에 비밀 코드가 들어 있어서 주소를 아는 기기만 조작할 수 있어요.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        h = QHBoxLayout()
        cp = QPushButton("주소 복사")
        cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(url))
        off = QPushButton("리모컨 끄기")
        off.clicked.connect(lambda: (self.stop_remote(), dlg.accept()))
        close = QPushButton("닫기 (켜 둔 채로)")
        close.clicked.connect(dlg.accept)
        h.addWidget(cp)
        h.addStretch(1)
        h.addWidget(off)
        h.addWidget(close)
        v.addLayout(h)
        dlg.exec()

    def stop_remote(self):
        if self.remote:
            self.remote.stop()
            self.remote = None
            self.osd("폰 리모컨 끔")

    def _remote_cmd(self, c, v):
        try:
            x = float(v) if v not in ("", None) else 0.0
        except ValueError:
            x = 0.0
        if c == "pause":
            self.toggle_pause()
        elif c == "seek":
            self.seek_rel(x)
        elif c == "goto":
            self.seek_abs(x)
        elif c == "prev":
            self.prev()
        elif c == "next":
            self.next(manual=True)
        elif c == "vol":
            self.change_volume(x)
        elif c == "mute":
            self.toggle_mute()
        elif c == "fullscreen":
            self.toggle_fullscreen()
        elif c == "speed":
            self.set_speed(1.0) if x == 0 else self.change_speed(x)
        elif c == "sub":
            self.toggle_sub()

    # ------------------------------------------------------------ 자동 자막
    def open_autosub(self):
        src = self._local_current()
        if not src:
            return
        if sys.platform != "win32":
            QMessageBox.information(self, "자동 자막", "자동 자막은 Windows 버전에서만 돼요.")
            return
        mdir = os.path.join(data_dir(), "models")
        dlg = QDialog(self)
        dlg.setWindowTitle("자동 자막 만들기")
        dlg.setMinimumWidth(460)
        v = QVBoxLayout(dlg)
        info = QLabel("영상의 말소리를 듣고 자막을 만들어요. 처음 한 번은 자막 엔진과 음성 인식 모델을 받아요.\n"
                      "PC 성능에 따라 영상 길이의 절반~2배 정도 걸려요. 만드는 동안 계속 봐도 돼요.")
        info.setWordWrap(True)
        v.addWidget(info)
        f = QFormLayout()
        cm = QComboBox()
        for k, (label, _) in F.WHISPER_MODELS.items():
            got = os.path.isfile(os.path.join(mdir, f"ggml-{k}.bin"))
            cm.addItem(f"{k} — {label}" + ("  ✓받음" if got else ""), k)
        cm.setCurrentIndex(1)
        cl = QComboBox()
        for code, name in (("ja", "일본어"), ("auto", "자동 감지"), ("en", "영어"), ("ko", "한국어"), ("zh", "중국어")):
            cl.addItem(name, code)
        ct = QComboBox()
        ct.addItem("한국어 자막으로 번역 (인터넷 번역 사용)", "ko")
        ct.addItem("말한 언어 그대로 자막", "orig")
        ct.addItem("영어 자막으로 번역 (오프라인)", "en")
        f.addRow("음성 인식 모델", cm)
        f.addRow("영상 속 언어", cl)
        f.addRow("만들 자막", ct)
        v.addLayout(f)
        note = QLabel("※ 한국어 번역은 음성 인식 결과를 구글 무료 번역으로 옮겨요 (인터넷 필요, 가끔 막힐 수 있어요).")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("자막 만들기")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if not dlg.exec():
            return
        model, lang, target = cm.currentData(), cl.currentData(), ct.currentData()
        base = os.path.splitext(src)[0]
        suffix = {"ko": "ko", "en": "en", "orig": lang if lang != "auto" else "orig"}[target]
        out = f"{base}.auto.{suffix}.srt"
        if not os.access(os.path.dirname(src) or ".", os.W_OK):
            out = os.path.join(data_dir(), "subs", os.path.basename(out))
            os.makedirs(os.path.dirname(out), exist_ok=True)

        def work(job):
            raw = out if target != "ko" else out.replace(".ko.srt", ".orig.srt")
            F.make_subtitles(job, tools_dir(), mdir, src, model, lang, target == "en", raw)
            if target == "ko":
                job.report(99, "한국어로 번역 중…")
                translate_srt(raw, out, "ko", lang if lang != "auto" else "auto")
            return out
        job = F.Job(work)
        self.run_job(job, "자동 자막 만드는 중", lambda path: self._autosub_done(src, path))

    def _autosub_done(self, src, path):
        if self.current == src and self.loaded:
            self.load_sub(path)
        self.osd(f"자막 완성: {os.path.basename(path)}", 3000)

    # ------------------------------------------------------------ 종료
    def extras_close(self):
        for j in list(self.jobs):
            j.cancelled = True
            p = getattr(j, "proc", None)
            if p:
                try:
                    p.kill()
                except Exception:
                    pass
        self.stop_remote()


# ------------------------------------------------------------------ SRT 번역
def _parse_srt(text):
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    out = []
    for b in blocks:
        lines = b.splitlines()
        if len(lines) >= 2 and "-->" in lines[1]:
            out.append([lines[0], lines[1], " ".join(l.strip() for l in lines[2:])])
        elif len(lines) >= 1 and "-->" in lines[0]:
            out.append([str(len(out) + 1), lines[0], " ".join(l.strip() for l in lines[1:])])
    return out


def _gtx(text, sl, tl):
    q = urllib.parse.urlencode({"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text})
    req = urllib.request.Request("https://translate.googleapis.com/translate_a/single?" + q,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in d[0] if seg and seg[0])


def translate_srt(src, dst, tl="ko", sl="auto"):
    with open(src, "r", encoding="utf-8", errors="replace") as fh:
        cues = _parse_srt(fh.read())
    texts = [c[2] for c in cues]
    result = [None] * len(texts)
    i = 0
    while i < len(texts):
        chunk, size, j = [], 0, i
        while j < len(texts) and size + len(texts[j]) < 3500 and len(chunk) < 80:
            chunk.append(texts[j].replace("\n", " "))
            size += len(texts[j]) + 1
            j += 1
        if not chunk:
            chunk, j = [texts[i]], i + 1
        try:
            tr = _gtx("\n".join(chunk), sl, tl).split("\n")
        except Exception:
            tr = []
        if len(tr) == len(chunk):
            result[i:j] = [t.strip() for t in tr]
        else:
            for k in range(i, j):  # 줄 수가 안 맞으면 한 줄씩
                try:
                    result[k] = _gtx(texts[k], sl, tl).strip()
                except Exception:
                    result[k] = texts[k]
                time.sleep(0.05)
        i = j
        time.sleep(0.2)
    with open(dst, "w", encoding="utf-8") as fh:
        for n, (c, t) in enumerate(zip(cues, result), 1):
            fh.write(f"{n}\n{c[1]}\n{t or c[2]}\n\n")
    return dst
