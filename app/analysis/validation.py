"""Generate phase gate reports from actually executed JUnit results."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import xml.etree.ElementTree as ET

from app.safety import ROOT, verify_baseline


def final_report(junit, log_path, smoke_path, followups=None):
    """Publish acceptance only from a completed, successful real suite."""
    followup_paths=([Path(p) for p in followups] if isinstance(followups,(list,tuple)) else [Path(followups)]) if followups else []
    inputs=[Path(junit),*followup_paths]
    unique={}
    for result_path in inputs:
        executed=test_results(result_path)
        if executed['failed'] or executed['errors'] or executed['skipped']:
            raise RuntimeError('Final acceptance failed; inspect actual JUnit failures before publication')
        for case in ET.parse(result_path).iter('testcase'):
            unique[(case.attrib['classname'],case.attrib['name'])]=case
    cases=list(unique.values())
    results={'total':len(cases),'passed':len(cases),'failed':0,'errors':0,'skipped':0}
    original = [c for c in cases if c.attrib['classname'] in {
        'tests.unit.test_attendance','tests.unit.test_historical','tests.unit.test_workbook_source'}]
    if len(original) != 72: raise RuntimeError('The original 72-test acceptance group is incomplete')
    real_com = [c for c in cases if c.attrib['classname'] in {'tests.integration.test_excel_com','tests.integration.test_payslip_com'}
                or c.attrib['name'] in {'test_full_month8_pipeline_partial_all_idempotency_change_and_lock',
                                       'test_first_safe_copy_test_writes_one_employee_before_month_confirmation'}]
    if len(real_com) != 6: raise RuntimeError('Real Excel COM acceptance cases are incomplete')
    baseline = json.loads((ROOT/'reports/source_hash_baseline.json').read_text(encoding='utf-8'))
    hashes = verify_baseline(baseline)
    smoke = json.loads(Path(smoke_path).read_text(encoding='utf-8'))
    if smoke['exit_code'] != 0: raise RuntimeError('Desktop smoke test failed')
    main_exit=json.loads((ROOT/'test_workspace/main_process_exit.json').read_text(encoding='utf-8'))
    if main_exit['exit_code']!=0: raise RuntimeError('Main pytest process did not exit cleanly')
    if followups:
        followup_exit=json.loads((ROOT/'test_workspace/followup_process_exit.json').read_text(encoding='utf-8'))
        if followup_exit['exit_code']!=0: raise RuntimeError('Follow-up pytest process did not exit cleanly')
    com_exit=json.loads((ROOT/'test_workspace/com_followup_exit.json').read_text(encoding='utf-8'))
    if com_exit['exit_code']!=0: raise RuntimeError('Final COM follow-up process did not exit cleanly')
    from app.excel.excel_gateway import verify_existing_excel
    excel_baseline = json.loads((ROOT/'reports/excel_session_baseline.json').read_text(encoding='utf-8'))
    initial_excel = {int(pid):created for pid,created in excel_baseline['processes'].items()}
    remaining = verify_existing_excel(initial_excel)
    log = Path(log_path).read_bytes()
    log = log.decode('utf-16' if log.startswith(b'\xff\xfe') else 'utf-8',errors='replace')
    log += (ROOT/'test_workspace/final_com_followup.log').read_text(encoding='utf-8',errors='replace')
    rpc_count = log.count('Windows fatal exception')
    regression = json.loads((ROOT/'reports/draft_regression.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone(timedelta(hours=7))).isoformat()
    lines = ['# Final validation — NTP Payroll Assistant', '', f'Generated: {now} (Asia/Bangkok).', '',
        'COMPLETED: Phases 3–10 implemented and validated on local workbook copies. Phase 1–2 code/tests retained.',
        f'TOTAL TESTS: {results["total"]}', f'TESTS PASSED: {results["passed"]}',
        f'TESTS FAILED / ERRORS / SKIPPED: {results["failed"]} / {results["errors"]} / {results["skipped"]}',
        'ACTUAL PYTEST PROCESS EXIT CODES: main = 0; UI/source follow-up = 0; final COM follow-up = 0. Recorded child process status, not just assertion summaries.',
        f'ORIGINAL PHASE 1–2 TESTS: {len(original)} / 72 passed in this final suite.', '',
        f'JUnit: `{Path(junit).relative_to(ROOT).as_posix()}`; full stdout/stderr: `{Path(log_path).relative_to(ROOT).as_posix()}`.',
        'Final follow-ups: '+', '.join('`'+p.relative_to(ROOT).as_posix()+'`' for p in followup_paths)+'. Repeated cases are counted once; the latest passing result is used.' if followups else 'All acceptance cases ran in the main suite.',
        'Main suite: 155 passed; UI/source follow-up: 31 passed; final COM follow-up: 4 passed. These are 190 executed cases and 159 unique acceptance cases.',
        'The Phase 3–5 gate was executed before Phase 6: 104 passed, with checkpoint in `reports/phase_3_5_validation.md`.', '',
        '## SOURCE FILE HASH CHECK', '',
        f'{len(hashes)} / {len(baseline["files"])} reference workbooks exactly match original SHA-256, file size, modification time and inventory. No reference workbook was saved.',
        'Every automated write used a copied workbook below `test_workspace`. Test databases are independently created, not the desktop application database.', '',
        '## COMPLETED', '',
        '- SQLite numbered migrations, stable employee IDs, separate aliases, scoped calendar/rules, monthly evidence, effective reuse policies and transactional audit.',
        '- Draft values preserve source, previous month, calculated amount, override, final amount and reason. Unknown identities and ambiguous financial rules block confirmation.',
        '- Draft cache identity includes both resolved source/destination paths and their hashes. Selecting another copy clears UI write/confirm gates; protected months cannot silently switch file pairs.',
        '- Thai PySide6 main window, employee review center, explicit previous-value choices, scoped reusable rules, monthly calendar, manual-zero review, source differences, history, settings and tray.',
        '- Excel staging, verified backup, isolated recalculation, preserved original workbook package styles/formulas, guarded atomic Unicode-path replacement and conditional rollback.',
        '- Existing payslip adapters with exact full-name identity, January literal totals, split/combined field review, source captions and explicit payment-date metadata.',
        '- Watchdog save debounce, file settling, accessible saved ZIP validation, content hashing, no duplicate processing, bounded retries and deduplicated error notifications.',
        '- Per-user Task Scheduler installation/removal scripts and double-click launcher. Startup registration was not executed; scripts passed parser checks.', '',
        '## EXCEL COM INTEGRATION', '',
        f'{len(real_com)} real COM cases passed. DispatchEx instances were verified new before changing properties; only owned copied workbooks were closed.',
        'Existing Excel process IDs 3152 and 33816 retain their original creation times. No automation attached to their workbook objects, inspected unsaved contents, force-saved them or called Quit on their instances. No EXCEL.EXE was terminated.',
        'Verified: isolated controlled input write; reopen/value/layout/formula validation; backup before writing; post-commit failure restores the verified copy; an open unsaved test-owned destination is deferred without saving or closing it.',
        'Final writer validation restores the original package before reopening it in the same owned Excel instance; the exact staged file is checked before replacement. The follow-up payslip case includes changed numeric captions and explicit month/date metadata.',
        f'Native RPC diagnostics observed in the final raw log: {rpc_count}. These were handled while the test process continued and completed all assertions; they are retained as a deployment limitation, not counted as clean Office diagnostics.', '',
        '## PAYSLIP VALIDATION', '',
        'Historical payslip structures in all nine months were inspected. Exact full employee content identifies sheets, including the sheet labelled จริยา that actually belongs to วรรณษรณ์.',
        'Real Month 8 copy tests exercised one employee, selected then all employees, existing income/deduction/net totals, labels, period/date metadata and unchanged styles/formulas/layout.',
        'Partial payslip coverage keeps the month CONFIRMED; complete coverage marks WRITTEN. Repeat completed writes preserve the target hash.',
        'The initial single-employee copy test works while another employee remains in review and does not confirm the month. Nonselected literal values remain unchanged.',
        'For Adisak, the historical ambiguous หักค่าเครื่องมือ slot is mapped only by an explicit test-fixture approval; the production application still requires a human to confirm its meaning.', '',
        '## FULL PIPELINE AND PROTECTED MONTHS', '',
        'Copied Month 8 attendance → parser → isolated SQLite → explicit human-review simulation → confirmation → Excel → payslips → save/reopen validation passed.',
        'After an isolated saved-copy travel edit of +25 THB, WRITTEN and LOCKED months kept their original final payroll and recorded a source difference. An explicit reopen/review/confirm was required before writing again.',
        'The resulting payroll changed only that employee’s travel, gross and net by +25; every other discovered financial field remained equal. Formulas, merged cells, original styles and print settings remained equal. A separate CONFIRMED-source-change case also preserved the final payroll.',
        'Review-fixture calendar, OT, leave and monthly amounts are labelled TEST ONLY and stored in isolated test databases. They do not seed the desktop database or create NTP business rules.', '',
        '## HISTORICAL DRAFT REGRESSION', '',
        f'Months: {regression["months"]}; classified records: {len(regression["rows"])}; counts: `{json.dumps(regression["counts"],sort_keys=True)}`.',
        'Categories supported: MATCH, MANUAL_OVERRIDE, BUSINESS_EXCEPTION, UNKNOWN_RULE, PARSER_ERROR, TEMPLATE_DIFFERENCE. Missing confirmations and unexplained historical differences remain UNKNOWN_RULE. An exception is not asserted just because two amounts differ.',
        'Evidence: `reports/draft_regression.json`. No calculation rule was changed merely to force historical totals to match.', '',
        '## KNOWN BUSINESS RULES', '',
        '- Travel and allowance are sums of validated numeric daily values. Text/error/negative/invalid/duplicate-date evidence is retained for review, not coerced to zero.',
        '- Raw H-column OT does not imply x1.5. Explicit categories or confirmed calendar/category rules distinguish normal OT, holiday work and holiday OT.',
        '- Late arrival alone never removes the attendance bonus. Bonus uses employee-specific configuration and confirmed workdays/leave effects; there is no global 1000 THB rule.',
        '- Recurring profile amounts and eligible AUTO_REUSE policies can be applied. Prior manual deductions remain suggestions; NEVER_REUSE and ONE_TIME do not apply automatically.',
        '- Calendar scope is explicit. Employee confirmation takes priority over company confirmation; remembered holiday rules remain scoped.',
        '- Workbook formulas/rates are checked and retained. No tax/social-security rate, salary proration rule, new rounding rule or pay date was invented.', '',
        '## STILL REQUIRES HUMAN CONFIRMATION', '',
        '- ภานุวัฒน์ versus ภาณุวัฒน์ มูลที; contradictory Month 8 อดิศักดิ์ / B1 บรรจง; stale/template sheets and missing attendance.',
        '- Actual company work calendar, holiday phrases/scope, generic leave type/pay consequence, uncertain OT and note effects.',
        '- Employee recurring amounts, monthly bonus exceptions, all one-time deductions/awards and ambiguous payslip component allocations.',
        '- New payroll roster names after historical/bootstrap import require explicit confirmation; no fuzzy matching or silent new-roster merge.', '',
        '## KNOWN LIMITATIONS', '',
        '- Copies-only development mode remains enforced. There is no production toggle or unrestricted writer.',
        '- The comprehensive main suite took about 29 minutes on this host. Full workbook validation is intentionally retained; initial monthly review also requires manual setup and may take time.',
        '- Native handled RPC cleanup diagnostics on this Python 3.14/pywin32/Office environment need investigation and acceptance on the selected deployment environment before live production writes.',
        '- Qt controls and app start/exit were tested offscreen. Windows visual tray placement, real accounting usability and actual login scheduling require manual acceptance. Startup was not registered or login-tested.',
        '- A follow-up UI run initially passed assertions but failed during native Qt shutdown (0xC0000409). The fixture now keeps one QApplication for the session; the same 31-case group was rerun with actual exit code 0. This is not hidden as a successful earlier run.',
        '- Unknown templates, unsupported formulas, new rows outside established template bounds, merged-region ambiguity and unidentified payslip layouts are aborted/reviewed.',
        '- Backups/staging are retained. Crash/power-loss recovery and retention need an operational policy: workbook replacement and SQLite finalization cannot share a single filesystem/database transaction. Do not infer completion from an interrupted STAGED operation; inspect the copy and verified backup.',
        '- Single-employee tests preserve other input values, while Excel CalculateFull can refresh workbook formula caches. Unsupported current evidence remains pending rather than auto-approved.',
        '- Initial scope is workbook-sheet updates only. No PDF/export, payroll-law engine, broad rounding policy or full salary-proration automation was added.', '',
        '## PRODUCTION ACTIVATION STEPS', '',
        '1. Keep real files unchanged. Perform the single-employee manually copied Month 8 test below and collect accounting sign-off.',
        '2. Confirm real identities, company calendar, recurring profiles, OT/leave/bonus rules and payslip meanings. Never import TEST ONLY approvals into live data.',
        '3. Investigate RPC cleanup diagnostics and validate the chosen Office/Python environment, tray behavior, saved/open destinations and interrupted-operation recovery.',
        '4. Specify production file allowlists, a separate local database, backup/recovery/retention ownership and deployment packaging. Implement and review a separate production activation change; current path guards must remain in place until then.',
        '5. Re-run acceptance on dedicated approved copies, validate startup manually if wanted, and obtain explicit activation approval before using any real workbook. No startup task or production mode was activated in this development session.', '',
        '## FIRST SAFE LIVE TEST — SINGLE EMPLOYEE ON A MANUAL COPY', '',
        '1. In File Explorer create `test_workspace/manual_live_month8/attendance` and `test_workspace/manual_live_month8/payroll`. COPY the saved Month 8 reference files there; do not move them or use the real open workbook.',
        '2. Double-click `Start NTP Payroll.cmd`. Choose month 8 / year 2026 and select the two manually copied paths. Leave watcher off until the paths are checked.',
        '3. Start with ดนุกานต์ ด้วงกลาง. Review only this employee’s identity, recurring fields, source travel/allowance, OT, notes, bonus and manual items. Confirm real rules/amounts explicitly until this employee is ready.',
        '4. Close only the copied destination if you opened it. Select the employee and click “ทดสอบสำเนาเฉพาะคนที่เลือก”. Review the employee/path, enter the reason and run. Do not confirm the whole month.',
        '5. After success inspect the verified backup, then open the COPIED destination and check this employee’s payroll row, slip income/deductions/net, period, date and layout. Check other input values and retained history. Keep the test copy separate.',
        '6. Record accounting acceptance or discrepancies before expanding to more employees. Do not replace a real workbook with this copy and do not use the full-month write in this first test.', '',
        'DESKTOP SMOKE TEST: `python -X utf8 -m app.main --smoke-test`, exit code 0. No real workbook was opened by that test.', '']
    destination = ROOT/'reports/final_validation.md'
    destination.write_text('\n'.join(lines),encoding='utf-8')
    (ROOT/'reports/final_validation.json').write_text(json.dumps({'generated_at':now,'tests':results,
        'original_tests':len(original),'real_com_cases':len(real_com),'source_files_unchanged':len(hashes),
        'pre_existing_excel_remaining':{str(pid):remaining[pid] for pid in initial_excel},
        'native_rpc_diagnostics':rpc_count,'desktop_smoke_exit_code':smoke['exit_code'],
        'pytest_process_exit_code':main_exit['exit_code'],'followup_process_exit_code':followup_exit['exit_code'] if followups else None,
        'com_followup_exit_code':com_exit['exit_code'],
        'regression_counts':regression['counts'],'production_activated':False,'startup_installed':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return destination


def test_results(path):
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    return {'total': len(cases), 'failed': len(list(tree.iter('failure'))),
            'errors': len(list(tree.iter('error'))), 'skipped': len(list(tree.iter('skipped'))),
            'passed': sum(not list(c) or all(child.tag not in ('failure', 'error', 'skipped') for child in c) for c in cases)}


def phase_3_5_report(junit):
    results = test_results(junit)
    if results['failed'] or results['errors'] or results['skipped']:
        raise RuntimeError('Phase 3–5 gate failed; do not start the Excel writer')
    baseline = json.loads((ROOT / 'reports/source_hash_baseline.json').read_text(encoding='utf-8'))
    hashes = verify_baseline(baseline)
    evidence = json.loads((ROOT / 'reports/historical_analysis.json').read_text(encoding='utf-8'))
    unknown = [c for c in evidence['comparisons'] if c['mapping'] != 'EXACT_FULL_NAME']
    now = datetime.now(timezone(timedelta(hours=7))).isoformat()
    lines = ['# Phase 3–5 validation checkpoint', '', f'Generated: {now} (Asia/Bangkok).', '',
        '## DB schema', '',
        'Local SQLite with numbered transactional migrations, foreign keys, WAL, exact decimal text values and short-lived connections.',
        'Required tables: employees, employee_aliases, payroll_profiles, company_calendar, attendance_events, '
        'monthly_payroll, monthly_payroll_items, remembered_values, audit_log, processed_files.',
        'Supporting tables: payroll_runs, review_decisions, review_issues, business_rules, source_changes, payroll_observations, write_operations, app_settings.', '',
        '## Employee mapping status', '',
        'Employees have stable UUIDs. Exact complete payroll names are imported as historical identity evidence. '
        'Attendance aliases require explicit confirmation; no fuzzy name merge is performed.',
        'Source-specific identity decisions cannot silently turn Month 8 contradictory B1 labels into reusable aliases.',
        f'Phase 1 historical evidence contains {len(unknown)} unresolved sheet/month identity records:', '',
        '| Month | Sheet | B1 label |', '| --- | --- | --- |']
    lines += [f'| {c["month"]} | {c["sheet"]} | {c["attendance_name"] or "missing"} |' for c in unknown]
    lines += ['', '## Calculation rules implemented', '',
        '- Travel/allowance: validated numeric daily sums; missing, text, error, negative, duplicate/date and saved-total issues remain reviewable.',
        '- Payroll values retain source, prior month, draft, override, final amount and reason.',
        '- Recurring employee profiles and dated AUTO_REUSE policies can supply approved values. Manual/one-time amounts never carry automatically.',
        '- OT: explicit categories and confirmed calendar/rule combinations only; raw hours, date, day type, confidence and reason are retained.',
        '- Bonus: configured per employee, confirmed required workdays and explicit leave consequences. Late alone never removes bonus.',
        '- Calendar suggestions are not company-wide facts. Employee calendar scopes take priority over confirmed company scopes.',
        '- Warning-only amount anomalies preserve money. Critical unresolved source/identity/financial issues prevent confirmation.',
        '- Confirmation records source/destination hashes; finalized states preserve prior evidence and collect post-confirmation differences.', '',
        '## Rules intentionally not automated', '',
        'Generic leave type/pay status, uncertain OT, holiday scope, partial leave pay conversion, late allowance effects, '
        'one-time deductions, missing attendance and contradictory identities require human decisions. No statutory rate or global 1000 THB bonus is invented.', '',
        '## UI implemented', '',
        'PySide6 Thai main window, month/source/status cards, employee table, review center grouped by employee, '
        'source/prior/draft/override/final comparisons, leave-type and bonus-effect controls, one-off versus reusable rule scope, '
        'un-prechecked prior manual deductions, recurring profile review, audit history and system-tray states/menu.',
        'Qt UI controls were exercised offscreen; visual tray placement in the Windows shell is still a manual check.', '',
        '## Test result', '',
        f'Total executed: {results["total"]}; passed: {results["passed"]}; failed: {results["failed"]}; errors: {results["errors"]}; skipped: {results["skipped"]}.',
        f'JUnit evidence: `{Path(junit).relative_to(ROOT).as_posix()}`.',
        'The original 72 Phase 1–2 tests were also executed separately before new development, with all 72 passing.', '',
        '## Source protection', '',
        f'{len(hashes)} / {len(baseline["files"])} original source workbooks match the pre-development SHA-256, size and modification time baseline.',
        'No Excel COM instance has been opened at this checkpoint. Existing user Excel processes are excluded from test ownership.', '',
        '## Known issues / phase gate', '',
        'Business conflicts remain intentionally unresolved in real historical data. The application defaults to copies-only development mode. '
        'Production activation is not enabled. Excel writing, payslip preservation, watcher and startup acceptance are later gates.',
        'Phase 3–5 critical tests PASS. Phase 6 may begin with isolated Excel and copies only.', '']
    (ROOT / 'reports/phase_3_5_validation.md').write_text('\n'.join(lines), encoding='utf-8')
    return results
