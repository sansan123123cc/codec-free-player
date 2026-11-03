; 코덱무관플레이어 설치 스크립트 (Inno Setup 6) — GitHub Actions 가 빌드할 때 사용
#define MyAppName "코덱무관플레이어"
#define MyAppExe "CodecFreePlayer.exe"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{7C1B6E4A-3D2F-4B8E-9A61-5F2C0D9E8A17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=CodecFreePlayer
DefaultDirName={localappdata}\Programs\CodecFreePlayer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CodecFreePlayer-setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsedUserAreasWarning=no

[Languages]
#ifexist "Korean.isl"
Name: "korean"; MessagesFile: "Korean.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"
Name: "assoc"; Description: "영상·음악 파일의 '연결 프로그램' 목록에 추가"
Name: "folderctx"; Description: "폴더 우클릭 메뉴에 '코덱무관플레이어로 재생' 추가"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\CodecFreePlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\CodecFreePlayer.media"; ValueType: string; ValueData: "미디어 파일 (코덱무관플레이어)"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\CodecFreePlayer.media\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\CodecFreePlayer.media\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Directory\shell\CodecFreePlayer"; ValueType: string; ValueData: "코덱무관플레이어로 재생"; Flags: uninsdeletekey; Tasks: folderctx
Root: HKA; Subkey: "Software\Classes\Directory\shell\CodecFreePlayer"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExe},0"; Tasks: folderctx
Root: HKA; Subkey: "Software\Classes\Directory\shell\CodecFreePlayer\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: folderctx
Root: HKA; Subkey: "Software\Classes\.264\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".264"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.265\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".265"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.3g2\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".3g2"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".aac"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ac3\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ac3"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.alac\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".alac"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ape\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ape"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.asf\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".asf"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.av1\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".av1"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.divx\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".divx"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.dts\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".dts"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.dv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".dv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.f4v\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".f4v"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".flv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.h264\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".h264"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.h265\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".h265"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.hevc\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".hevc"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ivf\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ivf"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m2ts\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m2ts"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m3u\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m3u"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m3u8\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m3u8"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mid\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mid"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.midi\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".midi"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mka\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mka"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mpeg\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mpeg"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mpg"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mts\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mts"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mxf\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mxf"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ogv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ogv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".opus"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.rm\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".rm"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.rmvb\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".rmvb"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ts"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.tta\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".tta"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.vob\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".vob"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wma"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wmv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.wv\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wv"; ValueData: ""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.y4m\OpenWithProgids"; ValueType: string; ValueName: "CodecFreePlayer.media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\Applications\CodecFreePlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".y4m"; ValueData: ""; Tasks: assoc

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "코덱무관플레이어 실행"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExe}"; Parameters: "--after-update"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im {#MyAppExe}"; Flags: runhidden; RunOnceId: "KillPlayer"
