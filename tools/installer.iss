; The ReflektorTTS installer, compiled by tools/build_release.py with Inno Setup 7 (ISCC.exe) from
; the same folder as the portable zip. It installs for the current user, with no admin rights, into
; %LOCALAPPDATA%\Programs\ReflektorTTS, or, if the user chooses and is an administrator, for all users
; into Program Files. Either way each user's settings, voices and logs stay in their own
; %LOCALAPPDATA%\ReflektorTTS.
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
#define AppGuid "AC5D9BAE-0B1A-425C-845D-8B09802D303D"
; The same start with Windows entry as src/reflektortts/desktop/autostart.py, which the app's own
; switch changes.
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#define StartupApprovedKey "Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

[Setup]
; Never change AppId: it is how an update finds the installed ReflektorTTS.
AppId={{{#AppGuid}}
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
; Setup asks "for me only" or "for all users" (or takes /CURRENTUSER or /ALLUSERS), offering the
; previous choice on an update; {autopf}, {autoprograms} and {autodesktop} follow it.
PrivilegesRequiredOverridesAllowed=dialog commandline
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
; holds the mutexes AppMutexes names). Setup then offers to close other programs that use its files, such as a game with
; the overlay loaded, which a silent install closes without asking. ReflektorTTS is started again from
; the last page, not by Windows.
AppMutex={code:AppMutexes}
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
english.StartWithWindows=Start ReflektorTTS when I sign in to Windows
polish.StartWithWindows=Uruchamiaj ReflektorTTS po zalogowaniu do Windows

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Offered only on a first install for oneself: an update must not turn back on what the user turned
; off in ReflektorTTS, and an all-users install runs as an administrator, whose sign-in it would set.
Name: "autostart"; Description: "{cm:StartWithWindows}"; Check: IsFirstInstall and not IsAdminInstallMode

[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --hidden"; Tasks: autostart

[InstallDelete]
; PyInstaller's files change between releases; old ones must not stay mixed in with the new.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; As the user who ran Setup, not as the administrator an all-users install runs as: ReflektorTTS
; keeps that user's settings and must not load the overlay into games with administrator rights.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
// An install for all users also looks for ReflektorTTS run by other users (the global mutex); one for
// the current user only in their own session, so another user's own copy does not stop it.
function AppMutexes(Param: String): String;
begin
  if IsAdminInstallMode then
    Result := '{#AppName},Global\{#AppName}'
  else
    Result := '{#AppName}';
end;

function IsFirstInstall: Boolean;
begin
  Result := not RegKeyExists(HKA, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppGuid}}_is1');
end;

// The uninstalling user's start with Windows, if it starts this copy (one from a zip may too).
procedure RemoveStartWithWindows;
var
  Command: String;
begin
  if RegQueryStringValue(HKCU, '{#RunKey}', '{#AppName}', Command) and
     (Pos(Lowercase(ExpandConstant('{app}\{#AppExe}')), Lowercase(Command)) > 0) then
  begin
    RegDeleteValue(HKCU, '{#RunKey}', '{#AppName}');
    RegDeleteValue(HKCU, '{#StartupApprovedKey}', '{#AppName}');
  end;
end;

// The uninstaller removes the program folder; the user's own data is removed only if they say so,
// and only for an install of their own: an all-users uninstall runs as an administrator, whose
// folder may not be the one of the user who asked, and leaves each user's data alone.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserData: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveStartWithWindows;
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent and not IsAdminInstallMode then
  begin
    UserData := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(UserData) and
       (MsgBox(FmtMessage(CustomMessage('DeleteUserData'), [UserData]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) and
       not DelTree(UserData, True, True, True) then
      MsgBox(FmtMessage(CustomMessage('UserDataNotDeleted'), [UserData]), mbError, MB_OK);
  end;
end;
