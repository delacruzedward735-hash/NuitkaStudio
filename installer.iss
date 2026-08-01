#define MyAppName "Nuitka Studio"
#define MyAppVersion "3.9.3"
#define MyAppPublisher "John Edward Dela Cruz"
#define MyAppURL "https://myportfoliohub.online"
#define MyAppExeName "NuitkaStudio.exe"
#ifndef SourceDist
  #define SourceDist "release\run.dist"
#endif

[Setup]
AppId={{E1A6F5FA-A825-49BD-BCA4-86AC061975CF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=installer-output
OutputBaseFilename=NuitkaStudio-Setup-{#MyAppVersion}
SetupIconFile=assets\nuitka-studio.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
AppMutex=PypyProject.NuitkaStudio.App,Global\PypyProject.NuitkaStudio.App
CloseApplications=yes
RestartApplications=no
RestartManagerSupport=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
Uninstallable=yes
UninstallLogging=yes
UninstallLogMode=append
ChangesAssociations=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Professional Installer
VersionInfoCopyright=Copyright (c) 2026 {#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Creator Portfolio"; Filename: "{#MyAppURL}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{#MyAppURL}"; Description: "Visit the creator's portfolio"; Flags: shellexec postinstall unchecked skipifsilent
