from app.services.automation_job_service import AutomationJobService
from app.services.automation_runtime import AutomationRuntime
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.problems_model import ProblemsViewModel
from app.ui.problems_page import ProblemsPage
from app.excel.workbook_source import file_hash
from tests.unit.test_ui import qt_app, draft_case


def _failed_job(service, source):
    source.write_bytes(b'synthetic source')
    jobs = AutomationJobService(service.repo)
    job, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'synthetic'})
    jobs.claim_pending(job['id'], 'test-worker')
    return jobs.fail(job['id'], 'SOURCE_MISSING', 'synthetic missing-source failure')


def test_problems_page_binds_bounded_jobs_filters_and_stable_selection(qt_app, draft_case, workbook_workspace):
    service = PayrollService(draft_case[0])
    failed = _failed_job(service, workbook_workspace / 'failed.xlsx')
    page = ProblemsPage(ProblemsViewModel(service))

    assert page.table.rowCount() == 1
    page.filter.setCurrentIndex(page.filter.findData('FAILED'))
    page.table.selectRow(0)
    selected = []
    page.job_selected.connect(selected.append)
    page.open_current()

    assert selected == [failed['id']]
    assert 'พบงานที่มีปัญหา' in page.cards['jobs'][1].text()


def test_problems_navigation_is_read_only_and_never_creates_watcher(qt_app, draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    runtime = AutomationRuntime(service, qt_app)
    window = MainWindow(service, runtime=runtime)

    window.navigate_to('problems')

    assert window.page_host.currentWidget() is window.problems_page
    assert runtime.watcher is None
    assert service.repo.setting('watch_enabled') is False
    window.close()


def test_problem_detail_keeps_persisted_job_identity_and_safe_source_name(qt_app, draft_case, workbook_workspace):
    service = PayrollService(draft_case[0])
    failed = _failed_job(service, workbook_workspace / 'private-source.xlsx')
    before = AutomationJobService(service.repo).get(failed['id'])
    window = MainWindow(service)

    window.navigate_to('problems')
    window._problem_job_selected(failed['id'])

    assert window.page_host.currentWidget() is window.problem_detail_page
    assert window.problem_detail_page.values['source'].text() == 'private-source.xlsx'
    assert str(workbook_workspace) not in window.problem_detail_page.values['source'].text()
    assert AutomationJobService(service.repo).get(failed['id']) == before
    window.close()
