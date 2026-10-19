#define AppName "NTP Payroll Assistant - Test Candidate"
#define AppVersion "0.0.0-test"
#define AppExeName "NTP Payroll Assistant - Test Candidate.exe"
#ifndef SourceDir
  #error "SourceDir must be a verified fresh installer-staging directory"
#endif
#ifndef OutputDir
  #error "OutputDir must be provided by the reproducible build script"
#endif
[Setup]
AppId={{9A405ED8-9820-45F4-A7C8-C0A1D1DA7E01}}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\NTP Payroll Assistant Test Candidate
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=NTP-Payroll-Assistant-Test-Candidate-Setup
[Files]
; SourceDir is built from a strict allowlist; runtime state is never staged.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--qa-ui"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--qa-ui"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
[Run]
; Deliberately no automatic launch, monitoring or startup registration.
