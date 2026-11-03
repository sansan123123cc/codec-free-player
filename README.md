# 코덱무관플레이어

코덱 설치 없이 거의 모든 영상을 재생하는 윈도우 동영상 플레이어 (mpv 엔진 + Qt 화면).

- 설치: [Releases](../../releases/latest) 에서 `CodecFreePlayer-setup-x.y.z.exe` 받아 실행
- 업데이트: 플레이어를 켜면 새 버전을 확인해서 자동으로 설치해요
- 단축키: 플레이어에서 F1

## 개발
```
pip install -r requirements.txt
python src/main.py
```
(윈도우에서는 `libmpv-2.dll` 을 src 폴더나 PATH 에 두기)

`main` 에 올라가면 GitHub Actions 가 설치 파일을 만들어 릴리스에 올립니다. 버전은 `src/version.py`.
