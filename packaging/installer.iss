; Inno Setup 6 : ISCC packaging\installer.iss /DAppVersion=1.0.0
; Entrée : dist\LiveClipper (PyInstaller onedir). Sortie : packaging\Output\LiveClipper-Setup.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Live Clipper"
#define AppExe "LiveClipper.exe"

[Setup]
AppId={{6E1F4A2B-3C9D-4E7A-9B1C-7D2E5F8A0C34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Live Clipper
DefaultDirName={autopf}\Live Clipper
DefaultGroupName=Live Clipper
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=LiveClipper-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
CloseApplications=yes
MinVersion=10.0.17763

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\LiveClipper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Live Clipper"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\Désinstaller Live Clipper"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Live Clipper"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Lancer Live Clipper"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed(): Boolean;
var
  V: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V);
  if Result then
    Result := (V <> '') and (V <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrorCode: Integer;
begin
  if (CurStep = ssPostInstall) and (not WebView2Installed()) then
  begin
    if MsgBox('Live Clipper a besoin du composant Microsoft Edge WebView2 pour afficher son interface.' + #13#10 +
              'Il n''a pas été trouvé sur ce PC. Ouvrir la page de téléchargement ?', mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/#download-section', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\LiveClipper');
    if DirExists(DataDir) then
      if MsgBox('Supprimer aussi tes données Live Clipper (clips, base, comptes, modèles Whisper) ?' + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
