# Deployment Safety Contract

## Readiness levels

| Level | Meaning | Write permission |
| --- | --- | --- |
| DEVELOPMENT | local engineering | only `test_workspace` |
| SYNTHETIC_UAT | fictional generated fixtures | only unique UAT children |
| DEPLOYMENT_CANDIDATE | technical evidence complete | still only `test_workspace` |
| PRODUCTION_AUTHORIZED | future business process | not implemented in Phase F |

No readiness result changes `development_target()`. There is no activation
flag, environment override or production-write path in this phase.

## Mutation map

| Entry point | Possible mutation | Existing fail-closed control |
| --- | --- | --- |
| `Database` / repositories | isolated SQLite rows and migrations | callers must supply an isolated DB; readiness must not construct normal DB |
| `PayrollService.prepare/confirm/reopen/lock` | runs, items, review/audit rows | state, revision and source-hash guards |
| `PayrollWriter` | target copy, backup, staging, write history | `development_target`, source hash, validated backup, owned Excel, atomic replace |
| `BackupService` | backup package | valid ZIP + hash verification |
| workflow configuration | app setting | path validation under test root |
| runtime/watcher/jobs | job rows and watcher lifecycle | explicit resume/pause and single owner |
| Windows startup | Task Scheduler | explicit service operation; not invoked by readiness |

## Mandatory gates

1. Target must resolve below `test_workspace`, must not be a reference path or
   hard link, and must be a file rather than the workspace root.
2. A payroll write requires a reviewed state, source/hash/revision evidence,
   validated backup and an owned Excel instance.
3. Ambiguous staging/recovery is evidence for a human decision, never an
   automatic restore.
4. Monitoring, Task Scheduler and production authorization are not outcomes of
   this contract.
