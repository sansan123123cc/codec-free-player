"""GitHub 릴리스 기반 자동 업데이트.
켤 때 releases/latest 를 확인 → 새 버전이면 설치 파일을 받아 조용히 설치 → 플레이어 다시 실행.
설치 프로그램(Inno Setup)은 사용자 폴더에 설치되므로 관리자 권한 창이 뜨지 않는다."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from version import VERSION, GITHUB_OWNER, GITHUB_REPO

UA = {"User-Agent": "CodecFreePlayer-Updater", "Accept": "application/vnd.github+json"}


def parse_ver(s):
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


class Updater(QObject):
    found = Signal(str, str, str, int)    # version, notes, url, size
    none = Signal(str)                    # message (수동 확인일 때만 사용)
    progress = Signal(int, int)
    downloaded = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.cancel = False

    def check(self, manual=False):
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual):
        try:
            if GITHUB_OWNER in ("", "OWNER"):
                raise RuntimeError("업데이트 저장소가 아직 설정되지 않았어요")
            url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8"))
            tag = d.get("tag_name", "")
            if parse_ver(tag) <= parse_ver(VERSION):
                if manual:
                    self.none.emit(f"최신 버전이에요 (현재 {VERSION})")
                return
            asset = None
            for a in d.get("assets", []):
                n = a.get("name", "").lower()
                if n.endswith(".exe") and "setup" in n:
                    asset = a
                    break
            if not asset:
                if manual:
                    self.none.emit(f"새 버전 {tag} 이 있지만 설치 파일이 아직 올라오지 않았어요")
                return
            self.found.emit(tag.lstrip("v"), d.get("body") or "", asset["browser_download_url"], int(asset.get("size", 0)))
        except Exception as e:
            if manual:
                self.failed.emit(f"업데이트 확인 실패: {e}")

    def download(self, url, size):
        self.cancel = False
        threading.Thread(target=self._download, args=(url, size), daemon=True).start()

    def _download(self, url, size):
        try:
            dst = os.path.join(tempfile.gettempdir(), "CodecFreePlayer-setup.exe")
            req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
            with urllib.request.urlopen(req, timeout=30) as r, open(dst + ".part", "wb") as f:
                total = int(r.headers.get("Content-Length") or size or 0)
                got = 0
                while True:
                    if self.cancel:
                        raise RuntimeError("취소됨")
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            if total and got < total:
                raise RuntimeError("다운로드가 중간에 끊겼어요")
            if os.path.exists(dst):
                os.remove(dst)
            os.replace(dst + ".part", dst)
            self.downloaded.emit(dst)
        except Exception as e:
            self.failed.emit(f"업데이트 다운로드 실패: {e}")


def run_installer(path):
    """설치 프로그램을 조용히 실행. 설치가 끝나면 설치 프로그램이 플레이어를 다시 켠다(--after-update)."""
    args = [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS"]
    if sys.platform == "win32":
        DETACHED = 0x00000008
        NEWGROUP = 0x00000200
        subprocess.Popen(args, creationflags=DETACHED | NEWGROUP, close_fds=True)
    else:
        subprocess.Popen(args)


class ToolFetcher(QObject):
    """유튜브용 보조 도구(Deno) 같은 파일을 한 번 받아 두는 다운로더."""
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def fetch_zip_member(self, url, member, dst_dir):
        threading.Thread(target=self._run, args=(url, member, dst_dir), daemon=True).start()

    def _run(self, url, member, dst_dir):
        import zipfile
        try:
            os.makedirs(dst_dir, exist_ok=True)
            tmp = os.path.join(tempfile.gettempdir(), "cfp_tool.zip")
            req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            with zipfile.ZipFile(tmp) as z:
                name = next(n for n in z.namelist() if n.lower().endswith(member.lower()))
                out = os.path.join(dst_dir, os.path.basename(name))
                with z.open(name) as src, open(out + ".part", "wb") as dst:
                    while True:
                        b = src.read(1 << 20)
                        if not b:
                            break
                        dst.write(b)
                os.replace(out + ".part", out)
            try:
                os.remove(tmp)
            except Exception:
                pass
            self.done.emit(out)
        except Exception as e:
            self.failed.emit(str(e))


def update_ytdlp_async(exe, stamp_file):
    """yt-dlp 를 하루 한 번 스스로 최신화 (유튜브가 자주 바뀌어서)."""
    import time as _t

    def run():
        try:
            if os.path.exists(stamp_file) and _t.time() - os.path.getmtime(stamp_file) < 86400:
                return
            with open(stamp_file, "w") as f:
                f.write(str(_t.time()))
            flags = 0x08000000 if sys.platform == "win32" else 0
            subprocess.run([exe, "-U"], timeout=180, capture_output=True, creationflags=flags)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()
