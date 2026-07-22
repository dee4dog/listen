; Inno Setup script for Listen.
; Compiles the PyInstaller output in dist\Listen into a single native
; Windows installer executable: dist_installer\Listen-Setup-<version>.exe
;
; Build the PyInstaller bundle first (scripts\build_installer.ps1 does both
; steps), then compile this with:
;   iscc scripts\installer.iss

#define AppName "Listen"
#define AppVersion "1.0.0"
#define AppPublisher "Dirk Cilliers"
#define AppExeName "Listen.exe"
#define SourceDir "..\dist\Listen"

[Setup]
AppId={{6E6C5C7E-6E2F-4A3B-9C7E-4F1B7C0B7B01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\dist_installer
OutputBaseFilename=Listen-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
SetupIconFile=..\assets\icon.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove any cached models/logs the app wrote next to itself (app data
; under %LOCALAPPDATA%\Listen is left in place so recordings/db survive
; an uninstall/reinstall — delete it manually if a full wipe is wanted).
Type: filesandordirs; Name: "{app}"
