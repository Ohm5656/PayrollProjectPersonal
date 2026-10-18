from PySide6.QtWidgets import QLabel

from app.ui.components import NavigationButton, PageHeader, SectionContainer, StatusBadge
from app.ui.theme import FONT_FAMILIES, TOKENS, apply_theme, stylesheet
from tests.unit.test_ui import qt_app


def test_theme_tokens_and_stylesheet_are_centralized(qt_app):
    assert TOKENS['canvas'] == '#F6F8FB'
    assert TOKENS['primary'] == '#1E5AA8'
    assert 'Segoe UI' in FONT_FAMILIES
    apply_theme(qt_app)
    assert 'QMainWindow' in qt_app.styleSheet()
    assert TOKENS['focus'] in qt_app.styleSheet()
    assert stylesheet() == qt_app.styleSheet()


def test_shell_components_construct_with_thai_text(qt_app):
    nav = NavigationButton('overview', 'ภาพรวม')
    header = PageHeader('ภาพรวม', 'ข้อมูลจะแสดงเมื่อย้ายใน Phase D.2')
    badge = StatusBadge('สถานะ: ยังไม่ได้ย้ายข้อมูล')
    section = SectionContainer('ส่วนทดสอบ')
    section.addWidget(QLabel('ข้อความภาษาไทย'))

    assert nav.isCheckable() and nav.accessibleName() == 'ภาพรวม'
    assert header.title.text() == 'ภาพรวม'
    assert badge.text().startswith('สถานะ:')
    assert section.property('role') == 'section'
