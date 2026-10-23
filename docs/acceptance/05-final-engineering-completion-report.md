# Final Engineering Completion Report

**Date:** 23 October 2026 (Asia/Bangkok)
**Repository / branch:** `Ohm5656/PayrollProjectPersonal` / `main`
**Pushed baseline:** `9fec0e2`
**Preserved local commits:** `a762abb`, `16abe88`, `517f680`

## Scope and safety result

This report completes the bounded engineering audit requested before human
acceptance. Tests used disposable databases, fictional workbooks, isolated Qt
sessions, and owned Excel instances only. No normal database, reference
workbook, user-owned QA database, user-owned Excel process, Scheduled Task,
Windows policy, trust store, production setting, frozen EXE, installer, or
`docs/qa/` file was changed.

The normal persistent smoke test was intentionally not run because it can open
the development database. The known-blocked frozen EXE was not retried.

## Working checklist and coverage matrix

| Area | Classification after audit | Automated evidence | Final status | Remaining boundary |
| --- | --- | --- | --- | --- |
| Five primary UI pages, navigation, dialogs, filters, empty states | ALREADY VERIFIED | Native Qt focused suite; synthetic visible-window harness | PASS | Human visual comfort review only |
| Period selector, stale rows, employee/detail context | ALREADY VERIFIED | September/October/empty-month and detail regression tests | PASS | None technical |
| Thai text, surfaces, icons, scroll areas, QSS parsing | ALREADY VERIFIED | Native Qt captures; style/palette tests; no native QSS warning | PASS | Actual monitor/DPI judgement |
| Keyboard focus, Tab/Shift+Tab, safe controls | ALREADY VERIFIED | accessibility/lifecycle native Qt regression tests | PASS | Physical keyboard traversal |
| Window lifecycle and single-instance IPC | ALREADY VERIFIED | controller, native handle, IPC, shutdown tests | PASS | None technical |
| Notification-area icon/menu click | HUMAN PHYSICAL INTERACTION REQUIRED | Controller callbacks and tray availability are tested | NOT VERIFIED | User must use the actual Windows notification area |
| Monitoring preference, QA isolation and watcher lifecycle | ALREADY VERIFIED | QA environment, settings, watcher and supervision tests | PASS | No real-folder monitoring was authorized |
| Payroll calculation, matching, review, confirmation and audit | ALREADY VERIFIED | isolated Decimal/UAT workflow tests | PASS (technical) | Owner must approve business rules |
| Monthly copy, formulas, layout, payments and rollover | ALREADY VERIFIED | workbook/period/December rollover tests | PASS (technical) | Owner policy approval |
| Source Excel COM and write recovery | ALREADY VERIFIED | owned-instance COM, backup, restore and writer safety tests | PASS | Packaged COM awaits trusted candidate |
| Backup, SQLite snapshot and ambiguous-operation recovery | ALREADY VERIFIED | hash, fresh-destination, snapshot, failure-injection tests | PASS | Operator rehearsal/retention decision |
| Runtime jobs, watcher, debounce and recovery | ALREADY VERIFIED | deterministic watcher/runtime/job regression tests | PASS | No real-folder monitoring authorized |
| Staging, installer contract and mutable-state isolation | ALREADY VERIFIED | staging allowlist, manifest, QA-only package tests | PASS | Installation needs disposable authorization |
| Signing evidence and release preflight | AUTOMATABLE AND NOW VERIFIED | new opt-in signature verifier checks `.exe`, `.dll`, `.pyd`, Authenticode and timestamp evidence | PASS (tooling) | Trusted signing identity is external |
| Frozen candidate execution | AUTOMATABLE BUT BLOCKED | Code Integrity Event 3077 evidence; unsigned candidate inspection | BLOCKED | Trusted signing and policy approval |
| Installer install/upgrade/uninstall and packaged COM | EXTERNAL AUTHORIZATION REQUIRED | static/contract inspection only | NOT VERIFIED | Authorized disposable environment |
| Payroll policy and production authorization | HUMAN DECISION REQUIRED | fictional technical evidence prepared | PENDING | Business owner and deploy authority |

**Audit conclusion:** every safe, meaningful automated check available in this
repository and on this host has either passed or is explicitly blocked by an
external trust/authorization boundary. No item was left manual merely because
an automated test was absent.

