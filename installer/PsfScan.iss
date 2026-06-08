; installer/PsfScan.iss — Inno Setup 6 (with ISPP)
; Compile on Windows:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\PsfScan.iss
; Output:
;   release\PsfScan-Setup-<MyAppVersion>.exe
;
; If installer\vendored\<MvsExeName> exists at compile time, it is bundled and
; silently invoked during install. Otherwise the installer skips the MVS SDK
; entry entirely (used by GitHub Actions builds where the vendor binary cannot
; be shipped).

#define MyAppName        "PSF Scan"
#define MyAppVersion "1.1.6"
#define MyAppPublisher   "PSF Scan"
#define MyAppExeName     "PsfScan.exe"
#define MvsExeName       "MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe"

#ifexist "vendored\" + MvsExeName
  #define HAS_MVS_SDK
#endif

[Setup]
; Stable AppId — never change between versions; controls upgrade detection.
AppId={{4F7B2D9E-3A1C-4F0D-9C7A-2E1B6D5F8A3C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PsfScan
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=PsfScan-Setup-{#MyAppVersion}
Compression=lzma2/ultra
SolidCompression=yes
MinVersion=10.0.17763
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no
DisableProgramGroupPage=yes
SetupIconFile=resources\installer-icon.ico
LicenseFile=resources\license.rtf
WizardStyle=modern
ShowLanguageDialog=auto
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
; ChineseSimplified.isl is shipped in repo because choco's stock Inno Setup
; install does NOT include the "Unofficial" language pack.
Name: "chs"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "en";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
#ifdef HAS_MVS_SDK
Name: "mvssdk"; Description: "同时安装 MVS SDK 运行时（连接海康相机必需）"; GroupDescription: "运行时组件:"
#endif

[Files]
; PyInstaller --onedir output (built before this step)
Source: "..\build\dist\PsfScan\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
#ifdef HAS_MVS_SDK
; MVS SDK installer — staged into TEMP, deleted after install
Source: "vendored\{#MvsExeName}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Tasks: mvssdk
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
#ifdef HAS_MVS_SDK
; Silent-install MVS SDK runtime (Hikvision)
Filename: "{tmp}\{#MvsExeName}"; \
    Parameters: "/S"; \
    StatusMsg: "正在安装 MVS SDK 运行时（约 1 分钟）..."; \
    Flags: waituntilterminated; \
    Tasks: mvssdk
#endif

; Optional: launch app after a non-silent install
Filename: "{app}\{#MyAppExeName}"; \
    Description: "立即启动 {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
