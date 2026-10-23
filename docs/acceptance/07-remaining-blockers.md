# Remaining Blockers After Final Engineering Completion

**Date:** 23 October 2026 (Asia/Bangkok)

All safely automatable source-level work has been completed. This document
separates genuine external/human gates from engineering work. It does not
authorize production.

## Blocker decision matrix

| ID | Outstanding gate | Codex can run independently? | Existing safe tool sufficient? | Synthetic evidence meaningful? | Needs physical interaction? | Needs external trust/authorization? | Needs owner decision? | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B-01 | Notification-area Tray, monitor DPI and human visual acceptance | No | No | Partial only | Yes | No | No | HUMAN PHYSICAL INTERACTION REQUIRED |
| B-02 | Payroll rates, policies, exceptions and real-data copy-only UAT | No | No | Technical implementation only | No | Yes | Yes | HUMAN DECISION REQUIRED |
| B-03 | Backup retention, restore ownership and operator rehearsal | No | No | Recovery mechanics already pass | Yes | Yes | Yes | HUMAN DECISION REQUIRED |
| B-04 | Trusted signing identity and App Control publisher approval | No | No | Unsigned inspection only | No | Yes | No | EXTERNAL TRUST / AUTHORIZATION REQUIRED |
| B-05 | Signed installer install/upgrade/uninstall, frozen UI and packaged COM in a disposable environment | No | No | Static package evidence only | Yes | Yes | No | EXTERNAL AUTHORIZATION REQUIRED |
| B-06 | Production activation | No | No | Not an appropriate synthetic action | Yes | Yes | Yes | HUMAN DECISION REQUIRED |

## Technical blocker: frozen EXE trust

The frozen EXE is **BLOCKED**, not failed by payroll functionality. The direct
evidence is Code Integrity Event 3077 for the unsigned canonical main EXE:

- policy: `VerifiedAndReputableDesktop`;
- status: `0xc0e90002`;
- EXE SHA-256:
  `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B`;
- the initial observed block named the main EXE, not a bundled DLL;
- no security setting, exclusion, registry entry, certificate or policy was
  changed to obtain this evidence.

The current static signing preflight can inspect all shipped native binaries
and fail a release gate when any is unsigned, invalid, or lacks timestamp
evidence. It cannot issue a trusted identity, sign files, or establish
publisher trust. Those operations require a release owner and potentially a
Windows administrator.

## What is not a remaining automatable task

- Re-running the unsigned frozen EXE would only repeat the known security
  block and is prohibited.
- Installing the unsigned installer on this user-owned Windows environment is
  neither a safe substitute for a disposable environment nor evidence of
  trusted deployment.
- Driving another user's existing tray icon or QA session would not be isolated
  and would not provide valid acceptance evidence.
- Inventing payroll rates, tax treatment, rounding, retention or exceptions
  would replace business authority rather than test engineering.

## Required order to clear blockers

1. Complete source UI/tray and recovery operator acceptance using only QA data.
2. Obtain payroll-owner decisions and, if approved, separate copy-only UAT
   authorization.
3. Obtain trusted signing and policy approval; sign and verify a new build.
4. Use an authorized disposable Windows environment for installer, frozen UI,
   packaged Excel COM, upgrade/uninstall and clean-machine verification.
5. Obtain explicit production authorization only after all applicable evidence
   is accepted.

**Remaining safely automatable engineering tasks: 0.**
