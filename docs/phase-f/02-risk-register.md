# Phase F Risk Register

| Risk | Level | Existing mitigation | Remaining acceptance |
| --- | --- | --- | --- |
| Wrong/outside workbook target | Critical | resolved test-root guard, reference/hash/hard-link checks | production workflow intentionally deferred |
| Stale or changed source | Critical | snapshot/hash/revision guards | operator review |
| Incorrect identity/review decision | Critical | exact mapping and READY/confirm gates | business-owner approval |
| Excel external process or failed save | High | `DispatchEx` ownership, backup, structure/reopen validation | native interruption test deferred |
| Power loss/staged ambiguity | High | atomic replacement, backup, retained staging evidence | operator recovery rehearsal |
| DB corruption/job interruption | High | transactions, durable jobs, integrity rehearsal | deployment environment approval |
| Watcher duplicates/restarts | Medium | idempotent jobs and watcher ownership tests | final Windows monitoring acceptance |
| Startup/Task Scheduler mistake | Medium | explicit mocked integration only | sign-in test needs permission |
| disk/permissions/template mismatch | Medium | preflight warnings and fail-closed operations | operator configuration sign-off |
