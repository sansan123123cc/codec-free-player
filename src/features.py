"""v2.1 추가 기능: 구간 저장(mp4/GIF), 장면 미리보기 시트, 폰 리모컨, 자동 자막(whisper), 화질 셰이더."""
import json
import os
import random
import re
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal, Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont

try:
    import av
except Exception:
    av = None

UA = {"User-Agent": "CodecFreePlayer"}
from fractions import Fraction
A_TB = Fraction(1, 48000)
NOWIN = 0x08000000 if sys.platform == "win32" else 0


def _fmt(sec):
    sec = int(max(0, sec or 0))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def download(url, dst, progress=None, cancel=None):
    tmp = dst + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancel and cancel():
                raise RuntimeError("취소됨")
            b = r.read(512 * 1024)
            if not b:
                break
            f.write(b)
            got += len(b)
            if progress:
                progress(got, total)
    os.replace(tmp, dst)
    return dst


def is_cover(s):
    """앨범 아트(첨부 그림) 스트림인지. AV_DISPOSITION_ATTACHED_PIC = 0x400"""
    try:
        return bool(int(s.disposition) & 0x400)
    except Exception:
        return False


def _first_video(c):
    for s in c.streams.video:
        if not is_cover(s):
            return s
    return None


class Job(QObject):
    """백그라운드 작업 공통: progress(퍼센트, 글자), done(결과), failed(메시지)."""
    progress = Signal(int, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.cancelled = False
        self.fn = fn
        self.args = args

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        try:
            self.done.emit(self.fn(self, *self.args) or "")
        except Exception as e:
            self.failed.emit(str(e))

    def report(self, pct, text=""):
        if self.cancelled:
            raise RuntimeError("취소됨")
        self.progress.emit(int(max(0, min(100, pct))), text)


# ------------------------------------------------------------------ 구간 저장
def export_clip(job, src, a, b, dst, kind):
    """src 의 a~b 초 구간을 mp4(H.264+AAC) 또는 GIF 로 저장."""
    if av is None:
        raise RuntimeError("PyAV 없음")
    if b - a < 0.2:
        raise RuntimeError("구간이 너무 짧아요")
    if kind == "gif" and b - a > 30:
        b = a + 30
    inp = av.open(src)
    vs = _first_video(inp)
    if vs is None:
        raise RuntimeError("영상 트랙이 없어요")
    vs.thread_type = "AUTO"
    aus = inp.streams.audio[0] if (inp.streams.audio and kind == "mp4") else None
    W, H = vs.codec_context.width, vs.codec_context.height
    sar = vs.sample_aspect_ratio
    if sar and sar.numerator and sar.denominator and sar != 1:
        W = int(W * sar.numerator / sar.denominator)
    maxw = 480 if kind == "gif" else 1920
    if W > maxw:
        H = int(H * maxw / W)
        W = maxw
    W, H = W // 2 * 2, H // 2 * 2
    rate = vs.average_rate or vs.guessed_rate or 30
    fps = min(float(rate), 15.0 if kind == "gif" else 60.0)
    inp.seek(int(a / vs.time_base) + (vs.start_time or 0), stream=vs, backward=True, any_frame=False)

    frames_gif = []
    out = ov = oa = res = None
    if kind == "mp4":
        out = av.open(dst, "w")
        fr = Fraction(fps).limit_denominator(1001)
        ov = out.add_stream("libx264", rate=fr)
        ov.width, ov.height, ov.pix_fmt = W, H, "yuv420p"
        ov.options = {"crf": "20", "preset": "veryfast"}
        if aus is not None:
            oa = out.add_stream("aac", rate=48000)
            oa.layout = "stereo"
            res = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
    next_v = 0
    a_samples = 0
    a_started = False
    v_done = False
    a_done = aus is None
    streams = [vs] + ([aus] if aus is not None else [])
    for pkt in inp.demux(*streams):
        if v_done and a_done:
            break
        if pkt.dts is None and pkt.size == 0:
            continue
        for frame in pkt.decode():
            t = frame.time
            if t is None:
                continue
            if pkt.stream is vs:
                if v_done or t < a - 0.001:
                    continue
                if t > b:
                    v_done = True
                    continue
                idx = int(round((t - a) * fps))
                if idx < next_v:
                    continue
                img = frame.reformat(width=W, height=H, format="rgb24" if kind == "gif" else "yuv420p")
                if kind == "gif":
                    frames_gif.append(img.to_image())
                else:
                    img.pts = idx
                    img.time_base = 1 / fr
                    for p in ov.encode(img):
                        out.mux(p)
                next_v = idx + 1
                job.report((t - a) / (b - a) * 100, f"{_fmt(t - a)} / {_fmt(b - a)}")
            else:
                if a_done or t < a - 0.05:
                    continue
                if t > b:
                    a_done = True
                    continue
                for rf in res.resample(frame):
                    if not a_started:
                        a_started = True
                    rf.pts = a_samples
                    rf.time_base = A_TB
                    a_samples += rf.samples
                    for p in oa.encode(rf):
                        out.mux(p)
    inp.close()
    if kind == "mp4":
        for p in ov.encode():
            out.mux(p)
        if oa is not None:
            for rf in res.resample(None):
                rf.pts = a_samples
                rf.time_base = A_TB
                a_samples += rf.samples
                for p in oa.encode(rf):
                    out.mux(p)
            for p in oa.encode():
                out.mux(p)
        out.close()
    else:
        if not frames_gif:
            raise RuntimeError("프레임을 읽지 못했어요")
        job.report(99, "GIF 저장 중…")
        pal = [f.convert("P", palette=1, colors=256) for f in frames_gif]  # 1 = ADAPTIVE
        pal[0].save(dst, save_all=True, append_images=pal[1:], duration=int(1000 / fps), loop=0, optimize=True,
                    disposal=1)
    return dst


# ------------------------------------------------------------------ 장면 미리보기 시트
def scene_sheet(job, src, dst, cols=4, rows=4, cell_w=400, title=""):
    if av is None:
        raise RuntimeError("PyAV 없음")
    c = av.open(src)
    vs = _first_video(c)
    if vs is None:
        raise RuntimeError("영상 트랙이 없어요")
    vs.thread_type = "AUTO"
    dur = (c.duration / 1_000_000) if c.duration else (float(vs.duration * vs.time_base) if vs.duration else 0)
    if dur <= 0:
        raise RuntimeError("영상 길이를 알 수 없어요")
    w0, h0 = vs.codec_context.width, vs.codec_context.height
    sar = vs.sample_aspect_ratio
    disp_w = w0 * (sar.numerator / sar.denominator if sar and sar.numerator and sar.denominator else 1)
    cell_h = int(cell_w * h0 / max(1, disp_w)) // 2 * 2
    n = cols * rows
    shots = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        c.seek(int(t / vs.time_base) + (vs.start_time or 0), stream=vs, backward=True, any_frame=False)
        img = None
        for fr in c.decode(vs):
            if fr.time is not None and fr.time + 0.5 < t and i > 0:
                continue
            rgb = fr.reformat(width=cell_w, height=cell_h, format="rgb24").to_ndarray()
            img = QImage(rgb.data, cell_w, cell_h, rgb.strides[0], QImage.Format_RGB888).copy()
            t = fr.time if fr.time is not None else t
            break
        shots.append((t, img))
        job.report((i + 1) / n * 95, f"{i + 1}/{n}")
    size = os.path.getsize(src) if os.path.exists(src) else 0
    c.close()
    pad, head = 8, 86
    W = cols * cell_w + (cols + 1) * pad
    H = head + rows * cell_h + (rows + 1) * pad
    sheet = QImage(W, H, QImage.Format_RGB32)
    sheet.fill(QColor(18, 18, 24))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont("Malgun Gothic", 15, QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(pad * 2, 10, W - 4 * pad, 32), Qt.AlignLeft | Qt.AlignVCenter, title or os.path.basename(src))
    f2 = QFont("Malgun Gothic", 11)
    p.setFont(f2)
    p.setPen(QColor(190, 190, 200))
    info = f"길이 {_fmt(dur)}   ·   해상도 {w0}x{h0}   ·   크기 {size / 1048576:.1f} MB   ·   코덱 {vs.codec_context.name}"
    p.drawText(QRectF(pad * 2, 44, W - 4 * pad, 28), Qt.AlignLeft | Qt.AlignVCenter, info)
    ft = QFont("Consolas", 11, QFont.Bold)
    for i, (t, img) in enumerate(shots):
        x = pad + (i % cols) * (cell_w + pad)
        y = head + pad + (i // cols) * (cell_h + pad)
        if img is not None:
            p.drawImage(x, y, img)
        p.setFont(ft)
        label = _fmt(t)
        tw = p.fontMetrics().horizontalAdvance(label) + 12
        p.fillRect(QRectF(x + cell_w - tw - 6, y + cell_h - 26, tw, 20), QColor(0, 0, 0, 170))
        p.setPen(QColor("white"))
        p.drawText(QRectF(x + cell_w - tw - 6, y + cell_h - 26, tw, 20), Qt.AlignCenter, label)
    p.end()
    sheet.save(dst)
    job.report(100)
    return dst


# ------------------------------------------------------------------ 화질 셰이더
ANIME4K_URL = "https://github.com/bloc97/Anime4K/releases/download/v4.0.1/Anime4K_v4.0.zip"
FSR_URL = "https://gist.githubusercontent.com/agyild/82219c545228d70c5604f865ce0b0ce5/raw/FSR.glsl"
ANIME4K_SETS = {
    "anime_fast": ["Anime4K_Clamp_Highlights.glsl", "Anime4K_Restore_CNN_M.glsl", "Anime4K_Upscale_CNN_x2_M.glsl",
                   "Anime4K_AutoDownscalePre_x2.glsl", "Anime4K_AutoDownscalePre_x4.glsl", "Anime4K_Upscale_CNN_x2_S.glsl"],
    "anime_hq": ["Anime4K_Clamp_Highlights.glsl", "Anime4K_Restore_CNN_VL.glsl", "Anime4K_Upscale_CNN_x2_VL.glsl",
                 "Anime4K_AutoDownscalePre_x2.glsl", "Anime4K_AutoDownscalePre_x4.glsl", "Anime4K_Upscale_CNN_x2_M.glsl"],
}
UPSCALE_LABELS = [
    ("off", "끄기 (기본)"),
    ("hq", "고품질 확대 + 계단 현상 줄이기 (가벼움)"),
    ("fsr", "FSR 선명하게 (실사·게임)"),
    ("anime_fast", "애니 업스케일 Anime4K (빠름)"),
    ("anime_hq", "애니 업스케일 Anime4K (고품질 · 좋은 그래픽카드)"),
]


def shader_files(tools, mode):
    """필요한 셰이더 파일 경로 목록 (없으면 None)."""
    if mode == "fsr":
        p = os.path.join(tools, "shaders", "FSR.glsl")
        return [p] if os.path.isfile(p) else None
    if mode in ANIME4K_SETS:
        d = os.path.join(tools, "shaders", "anime4k")
        ps = [os.path.join(d, n) for n in ANIME4K_SETS[mode]]
        return ps if all(os.path.isfile(x) for x in ps) else None
    return []


def fetch_shaders(job, tools, mode):
    d = os.path.join(tools, "shaders")
    os.makedirs(d, exist_ok=True)
    if mode == "fsr":
        download(FSR_URL, os.path.join(d, "FSR.glsl"), lambda g, t: job.report(g * 100 / t if t else 50, "FSR 받는 중"))
    else:
        z = os.path.join(tempfile.gettempdir(), "anime4k.zip")
        download(ANIME4K_URL, z, lambda g, t: job.report(g * 100 / t if t else 50, "Anime4K 받는 중"))
        out = os.path.join(d, "anime4k")
        os.makedirs(out, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if n.lower().endswith(".glsl"):
                    with zf.open(n) as s, open(os.path.join(out, os.path.basename(n)), "wb") as t:
                        t.write(s.read())
    return mode


# ------------------------------------------------------------------ 자동 자막 (whisper.cpp)
WHISPER_ZIP = "https://github.com/ggml-org/whisper.cpp/releases/latest/download/whisper-bin-x64.zip"
WHISPER_MODELS = {
    "base": ("빠름 · 정확도 보통 (142MB)", "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"),
    "small": ("보통 · 추천 (466MB)", "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"),
    "medium": ("느림 · 가장 정확 (1.5GB)", "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"),
}


def whisper_exe(tools):
    d = os.path.join(tools, "whisper")
    for n in ("whisper-cli.exe", "main.exe", "whisper-cli"):
        if os.path.isfile(os.path.join(d, n)):
            return os.path.join(d, n)
    return None


def extract_audio_16k(job, src, wav, start_pct=0, span=20):
    import wave
    c = av.open(src)
    if not c.streams.audio:
        raise RuntimeError("소리 트랙이 없어요")
    st = c.streams.audio[0]
    dur = (c.duration / 1_000_000) if c.duration else 0
    res = av.AudioResampler(format="s16", layout="mono", rate=16000)
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        last = 0
        for fr in c.decode(st):
            for r in res.resample(fr):
                w.writeframes(bytes(r.planes[0])[: r.samples * 2])
            if dur and fr.time and fr.time - last > 5:
                last = fr.time
                job.report(start_pct + span * fr.time / dur, f"소리 추출 {int(fr.time * 100 / dur)}%")
        for r in res.resample(None):
            w.writeframes(bytes(r.planes[0])[: r.samples * 2])
    c.close()
    return dur


def make_subtitles(job, tools, models_dir, src, model, lang, translate, out_srt):
    os.makedirs(models_dir, exist_ok=True)
    exe = whisper_exe(tools)
    if not exe:
        z = os.path.join(tempfile.gettempdir(), "whisper-bin.zip")
        download(WHISPER_ZIP, z, lambda g, t: job.report(g * 10 / t if t else 5, "자막 엔진 받는 중"), lambda: job.cancelled)
        d = os.path.join(tools, "whisper")
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                base = os.path.basename(n)
                if base and base.lower().endswith((".exe", ".dll")):
                    with zf.open(n) as s, open(os.path.join(d, base), "wb") as t:
                        t.write(s.read())
        exe = whisper_exe(tools)
        if not exe:
            raise RuntimeError("자막 엔진 파일을 찾지 못했어요")
    mpath = os.path.join(models_dir, f"ggml-{model}.bin")
    if not os.path.isfile(mpath):
        download(WHISPER_MODELS[model][1], mpath,
                 lambda g, t: job.report(10 + (g * 30 / t if t else 10), f"음성 인식 모델 받는 중 {g / 1048576:.0f}MB"),
                 lambda: job.cancelled)
    wav = os.path.join(tempfile.gettempdir(), "cfp_whisper.wav")
    dur = extract_audio_16k(job, src, wav, 40, 10)
    base = os.path.splitext(out_srt)[0]
    threads = max(2, (os.cpu_count() or 4) - 1)
    args = [exe, "-m", mpath, "-f", wav, "-osrt", "-of", base, "-pp", "-t", str(threads)]
    args += ["-l", lang or "auto"]
    if translate:
        args.append("-tr")
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NOWIN,
                         cwd=os.path.dirname(exe), text=True, encoding="utf-8", errors="replace")
    job.proc = p
    last_t = 0.0
    for line in p.stdout:
        if job.cancelled:
            p.kill()
            raise RuntimeError("취소됨")
        m = re.search(r"progress\s*=\s*(\d+)%", line)
        if m:
            job.report(50 + int(m.group(1)) / 2, f"음성 인식 {m.group(1)}%")
            continue
        m = re.search(r"\[(\d+):(\d+):(\d+)\.\d+\s*-->\s*(\d+):(\d+):(\d+)", line)
        if m and dur:
            h, mi, s = int(m.group(4)), int(m.group(5)), int(m.group(6))
            last_t = h * 3600 + mi * 60 + s
            job.report(50 + 50 * last_t / dur, f"음성 인식 {_fmt(last_t)} / {_fmt(dur)}")
    p.wait()
    try:
        os.remove(wav)
    except Exception:
        pass
    if p.returncode != 0 or not os.path.isfile(base + ".srt"):
        raise RuntimeError(f"음성 인식 실패 (코드 {p.returncode})")
    if base + ".srt" != out_srt:
        os.replace(base + ".srt", out_srt)
    return out_srt


# ------------------------------------------------------------------ 폰 리모컨
REMOTE_HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>코덱무관플레이어 리모컨</title><style>
:root{--a:ACCENT}*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#121218;color:#eee;font-family:-apple-system,'Malgun Gothic',sans-serif;padding:16px;user-select:none}
h1{font-size:15px;color:#aaa;margin:0 0 6px;font-weight:600}#t{font-size:18px;font-weight:700;margin-bottom:12px;word-break:break-all}
#bar{width:100%;accent-color:var(--a)}#tm{display:flex;justify-content:space-between;color:#aaa;font-size:13px;margin:2px 0 16px}
.g{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px}
button{background:#23232c;border:1px solid #33333d;color:#fff;border-radius:14px;padding:18px 0;font-size:17px;font-weight:600}
button:active{background:var(--a)}#pp{background:var(--a);border-color:var(--a);font-size:26px}
.s{font-size:14px;padding:14px 0}</style></head><body>
<h1>코덱무관플레이어 리모컨</h1><div id="t">-</div>
<input id="bar" type="range" min="0" max="1000" value="0"><div id="tm"><span id="p">0:00</span><span id="v">볼륨 -</span><span id="d">0:00</span></div>
<div class="g"><button onclick="c('seek',-10)">⟲ 10초</button><button id="pp" onclick="c('pause')">⏯</button><button onclick="c('seek',10)">10초 ⟳</button></div>
<div class="g"><button onclick="c('prev')">⏮ 이전</button><button onclick="c('fullscreen')">⛶ 전체화면</button><button onclick="c('next')">다음 ⏭</button></div>
<div class="g"><button onclick="c('vol',-5)">🔉 -</button><button onclick="c('mute')">🔇 음소거</button><button onclick="c('vol',5)">🔊 +</button></div>
<div class="g"><button class="s" onclick="c('speed',-0.25)">느리게</button><button class="s" id="sp" onclick="c('speed',0)">1.0x</button><button class="s" onclick="c('speed',0.25)">빠르게</button></div>
<div class="g"><button class="s" onclick="c('seek',-60)">-1분</button><button class="s" onclick="c('sub')">자막 켜기/끄기</button><button class="s" onclick="c('seek',60)">+1분</button></div>
<script>
const K=new URLSearchParams(location.search).get('k');let drag=false,dur=0;
function f(s){s=Math.max(0,s|0);let h=s/3600|0,m=(s%3600)/60|0,x=s%60;return(h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')}
function c(cmd,v){fetch('/api/cmd?k='+K+'&c='+cmd+(v!==undefined?'&v='+v:'')).then(()=>setTimeout(u,150))}
const bar=document.getElementById('bar');bar.oninput=()=>{drag=true;document.getElementById('p').textContent=f(bar.value/1000*dur)};
bar.onchange=()=>{c('goto',bar.value/1000*dur);drag=false};
function u(){fetch('/api/state?k='+K).then(r=>r.json()).then(s=>{document.getElementById('t').textContent=s.title||'(재생 중인 영상 없음)';dur=s.dur||0;
if(!drag){bar.value=dur?s.pos/dur*1000:0;document.getElementById('p').textContent=f(s.pos)}document.getElementById('d').textContent=f(dur);
document.getElementById('v').textContent=s.mute?'음소거':'볼륨 '+Math.round(s.vol)+'%';document.getElementById('pp').textContent=s.pause?'▶':'⏸';
document.getElementById('sp').textContent=(+s.speed).toFixed(2).replace(/0$/,'')+'x'}).catch(()=>{})}
u();setInterval(u,1000);
</script></body></html>"""


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class RemoteServer(QObject):
    command = Signal(str, str)

    def __init__(self, accent="#ff5c8a"):
        super().__init__()
        self.state = {}
        self.token = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        self.httpd = None
        self.port = None
        self.accent = accent

    def start(self):
        owner = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                b = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if q.get("k", [""])[0] != owner.token:
                    return self._send(403, "잘못된 주소예요. 플레이어에 보이는 QR/주소로 다시 접속해 주세요.", "text/plain; charset=utf-8")
                if u.path == "/":
                    return self._send(200, REMOTE_HTML.replace("ACCENT", owner.accent), "text/html; charset=utf-8")
                if u.path == "/api/state":
                    return self._send(200, json.dumps(owner.state, ensure_ascii=False), "application/json; charset=utf-8")
                if u.path == "/api/cmd":
                    owner.command.emit(q.get("c", [""])[0], q.get("v", [""])[0])
                    return self._send(200, "{}", "application/json")
                self._send(404, "not found", "text/plain")

        for port in range(8765, 8785):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", port), H)
                self.port = port
                break
            except OSError:
                continue
        if not self.httpd:
            raise RuntimeError("빈 포트를 찾지 못했어요")
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.url()

    def url(self):
        return f"http://{lan_ip()}:{self.port}/?k={self.token}"

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None


def qr_image(text, scale=8):
    try:
        import qrcode
    except Exception:
        return None
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    mat = q.get_matrix()
    n = len(mat)
    img = QImage(n * scale, n * scale, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    for y, row in enumerate(mat):
        for x, v in enumerate(row):
            if v:
                p.fillRect(x * scale, y * scale, scale, scale, QColor("black"))
    p.end()
    return img
