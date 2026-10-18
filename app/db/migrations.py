"""Numbered, transactional migrations. Never modifies an Excel workbook."""
MIGRATIONS = [(1, [
    """CREATE TABLE employees (
        id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, name_norm TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE employee_aliases (
        id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id),
        alias TEXT NOT NULL, alias_norm TEXT NOT NULL, source TEXT NOT NULL,
        confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(alias_norm,source))""",
    """CREATE TABLE payroll_profiles (
        employee_id TEXT PRIMARY KEY REFERENCES employees(id), base_salary TEXT,
        attendance_bonus_default TEXT, phone_allowance TEXT, position_allowance TEXT, housing TEXT,
        attendance_required INTEGER NOT NULL DEFAULT 1 CHECK(attendance_required IN (0,1)),
        confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)), updated_at TEXT NOT NULL)""",
    """CREATE TABLE company_calendar (
        date TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '*', type TEXT NOT NULL,
        description TEXT NOT NULL, required_workday INTEGER NOT NULL CHECK(required_workday IN (0,1)),
        affects_attendance_bonus INTEGER NOT NULL CHECK(affects_attendance_bonus IN (0,1)),
        confirmed INTEGER NOT NULL CHECK(confirmed IN (0,1)), source TEXT NOT NULL,
        confirmed_by TEXT, PRIMARY KEY(date,scope))""",
    """CREATE TABLE payroll_runs (
        id TEXT PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
        state TEXT NOT NULL CHECK(state IN ('DRAFT','NEEDS_REVIEW','READY','CONFIRMED','WRITTEN','LOCKED')),
        source_path TEXT NOT NULL, source_hash TEXT NOT NULL, payroll_path TEXT NOT NULL,
        payroll_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, evidence TEXT NOT NULL,
        calculated_at TEXT NOT NULL, confirmed_at TEXT, UNIQUE(year,month))""",
    """CREATE TABLE attendance_events (
        id TEXT PRIMARY KEY, employee_id TEXT REFERENCES employees(id), date TEXT NOT NULL,
        event_type TEXT NOT NULL, raw_text TEXT NOT NULL, hours TEXT, days TEXT,
        confirmed INTEGER NOT NULL DEFAULT 0, source_workbook TEXT NOT NULL,
        source_hash TEXT NOT NULL, sheet TEXT NOT NULL, cell TEXT NOT NULL,
        UNIQUE(source_hash,sheet,date,cell,event_type))""",
    """CREATE TABLE monthly_payroll (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
        employee_id TEXT REFERENCES employees(id), source_key TEXT NOT NULL, year INTEGER NOT NULL,
        month INTEGER NOT NULL, status TEXT NOT NULL, calculated_at TEXT NOT NULL, confirmed_at TEXT,
        UNIQUE(run_id,source_key))""",
    """CREATE TABLE monthly_payroll_items (
        payroll_id TEXT NOT NULL REFERENCES monthly_payroll(id) ON DELETE CASCADE,
        item_key TEXT NOT NULL, value TEXT, source_type TEXT NOT NULL, source_reference TEXT NOT NULL,
        source_value TEXT, previous_value TEXT, draft_value TEXT, user_override TEXT,
        user_confirmed INTEGER NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(payroll_id,item_key))""",
    """CREATE TABLE remembered_values (
        id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id), field_key TEXT NOT NULL,
        value TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT,
        reuse_policy TEXT NOT NULL CHECK(reuse_policy IN ('ALWAYS_SUGGEST','AUTO_REUSE','NEVER_REUSE','ONE_TIME')),
        confirmed_by TEXT NOT NULL, UNIQUE(employee_id,field_key,valid_from),
        CHECK(valid_to IS NULL OR valid_to >= valid_from))""",
    """CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, action TEXT NOT NULL, employee_id TEXT,
        year INTEGER, month INTEGER, old_value TEXT, new_value TEXT, source TEXT NOT NULL, actor TEXT NOT NULL)""",
    """CREATE TABLE processed_files (
        path TEXT PRIMARY KEY, modified_time INTEGER NOT NULL, hash TEXT NOT NULL, processed_at TEXT NOT NULL)""",
    """CREATE TABLE business_rules (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, match_key TEXT NOT NULL, scope TEXT NOT NULL,
        value TEXT NOT NULL, confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(kind,match_key,scope))""",
    """CREATE TABLE review_decisions (
        source_hash TEXT NOT NULL, issue_key TEXT NOT NULL, decision TEXT NOT NULL,
        reason TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(source_hash,issue_key))""",
    """CREATE TABLE review_issues (
        run_id TEXT NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE, issue_key TEXT NOT NULL,
        employee_id TEXT, kind TEXT NOT NULL, critical INTEGER NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY(run_id,issue_key))""",
    """CREATE TABLE source_changes (
        id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES payroll_runs(id),
        old_hash TEXT NOT NULL, new_hash TEXT NOT NULL, difference TEXT NOT NULL,
        created_at TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0,
        UNIQUE(run_id,new_hash))""",
    """CREATE TABLE payroll_observations (
        employee_id TEXT NOT NULL REFERENCES employees(id), year INTEGER NOT NULL, month INTEGER NOT NULL,
        field_key TEXT NOT NULL, value TEXT, formula TEXT, source_path TEXT NOT NULL,
        source_hash TEXT NOT NULL, PRIMARY KEY(employee_id,year,month,field_key))""",
    """CREATE TABLE write_operations (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES payroll_runs(id), status TEXT NOT NULL,
        target TEXT NOT NULL, backup_path TEXT NOT NULL, backup_hash TEXT NOT NULL,
        result_hash TEXT, error TEXT, created_at TEXT NOT NULL, completed_at TEXT)""",
    """CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    "CREATE INDEX events_employee_date ON attendance_events(employee_id,date)",
    "CREATE INDEX audit_timestamp ON audit_log(timestamp)",
]), (2, [
    """CREATE TABLE recurring_value_effective (
        employee_id TEXT NOT NULL REFERENCES employees(id), field_key TEXT NOT NULL,
        value TEXT NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT,
        scope TEXT NOT NULL CHECK(scope IN ('CURRENT_MONTH','FROM_THIS_MONTH')),
        reason TEXT NOT NULL, confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(employee_id,field_key,effective_from,scope),
        CHECK(effective_to IS NULL OR effective_to >= effective_from))""",
    "CREATE INDEX recurring_value_lookup ON recurring_value_effective(employee_id,field_key,effective_from,effective_to)",
]), (3, [
    """CREATE TABLE employee_endings (
        employee_id TEXT PRIMARY KEY REFERENCES employees(id), last_year INTEGER NOT NULL,
        last_month INTEGER NOT NULL CHECK(last_month BETWEEN 1 AND 12), reason TEXT NOT NULL,
        confirmed_by TEXT NOT NULL, confirmed_at TEXT NOT NULL)""",
]), (4, [
    """CREATE TABLE automation_jobs (
        id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_hash TEXT NOT NULL,
        period_year INTEGER, period_month INTEGER CHECK(period_month IS NULL OR period_month BETWEEN 1 AND 12),
        job_type TEXT NOT NULL, context TEXT NOT NULL, state TEXT NOT NULL
            CHECK(state IN ('PENDING','PROCESSING','REVIEW_REQUIRED','COMPLETED','FAILED')),
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0, failure_code TEXT, failure_message TEXT,
        payroll_run_id TEXT REFERENCES payroll_runs(id), write_operation_id TEXT REFERENCES write_operations(id),
        review_required INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT NOT NULL UNIQUE,
        worker_instance_id TEXT, claimed_at TEXT, updated_at TEXT NOT NULL)""",
    "CREATE INDEX automation_jobs_state_updated ON automation_jobs(state,updated_at DESC)",
    "CREATE INDEX automation_jobs_run_state ON automation_jobs(payroll_run_id,state)",
    """CREATE TABLE automation_job_failures (
        id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES automation_jobs(id) ON DELETE CASCADE,
        attempt_count INTEGER NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE INDEX automation_job_failures_job ON automation_job_failures(job_id,id DESC)",
])]