## Verified engineering changes

### Native visual fixes retained

The prior native Qt correction remains covered: scoped opaque canvas/table
surfaces prevent dark Windows palette inheritance, and quoted local SVG paths
prevent a stylesheet parse failure when the repository path contains spaces.
The current native Qt suite passed after those fixes.

### Signing-readiness preflight added

`packaging/verify_signatures.ps1` is intentionally an inspection tool, not a
signing tool. It:

- enumerates every shipped `.exe`, `.dll`, and `.pyd` under a supplied bundle;
- records SHA-256, Authenticode status/type, signer identity, and timestamp
  identity without exporting credentials or changing a file;
- permits current unsigned-candidate inspection by default; and
- fails only when the explicit `-RequireTrustedSignature` switch is used and
  any native binary lacks a valid Authenticode signature or RFC 3161 timestamp.

`verify_exe.ps1` and `verify_installer.ps1` now call the same evidence tool.
No signing hook, private key, certificate, thumbprint, trust-store change, or
security-policy modification was added. The new packaging contract test proves
that this behaviour remains opt-in and includes all shipped native-binary
extensions.

Read-only inspection of the canonical candidate bundle examined **127** native
binaries. Aggregate `all_trusted` is `false`; strict mode correctly rejected
the unsigned bundle. This is expected and does not alter the pre-existing
Windows Application Control blocker.

## Test results

| Scope | Result |
| --- | --- |
| Native Windows Qt focused UI/controller suite | `56 passed in 106.74 s` |
| Synthetic payroll, Excel safety, runtime, recovery and packaging suite | `112 passed in 101.74 s` |
| Native source Excel COM suite | `3 passed in 45.89 s` |
| Full unit suite | `332 passed in 400.05 s (0:06:40)` |
| Read-only EXE and installer signature-verification wrappers | PASS |
| `python -X utf8 -m compileall -q app` | exit 0 |
| `git diff --check` | exit 0 |

The native COM run first observed zero `EXCEL.EXE` processes and used only an
owned Excel instance. It did not attach to or terminate an existing process.

## Tray verification levels

| Level | Result | Evidence / limitation |
| --- | --- | --- |
| A — Qt controller | PASS | hide/restore, authoritative callbacks, Exit, and runtime shutdown tested |
| B — source native Windows process | PASS | isolated visible native Qt windows, handles and single-instance IPC tested |
| C — Windows notification area | NOT VERIFIED | no user-owned icon was manipulated and no independent shell automation was authorized/available |

## Packaging and signing readiness

The canonical EXE remains
`dist/build-6c5c459ccfac4d498ad85c6c517a46e9/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe`
with SHA-256 `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B`.
The canonical installer remains
`artifacts/NTP-Payroll-Assistant-Test-Candidate-Setup.exe` with SHA-256
`D7C8C8E87B0D8FCBFE59737026A3AFA4B16D31AD3C6E56787500DF2C1C74A8DB`.

The candidate and installer are not represented as trusted. The existing
diagnosis confirms that Code Integrity blocked the unsigned main EXE under the
`VerifiedAndReputableDesktop` policy before any bundled DLL could load. See
[the Application Control diagnosis](../phase-g/07-windows-application-control-diagnosis.md).

## Exact unresolved boundaries

1. Only a release owner can obtain/authorize a trusted signing identity and a
   protected signing service or agent.
2. Only an authorized Windows administrator can confirm that the approved
   publisher/trusted-signing route meets the applicable policy.
3. Only an authorized operator can install/uninstall a signed candidate in a
   disposable environment and interact with a real Windows notification area.
4. Only the payroll owner can approve business rules and authorize copy-only
   real-data UAT.
5. Only the authorized business/deployment owner can approve production.

The comprehensive handoff is in
[06-human-acceptance-package-th.md](06-human-acceptance-package-th.md), and
the rationale for each blocker is in
[07-remaining-blockers.md](07-remaining-blockers.md).

## Engineering decision

**AUTOMATABLE ENGINEERING WORK COMPLETE: YES.** Source-only QA, technical UAT,
recovery, runtime and packaging contracts are ready for human acceptance.
This is not final acceptance, trusted deployment approval, or production
authorization.
