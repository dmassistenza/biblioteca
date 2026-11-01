; Installer di Biblioteca (Inno Setup 7). Si compila con build.ps1, dopo PyInstaller.
; Regola: la disinstallazione toglie SOLO la cartella del programma. I libri, la Biblioteca,
; il catalogo, i log, le impostazioni e i modelli AI dell'utente non vengono mai toccati.

#define Nome "Biblioteca"
#define Versione "0.1.0"

[Setup]
AppId={{6E0B7C21-4C3A-4F5E-9C1B-2B7D8A4E9F10}
AppName={#Nome}
AppVersion={#Versione}
AppVerName={#Nome} {#Versione}
AppPublisher=Biblioteca
DefaultDirName={autopf}\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
; chi non e' amministratore puo' installare solo per se' (utile su PC condivisi o di scuole e chiese)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=output
OutputBaseFilename=Biblioteca-Setup-{#Versione}
SetupIconFile=biblioteca.ico
UninstallDisplayIcon={app}\Biblioteca.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
italian.Manuale=Manuale di Biblioteca
english.Manuale=Biblioteca manual
spanish.Manuale=Manual de Biblioteca
italian.NoWebView=Per la finestra del programma serve Microsoft Edge WebView2, che di solito c'è già in Windows 10 e 11 ma su questo PC non risulta installato.%n%nDopo l'installazione scaricalo gratis da:%nhttps://developer.microsoft.com/microsoft-edge/webview2/
english.NoWebView=The program window needs Microsoft Edge WebView2, which is usually included in Windows 10 and 11 but does not seem to be installed on this PC.%n%nAfter the installation download it for free from:%nhttps://developer.microsoft.com/microsoft-edge/webview2/
spanish.NoWebView=La ventana del programa necesita Microsoft Edge WebView2, que suele venir con Windows 10 y 11 pero no parece estar instalado en este PC.%n%nDespués de la instalación descárgalo gratis desde:%nhttps://developer.microsoft.com/microsoft-edge/webview2/

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\Biblioteca\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\Biblioteca.exe"
Name: "{group}\{cm:Manuale}"; Filename: "{app}\_internal\biblioteca\risorse\manuale.html"
Name: "{group}\{cm:UninstallProgram,{#Nome}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\Biblioteca.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Biblioteca.exe"; Description: "{cm:LaunchProgram,{#Nome}}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Presente(): Boolean;
var v: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  Result := Result and (v <> '') and (v <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WebView2Presente()) and (not WizardSilent()) then
    MsgBox(CustomMessage('NoWebView'), mbInformation, MB_OK);
end;
