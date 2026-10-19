#define AppName "NTP Payroll Assistant - Test Candidate"
#define AppVersion "0.0.0-test"
#define AppExeName "NTP Payroll Assistant - Test Candidate.exe"
[Setup]
AppId={{9A405ED8-9820-45F4-A7C8-C0A1D1DA7E01}}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\NTP Payroll Assistant Test Candidate
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
[Files]
Source: "..\..\dist\NTP Payroll Assistant - Test Candidate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--qa-ui"
[Run]
; Deliberately no automatic launch, monitoring or startup registration.
