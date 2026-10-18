# Phase D.1 — Implemented Shell Foundation

## Delivered foundation

Phase D.1 implements the presentation foundation described by the approved D.0 documents. It adds a shared QSS theme, Thai-capable Windows font fallbacks, a persistent left sidebar, page header and `QStackedWidget` page host.

The existing payroll controls now reside in the Overview compatibility page. No calculation, database schema, Excel template, writer safety rule, watcher lifecycle or runtime ownership was moved into the shell.

## Navigation status

| Destination | D.1 behaviour | Future phase |
| --- | --- | --- |
| ภาพรวม | Hosts the complete existing payroll workflow as a compatibility page. | D.2 redesigns it as the dedicated overview. |
| รอตรวจสอบ | Routes to the current Review Center. | D.3 creates the review queue/detail UI. |
| ประวัติ | Routes to the current audit-history dialog. | D.4 creates history/period lifecycle UI. |
| ปัญหาและการกู้คืน | Honest placeholder only; no synthetic errors or recovery records. | D.5 provides the runtime/job recovery surface. |
| ตั้งค่า | Routes to the existing Setup Wizard. | D.6 provides redesigned settings/first-run UI. |

## Safety and lifecycle guarantees

- Navigation is presentation-only and never calls `resume_monitoring()`, `pause_monitoring()`, creates a runtime, or creates a watcher.
- Existing public `review()`, `history()`, `settings()` and `open_copy(kind)` entry points remain available for the tray.
- Settings remains governed by the Phase C.1 rule: saving folders/Windows-start preference cannot resume an explicitly paused watcher.
- `WindowController` remains the sole lazy creator/restorer of `MainWindow`; close-to-tray and tray-triggered safe shutdown are unchanged.
- The compatibility page preserves current state gates for review, confirmation, copy-only writing, payslips, reopening and locking.

## Responsive and accessibility foundation

The standard shell is 220–240 px wide. At window widths below 1024 px it becomes a readable 180 px compact sidebar; labels remain visible rather than becoming unlabelled icon-only controls. The window has an 860 × 620 minimum size, while the compatibility content scrolls as a single page around its existing table control.

Navigation buttons are checkable, have visible text, keyboard focus and accessible names. Theme QSS defines focus, hover, pressed, disabled and selected states. Status meaning remains text-first; no semantic state is conveyed only through colour.

## Visual QA scope

Automated offscreen layout tests cover the wide 1366 × 768 shell and a 900 px compact shell, including readable navigation labels and the minimum window size. Actual interactive Windows visual QA at 100%, 125%, 150% and 200% DPI was **not verified in this environment**. It remains a D.7/manual release checklist item; this document does not represent it as passed.

## Not implemented in D.1

D.1 deliberately does not claim implementation of the redesigned Overview metrics/action panel, Review queue, history filters/detail, problems/recovery read model, or new settings screen. Those remain D.2 through D.6. D.7 remains responsible for final cross-page accessibility and polish.
