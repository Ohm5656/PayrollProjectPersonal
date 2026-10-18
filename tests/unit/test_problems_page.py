from app.services.automation_job_service import AutomationJobService
from app.services.automation_runtime import AutomationRuntime
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.problems_model import ProblemsViewModel
from app.ui.problems_page import ProblemsPage
from app.ui.problems_detail_page import StagedWriteInspectionPage
from app.excel.workbook_source import file_hash
from tests.unit.test_ui import qt_app, draft_case
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QHeaderView


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


def test_retry_is_explicit_and_routes_only_through_runtime(qt_app, draft_case, workbook_workspace, monkeypatch):
    service = PayrollService(draft_case[0])
    failed = _failed_job(service, workbook_workspace / 'retry.xlsx')
    runtime = AutomationRuntime(service, qt_app)
    calls = []
    monkeypatch.setattr(runtime, 'retry_eligibility', lambda job_id: (True, '') if job_id == failed['id'] else (False, 'missing'))
    monkeypatch.setattr(runtime, 'retry_job', lambda job_id: calls.append(job_id) or {'retried': False})
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window = MainWindow(service, runtime=runtime)
    monkeypatch.setattr(window, 'work', lambda task, success: success(task()))

    window._problem_job_selected(failed['id'])
    assert window.problem_detail_page.retry.isEnabled()
    window.problem_detail_page.retry.click()

    assert calls == [failed['id']]
    assert runtime.watcher is None
    window.close()


def test_changed_source_retry_result_is_not_presented_as_success(qt_app, draft_case, workbook_workspace):
    service = PayrollService(draft_case[0])
    failed = _failed_job(service, workbook_workspace / 'changed.xlsx')
    runtime = AutomationRuntime(service, qt_app)
    window = MainWindow(service, runtime=runtime)

    window._retry_problem_finished(failed['id'], {'retried': False, 'changed_source_job': {'state': 'PENDING'}})

    assert 'ยังไม่ได้ยืนยันว่าประมวลผลสำเร็จ' in window.statusBar().currentMessage()
    window.close()


def test_staged_write_page_is_read_only_and_problems_layout_is_usable_offscreen(qt_app, draft_case):
    page = StagedWriteInspectionPage()
    page.refresh(({'operation_id': 'synthetic', 'target_exists': False, 'backup_valid': True,
                   'classification': 'STAGED_REQUIRES_REVIEW'},))
    assert page.table.rowCount() == 1
    assert 'ตรวจสอบด้วยตนเอง' in page.state.text()

    window = MainWindow(PayrollService(draft_case[0]))
    window.show(); window.navigate_to('problems')
    for width, height in ((1366, 768), (1920, 1080), (900, 700)):
        window.resize(width, height); qt_app.processEvents()
        assert window.problems_page.table.isVisible()
        assert window.problems_page.table.width() > 0
        assert window.problems_page.refresh_button.focusPolicy()
    window.close()


def test_problems_table_stretches_detail_column(qt_app, draft_case):
    page = ProblemsPage(ProblemsViewModel(PayrollService(draft_case[0])))

    header = page.table.horizontalHeader()
    assert header.sectionResizeMode(1) is QHeaderView.Stretch
    assert header.minimumSectionSize() >= 96
