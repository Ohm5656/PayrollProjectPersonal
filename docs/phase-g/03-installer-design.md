# Installer Design

The candidate uses Inno Setup, per-user (`PrivilegesRequired=lowest`), a Start
Menu shortcut and uninstaller. It does not launch the app, import data, enable
monitoring, register a task or remove persistent data automatically. Inno
Setup compiler was not available during source preparation, so installer build
and execution are NOT VERIFIED.
