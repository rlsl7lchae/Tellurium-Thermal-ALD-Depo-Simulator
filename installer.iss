; Te ALD Simulator 설치 프로그램 (Inno Setup 6)
; 사용법: build.bat 으로 dist\Te_ALD_Simulator 폴더를 만든 뒤,
;         이 파일을 Inno Setup Compiler로 열고 Build > Compile (Ctrl+F9)
; 결과물: installer_output\Te_ALD_Simulator_Setup.exe
;
; 관리자 권한 없이 사용자 폴더(%LOCALAPPDATA%\Programs)에 설치되고,
; 시작 메뉴에 "Te ALD Simulator"가 등록됩니다.

#define AppName "Te ALD Simulator"
#define AppVersion "1.1"
#define AppExe "Te_ALD_Simulator.exe"

[Setup]
AppId={{C97BA998-91CC-46D3-9959-058813EA038F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Chae Jungi
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=Te_ALD_Simulator_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 작업:"

[Files]
; PyInstaller 결과 폴더 전체 (exe + _internal)
Source: "dist\Te_ALD_Simulator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "설치 후 바로 실행"; Flags: nowait postinstall skipifsilent
