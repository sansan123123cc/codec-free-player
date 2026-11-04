"""단축키 표 — mpv 키 이름 기준. Qt 키 이벤트도 같은 이름으로 바꿔서 한 표로 처리한다."""
from PySide6.QtCore import Qt

# (mpv 키 목록, 동작 id, 설명, 분류)
SHORTCUTS = [
    (["SPACE", "k", "PLAYPAUSE"], "pause", "재생 / 일시정지", "재생"),
    (["ENTER", "KP_ENTER", "f"], "fullscreen", "전체 화면 켜기/끄기", "재생"),
    (["ESC"], "escape", "전체 화면 해제 (창 모드에서는 종료*)", "재생"),
    (["q"], "quit", "종료", "재생"),
    (["LEFT"], "seek_back", "뒤로 5초", "탐색"),
    (["RIGHT"], "seek_fwd", "앞으로 5초", "탐색"),
    (["Shift+LEFT"], "seek_back1", "뒤로 1초", "탐색"),
    (["Shift+RIGHT"], "seek_fwd1", "앞으로 1초", "탐색"),
    (["Ctrl+LEFT"], "seek_back_big", "뒤로 30초", "탐색"),
    (["Ctrl+RIGHT"], "seek_fwd_big", "앞으로 30초", "탐색"),
    (["j"], "seek_back10", "뒤로 10초 (유튜브식)", "탐색"),
    (["l"], "seek_fwd10", "앞으로 10초 (유튜브식)", "탐색"),
    ([",", "d"], "frame_back", "한 프레임 뒤로 (일시정지)", "탐색"),
    ([".", "g"], "frame_step", "한 프레임 앞으로 (일시정지)", "탐색"),
    (["HOME"], "seek_start", "처음으로", "탐색"),
    (["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], "seek_percent", "0~90% 지점으로 이동", "탐색"),
    (["Shift+PGUP"], "chapter_prev", "이전 챕터", "탐색"),
    (["Shift+PGDWN"], "chapter_next", "다음 챕터", "탐색"),
    (["PGUP", "PREV"], "prev", "이전 파일", "재생목록"),
    (["PGDWN", "NEXT"], "next", "다음 파일", "재생목록"),
    (["p", "F7"], "toggle_playlist", "재생목록 보이기/숨기기", "재생목록"),
    (["UP"], "vol_up", "볼륨 +5", "소리"),
    (["DOWN"], "vol_down", "볼륨 -5", "소리"),
    (["m", "MUTE"], "mute", "음소거", "소리"),
    (["a"], "cycle_audio", "오디오 트랙 바꾸기", "소리"),
    (["Ctrl+["], "audio_delay_minus", "소리 싱크 -0.1초", "소리"),
    (["Ctrl+]"], "audio_delay_plus", "소리 싱크 +0.1초", "소리"),
    (["Ctrl+\\"], "audio_delay_reset", "소리 싱크 초기화", "소리"),
    (["n"], "toggle_normalize", "음량 평준화 켜기/끄기", "소리"),
    (["c", ">"], "speed_up", "빠르게 (+0.1배 / 유튜브 Shift+.)", "속도"),
    (["x", "<"], "speed_down", "느리게", "속도"),
    (["z"], "speed_reset", "원래 속도", "속도"),
    (["["], "ab_a", "구간 반복 시작점(A)", "구간 반복"),
    (["]"], "ab_b", "구간 반복 끝점(B)", "구간 반복"),
    (["\\"], "ab_clear", "구간 반복 해제", "구간 반복"),
    (["s"], "cycle_sub", "자막 트랙 바꾸기", "자막"),
    (["v", "Alt+h"], "toggle_sub", "자막 보이기/숨기기", "자막"),
    (["Alt+LEFT"], "sub_delay_minus", "자막 싱크 -0.1초 (빨리)", "자막"),
    (["Alt+RIGHT"], "sub_delay_plus", "자막 싱크 +0.1초 (늦게)", "자막"),
    (["Alt+UP"], "sub_bigger", "자막 크게", "자막"),
    (["Alt+DOWN"], "sub_smaller", "자막 작게", "자막"),
    (["Alt+Shift+UP", "Shift+Alt+UP"], "sub_up", "자막 위로", "자막"),
    (["Alt+Shift+DOWN", "Shift+Alt+DOWN"], "sub_down", "자막 아래로", "자막"),
    (["Ctrl+e"], "screenshot", "화면 캡처 (파일로 저장)", "화면"),
    (["Ctrl+c"], "screenshot_clip", "화면 캡처를 클립보드로 복사", "화면"),
    (["r"], "rotate", "90° 회전", "화면"),
    (["Ctrl+0"], "zoom_reset", "확대·이동·회전 초기화", "화면"),
    (["Ctrl+=", "Ctrl+KP_ADD"], "zoom_in", "확대", "화면"),
    (["Ctrl+-", "Ctrl+KP_SUBTRACT"], "zoom_out", "축소", "화면"),
    (["Ctrl+t"], "on_top", "항상 위", "화면"),
    (["i"], "mini", "미니 플레이어(PIP) 켜기/끄기", "화면"),
    (["TAB"], "stats", "재생 통계 오버레이", "화면"),
    (["Ctrl+i"], "media_info", "미디어 정보", "화면"),
    (["Alt+1"], "size_50", "창 크기 50%", "화면"),
    (["Alt+2"], "size_100", "창 크기 100%", "화면"),
    (["Alt+3"], "size_150", "창 크기 150%", "화면"),
    (["Alt+4"], "size_200", "창 크기 200%", "화면"),
    (["b"], "bookmark", "북마크 추가", "기타"),
    (["Ctrl+o"], "open_file", "파일 열기", "기타"),
    (["Ctrl+u"], "open_url", "주소(URL) 열기 (유튜브 포함)", "기타"),
    (["Ctrl+v"], "paste", "클립보드의 주소/파일 열기", "기타"),
    (["Ctrl+y"], "youtube", "유튜브 검색·구독 목록", "기타"),
    (["F5"], "settings", "환경설정", "기타"),
    (["F1"], "help", "단축키 도움말", "기타"),
]

KEY_TO_ACTION = {}
for keys, act, _, _ in SHORTCUTS:
    for k in keys:
        KEY_TO_ACTION.setdefault(k, act)

MODS = ("Shift", "Ctrl", "Alt", "Meta")


def normalize(name):
    """'Alt+Shift+UP' 과 'Shift+Alt+UP' 을 같은 키로."""
    parts = name.split("+")
    # 'Ctrl++' 같은 경우 처리
    if name.endswith("++"):
        base = "+"
        mods = name[:-2].split("+") if len(name) > 2 else []
    else:
        base = parts[-1]
        mods = parts[:-1]
    mods = [m for m in MODS if m in mods]
    return "+".join(mods + [base])


NORMALIZED = {normalize(k): v for k, v in KEY_TO_ACTION.items()}

SPECIAL = {
    Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT", Qt.Key_Up: "UP", Qt.Key_Down: "DOWN",
    Qt.Key_Space: "SPACE", Qt.Key_Return: "ENTER", Qt.Key_Enter: "ENTER", Qt.Key_Escape: "ESC",
    Qt.Key_Tab: "TAB", Qt.Key_Backspace: "BS", Qt.Key_Delete: "DEL", Qt.Key_Home: "HOME",
    Qt.Key_End: "END", Qt.Key_PageUp: "PGUP", Qt.Key_PageDown: "PGDWN", Qt.Key_Insert: "INS",
    Qt.Key_MediaPlay: "PLAYPAUSE", Qt.Key_MediaTogglePlayPause: "PLAYPAUSE",
    Qt.Key_MediaPause: "PLAYPAUSE", Qt.Key_MediaNext: "NEXT", Qt.Key_MediaPrevious: "PREV",
    Qt.Key_VolumeMute: "MUTE",
}
for i in range(1, 13):
    SPECIAL[getattr(Qt, f"Key_F{i}")] = f"F{i}"


def qt_event_to_mpv(e):
    """QKeyEvent -> mpv 스타일 키 이름 (없으면 None)."""
    key = e.key()
    mods = e.modifiers()
    shift = bool(mods & Qt.ShiftModifier)
    ctrl = bool(mods & Qt.ControlModifier)
    alt = bool(mods & Qt.AltModifier)
    keypad = bool(mods & Qt.KeypadModifier)
    if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_unknown):
        return None
    use_shift = shift
    if key in SPECIAL:
        base = SPECIAL[key]
        if keypad and base == "ENTER":
            base = "KP_ENTER"
    elif Qt.Key_A <= key <= Qt.Key_Z:
        # 한글 입력 상태여도 물리 키 기준 영문으로
        base = chr(key).lower()
        if shift:
            base = base.upper()
            use_shift = False
    elif keypad and key == Qt.Key_Plus:
        base = "KP_ADD"
    elif keypad and key == Qt.Key_Minus:
        base = "KP_SUBTRACT"
    else:
        t = e.text()
        if t and t.isprintable() and not ctrl and not alt:
            base = t
            use_shift = False
        elif 0x20 < key < 0x7f:
            base = chr(key).lower()
            if key == Qt.Key_Plus:
                base = "="  # Ctrl++ (보통 Shift+=)
                use_shift = False
            if shift and base in "<>?":
                use_shift = False
        else:
            return None
    out = []
    if use_shift:
        out.append("Shift")
    if ctrl:
        out.append("Ctrl")
    if alt:
        out.append("Alt")
    out.append(base)
    return "+".join(out)


# 한글 두벌식 자판 (mpv 창에 포커스가 있을 때 한글 상태로 눌린 키도 동작하도록)
HANGUL = {
    "q": "ㅂ", "w": "ㅈ", "e": "ㄷ", "r": "ㄱ", "t": "ㅅ", "y": "ㅛ", "u": "ㅕ", "i": "ㅑ",
    "o": "ㅐ", "p": "ㅔ", "a": "ㅁ", "s": "ㄴ", "d": "ㅇ", "f": "ㄹ", "g": "ㅎ", "h": "ㅗ",
    "j": "ㅓ", "k": "ㅏ", "l": "ㅣ", "z": "ㅋ", "x": "ㅌ", "c": "ㅊ", "v": "ㅍ", "b": "ㅠ",
    "n": "ㅜ", "m": "ㅡ",
}


def mpv_binding_names():
    """mpv 창에 등록할 키 이름들 (한글 자모 포함)."""
    out = {}
    for k, act in KEY_TO_ACTION.items():
        out[k] = act
        if len(k) == 1 and k in HANGUL:
            out[HANGUL[k]] = act
    return out
