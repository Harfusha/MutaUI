#define MyAppName "Mutagen Control"
#ifndef MyAppVersion
#define MyAppVersion "8.2.0"
#endif
#define MyAppPublisher "Mutagen Control"
#define MyAppExeName "MutagenControl.exe"

[Setup]
AppId={{A247AF73-13F8-4D45-B7FC-F0AB374677A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Mutagen Control
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=MutagenControl-{#MyAppVersion}-windows-x64-setup
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[CustomMessages]
english.AdditionalShortcuts=Additional shortcuts:
english.ExplorerSendToTask=Add "Mutagen Control" to File Explorer Send To menu (optional)
czech.AdditionalShortcuts=Další zástupci:
czech.ExplorerSendToTask=Přidat „Mutagen Control“ do nabídky Odeslat v Průzkumníku (volitelné)

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "{cm:AdditionalShortcuts}"; Flags: unchecked
Name: "explorersendto"; Description: "{cm:ExplorerSendToTask}"; GroupDescription: "{cm:AdditionalShortcuts}"; Flags: unchecked

[Files]
Source: "..\..\dist-fast\MutagenControl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Mutagen Control"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Mutagen Control"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{usersendto}\Mutagen Control.lnk"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--open-folder"; Tasks: explorersendto

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Mutagen Control"; Flags: postinstall nowait skipifsilent
