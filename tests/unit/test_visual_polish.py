from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.services.payroll_service import PayrollService
from app.ui.components import SectionContainer, StatusBadge
from app.ui.main_window import MainWindow
from app.ui.theme import FONT_FAMILIES, stylesheet
from tests.unit.test_ui import qt_app, draft_case


def test_shared_theme_keeps_thai_font_fallback_and_table_states():
    css = stylesheet()
    assert FONT_FAMILIES[:3] == ('Segoe UI', 'Leelawadee UI', 'Tahoma')
    assert 'QTableWidget::item:selected' in css
    assert 'QGroupBox' in css


def test_status_and_long_thai_section_titles_are_accessible(qt_app):
    title = 'รายละเอียดการตรวจสอบรายการเงินเดือนและข้อควรดำเนินการเพิ่มเติมสำหรับผู้ใช้งาน'
    section = SectionContainer(title)
    section.addWidget(QLabel('ข้อความทดสอบ'))
    badge = StatusBadge('สถานะการประมวลผลรอบเงินเดือน')

    assert section.title.wordWrap()
    assert badge.accessibleName() == 'สถานะการประมวลผลรอบเงินเดือน'
    section.close(); badge.close()


def test_shell_layout_remains_reachable_at_supported_offscreen_viewports(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))
    window.show()
    for width, height in ((1920, 1080), (1366, 768), (1024, 768), (900, 700)):
        window.resize(width, height)
        qt_app.processEvents()
        assert window.sidebar.width() >= 180
        assert window.period_context.width() > 0
        assert window.overview_page.primary_action.width() > 0
        assert window.table.horizontalHeader().isVisible()
        assert window.navigation_buttons['overview'].focusPolicy() == Qt.StrongFocus
    window.close()
