from app.services.automation_runtime import RuntimeState


def test_phase_f_readiness_contract_does_not_resume_or_create_monitoring(workbook_workspace):
    from app.db.database import Database
    from app.db.repositories import Repository
    from app.services.readiness import ReadinessService
    from types import SimpleNamespace
    repo = Repository(Database(workbook_workspace / 'runtime.db'))
    workflow = SimpleNamespace(repo=repo, configuration=lambda: {})
    runtime = SimpleNamespace(state=RuntimeState.DISABLED)
    report = ReadinessService(workflow, runtime=runtime).assess()
    assert runtime.state == RuntimeState.DISABLED
    assert next(c for c in report.checks if c.id == 'MONITORING_STATE').status == 'PASS'
