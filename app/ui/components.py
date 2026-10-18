"""Small reusable presentation components for the desktop shell."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class NavigationButton(QPushButton):
    """Accessible, checkable sidebar button with text-based active state."""
    def __init__(self, page_id, label, parent=None):
        super().__init__(label, parent)
        self.page_id = page_id
        self.setCheckable(True)
        self.setProperty('role', 'navigation')
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setFocusPolicy(Qt.StrongFocus)


class PageHeader(QWidget):
    def __init__(self, title='', subtitle='', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setProperty('role', 'pageTitle')
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty('role', 'supporting')
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def set_content(self, title, subtitle=''):
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))


class StatusBadge(QFrame):
    """Text-first state indicator; semantic meaning never depends on colour."""
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setProperty('role', 'section')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        return self.label.text()


class SectionContainer(QFrame):
    def __init__(self, title='', parent=None):
        super().__init__(parent)
        self.setProperty('role', 'section')
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setProperty('role', 'sectionTitle')
            self.layout.addWidget(label)

    def addWidget(self, widget, stretch=0, alignment=Qt.Alignment()):
        self.layout.addWidget(widget, stretch, alignment)
