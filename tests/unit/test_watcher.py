from pathlib import Path
from threading import Event
from types import SimpleNamespace
from time import sleep
import shutil

from app.services.watcher import AttendanceWatcher
from app.services.watcher import AttendanceFolderWatcher
from app.excel.workbook_source import WorkbookSnapshot


def make_case(copied_reference, workbook_workspace):
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    target = workbook_workspace / source.name
    shutil.copy2(source, target)
    return target


def test_save_events_debounce_and_same_content_is_idempotent(copied_reference, workbook_workspace):
    path = make_case(copied_reference, workbook_workspace)
    done, calls = Event(), []
    def process(path):
        calls.append(path)
        return {'draft': SimpleNamespace(source_hash=WorkbookSnapshot.read(path).sha256)}
    watcher = AttendanceWatcher(path, process, debounce=.05, settle=.01, on_result=lambda r: done.set())
    watcher.start(observe=False)
    try:
        for _ in range(25): watcher.queue(path)
        watcher.queue(path.with_name('~$' + path.name))
        watcher.queue(path.with_name('other.xlsx'))
        assert done.wait(3)
        assert len(calls) == 1
        done.clear()
        for _ in range(25): watcher.queue(path)
        sleep(.25)
        assert not done.is_set() and len(calls) == 1
    finally:
        assert watcher.stop()


def test_locked_file_retries_are_bounded_and_notification_is_deduplicated(copied_reference, workbook_workspace):
    path = make_case(copied_reference, workbook_workspace)
    failures, messages, notified = [], [], Event()
    def fail(path):
        failures.append(path)
        raise PermissionError('temporarily locked')
    def notify(message):
        messages.append(message)
        notified.set()
    watcher = AttendanceWatcher(path, lambda _: None, snapshot=fail, notify=notify, max_retries=2, debounce=.01, settle=.001)
    watcher.start(observe=False)
    try:
        assert notified.wait(3)
        assert len(failures) == 2 and len(messages) == 1
        watcher.queue(path)
        sleep(.4)
        assert len(failures) == 4 and len(messages) == 1
    finally:
        assert watcher.stop()


def test_protected_month_uses_observed_changed_hash(copied_reference, workbook_workspace):
    path = make_case(copied_reference, workbook_workspace)
    new = WorkbookSnapshot.read(path).sha256
    completed, calls = Event(), []
    def process(path):
        calls.append(path)
        return {'draft': SimpleNamespace(source_hash='finalized-old'), 'difference': {'new_hash': new}}
    watcher = AttendanceWatcher(path, process, initial_hash='finalized-old', debounce=.01, settle=.001,
                                on_result=lambda r: completed.set())
    watcher.start(observe=False)
    try:
        assert completed.wait(3)
        watcher.queue(path)
        sleep(.2)
        assert len(calls) == 1 and watcher.last_hash == new
    finally: assert watcher.stop()


def test_actual_watchdog_observes_atomic_save(copied_reference, workbook_workspace):
    path = make_case(copied_reference, workbook_workspace)
    done = Event()
    watcher = AttendanceWatcher(path, lambda p: {'draft': SimpleNamespace(source_hash=WorkbookSnapshot.read(p).sha256)},
                                on_result=lambda r: done.set(), debounce=.04, settle=.01)
    watcher.start()
    try:
        assert done.wait(3)
        done.clear()
        # A ZIP comment is a real content change without altering cell values.
        from zipfile import ZipFile
        replacement = path.with_name('saved.xlsx')
        shutil.copy2(path, replacement)
        with ZipFile(replacement, 'a') as book: book.comment = b'controlled saved copy'
        replacement.replace(path)
        assert done.wait(5)
    finally: assert watcher.stop()


def test_folder_watcher_accepts_only_saved_xlsx_in_approved_folder(copied_reference, workbook_workspace):
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    folder = workbook_workspace / 'attendance'
    folder.mkdir()
    target = folder / source.name
    shutil.copy2(source, target)
    done, calls = Event(), []
    watcher = AttendanceFolderWatcher(folder, lambda p: (calls.append(p) or {'draft': SimpleNamespace(source_hash=WorkbookSnapshot.read(p).sha256)}),
                                      debounce=.01, settle=.001, on_result=lambda _: done.set())
    watcher.start(observe=False)
    try:
        watcher.queue(folder / ('~$' + source.name))
        watcher.queue(workbook_workspace / 'other.xlsx')
        watcher.queue(target)
        assert done.wait(3)
        assert calls == [target.resolve()]
    finally:
        assert watcher.stop()
