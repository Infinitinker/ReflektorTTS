; The ReflektorTTS installer, compiled by tools/build_release.py with Inno Setup 7 (ISCC.exe) from
; the same folder as the portable zip. It installs for the current user only, with no admin rights,
; into %LOCALAPPDATA%\Programs\ReflektorTTS; settings, voices and logs stay in %LOCALAPPDATA%\ReflektorTTS.
;
; build_release.py passes:
;   AppVersion      the release, e.g. 0.2.0
;   NumericVersion  its four numbers for the Windows version resource, e.g. 0.2.0.0
;   Copyright       the copyright line from COPYRIGHT
;   SourceDir       the folder PyInstaller built, with the overlay and the text files
;   OutputDir       where the installer is written
;   IconFile        ReflektorTTS's icon

#if !Defined(AppVersion) || !Defined(NumericVersion) || !Defined(Copyright) || !Defined(SourceDir) || !Defined(OutputDir) || !Defined(IconFile)
  #error Build the installer with tools/build_release.py, which passes the values this script needs.
#endif

#define AppName "ReflektorTTS"
#define AppExe "ReflektorTTS.exe"
#define Repository "https://github.com/Infinitinker/ReflektorTTS"

[Setup]
; Never change AppId: it is how an update finds the installed ReflektorTTS.
AppId={{AC5D9BAE-0B1A-425C-845D-8B09802D303D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Infinitinker
AppPublisherURL={#Repository}
AppSupportURL={#Repository}/issues
AppUpdatesURL={#Repository}/releases
AppCopyright={#Copyright}
VersionInfoVersion={#NumericVersion}
VersionInfoProductTextVersion={#AppVersion}
PrivilegesRequired=lowest
SetupArchitecture=x64
MinVersion=10.0
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
; Setup speaks Polish on a Polish Windows and English elsewhere, without asking.
ShowLanguageDialog=auto
Compression=lzma2/ultra64
SolidCompression=yes
; Setup and Uninstall ask the user to quit a running ReflektorTTS (src/reflektortts/desktop/session.py
; holds this mutex). Setup then offers to close other programs that use its files, such as a game with
; the overlay loaded, which a silent install closes without asking. ReflektorTTS is started again from
; the last page, not by Windows.
AppMutex={#AppName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[CustomMessages]
english.DeleteUserData=Also delete your ReflektorTTS settings, downloaded voices and translation models, your own profiles and the logs?%n%n%1
polish.DeleteUserData=Usunąć też ustawienia ReflektorTTS, pobrane głosy i modele tłumaczenia, własne profile i logi?%n%n%1
english.UserDataNotDeleted=Some files in %1 could not be deleted. Delete the folder yourself.
polish.UserDataNotDeleted=Nie udało się usunąć niektórych plików z %1. Usuń ten folder ręcznie.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; PyInstaller's files change between releases; old ones must not stay mixed in with the new.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// The uninstaller removes the program folder; the user's own data is removed only if they say so.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserData: String;
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    UserData := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(UserData) and
       (MsgBox(FmtMessage(CustomMessage('DeleteUserData'), [UserData]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) and
       not DelTree(UserData, True, True, True) then
      MsgBox(FmtMessage(CustomMessage('UserDataNotDeleted'), [UserData]), mbError, MB_OK);
  end;
end;
