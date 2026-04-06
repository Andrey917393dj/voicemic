; VoiceMic Installer - Inno Setup Script
; Builds a professional Windows installer with virtual audio driver

#define MyAppName "VoiceMic"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "VoiceMic Project"
#define MyAppURL "https://github.com/voicemic/voicemic"
#define MyAppExeName "VoiceMic.exe"

[Setup]
AppId={{E8F4A2B1-5C3D-4E6F-9A8B-7D2C1E0F3A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=license.txt
OutputDir=..\dist
OutputBaseFilename=VoiceMic-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardImageFile=..\assets\wizard_image.bmp
WizardSmallImageFile=..\assets\wizard_small.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
english.InstallingDriver=Installing virtual audio driver...
english.DriverInstalled=Virtual audio driver installed successfully.
english.DriverFailed=Driver installation failed. You may need to install it manually.
english.RemovingDriver=Removing virtual audio driver...
russian.InstallingDriver=Установка виртуального аудио драйвера...
russian.DriverInstalled=Виртуальный аудио драйвер успешно установлен.
russian.DriverFailed=Ошибка установки драйвера. Возможно, потребуется ручная установка.
russian.RemovingDriver=Удаление виртуального аудио драйвера...

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start VoiceMic when Windows starts"; GroupDescription: "Additional options:"
Name: "installdriver"; Description: "Install VoiceMic Virtual Microphone driver"; GroupDescription: "Audio driver:"; Flags: checkedonce

[Files]
; Main application
Source: "..\dist\VoiceMic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Language files
Source: "..\pc-server\lang\*"; DestDir: "{app}\lang"; Flags: ignoreversion recursesubdirs createallsubdirs
; Virtual audio driver
Source: "..\driver\build\*"; DestDir: "{app}\driver"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: installdriver
; Driver installer utility
Source: "..\driver\devcon.exe"; DestDir: "{app}\driver"; Flags: ignoreversion; Tasks: installdriver

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VoiceMic"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart
; App settings
Root: HKCU; Subkey: "Software\VoiceMic"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
; Install virtual audio driver
Filename: "{app}\driver\devcon.exe"; Parameters: "install ""{app}\driver\voicemic_audio.inf"" Root\VoiceMicAudio"; StatusMsg: "{cm:InstallingDriver}"; Flags: runhidden waituntilterminated; Tasks: installdriver
; Launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove virtual audio driver on uninstall
Filename: "{app}\driver\devcon.exe"; Parameters: "remove Root\VoiceMicAudio"; StatusMsg: "{cm:RemovingDriver}"; Flags: runhidden waituntilterminated

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Post-install actions
    Log('VoiceMic installation completed.');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    // Clean up driver before uninstall
    Log('VoiceMic uninstall started.');
  end;
end;
