"""코덱무관플레이어 실행 진입점."""
import json
import os
import sys
import traceback


def _setup_paths():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    extra = [base, getattr(sys, "_MEIPASS", base)]
    os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])
    if hasattr(os, "add_dll_directory"):
        for d in extra:
            try:
                os.add_dll_directory(d)
            except Exception:
                pass


_setup_paths()

from PySide6.QtCore import Qt, QLocale  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from store import Store  # noqa: E402
from version import APP_ID, APP_NAME  # noqa: E402

SERVER = f"{APP_ID}-{os.environ.get('USERNAME') or os.environ.get('USER') or 'user'}"


def send_to_running(args):
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(args).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CodecFreePlayer.App")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    QLocale.setDefault(QLocale(QLocale.Korean, QLocale.SouthKorea))
    f = QFont("Malgun Gothic")
    f.setPointSize(10)
    app.setFont(f)

    args = [a for a in sys.argv[1:]]
    after_update = "--after-update" in args
    files = [a for a in args if not a.startswith("--")]
    store = Store()

    if "--selftest" in args:
        store["check_updates"] = False
    if store["single_instance"] and files and send_to_running(args):
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(SERVER)
    server.listen(SERVER)

    # mpv 는 숫자 로케일이 C 여야 함
    import locale
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass

    try:
        from player_app import MainWindow
        win = MainWindow(store, files, after_update=after_update)
    except Exception as e:
        if "--selftest" in args:
            from store import data_dir
            with open(os.path.join(data_dir(), "selftest.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"FAIL {e}\n{traceback.format_exc()}")
            return 2
        QMessageBox.critical(None, APP_NAME, f"플레이어를 시작하지 못했어요.\n\n{e}\n\n{traceback.format_exc()[-1500:]}")
        return 1

    def on_conn():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()

            def read(c=c):
                try:
                    data = bytes(c.readAll()).decode("utf-8")
                    if data:
                        win.handle_message(json.loads(data))
                except Exception:
                    pass
            if c.waitForReadyRead(500):
                read()
            else:
                c.readyRead.connect(read)
    server.newConnection.connect(on_conn)

    win.show()
    if "--selftest" in args:
        # 빌드 검증용: mpv 엔진·썸네일 모듈이 제대로 실려 있는지 확인하고 종료
        from PySide6.QtCore import QTimer

        def finish():
            from store import data_dir
            try:
                ver = win.m._get_property("mpv-version")
                ok = bool(ver) and win.thumbs.available()
                msg = f"{'OK' if ok else 'FAIL'} mpv={ver} av={win.thumbs.available()}"
            except Exception as ex:
                ok, msg = False, f"FAIL {ex}"
            with open(os.path.join(data_dir(), "selftest.txt"), "w", encoding="utf-8") as fh:
                fh.write(msg)
            win.close()
            app.exit(0 if ok else 3)
        QTimer.singleShot(2500, finish)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        try:
            from store import data_dir
            with open(os.path.join(data_dir(), "crash.log"), "a", encoding="utf-8") as fh:
                fh.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        raise
