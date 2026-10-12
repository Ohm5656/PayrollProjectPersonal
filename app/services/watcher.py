"""Saved XLSX events, bounded settling retries, content idempotency and clean stop."""
from pathlib import Path
from threading import Condition, Thread
from time import monotonic
from io import BytesIO
from zipfile import ZipFile
import logging

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from app.excel.workbook_source import WorkbookSnapshot
from app.safety import development_target


class AttendanceWatcher(FileSystemEventHandler):
    def __init__(self, path, process, *, notify=lambda message: None, on_result=lambda result: None,
                 initial_hash=None, debounce=.8, settle=.25, max_retries=5, snapshot=WorkbookSnapshot.read):
        self.path = development_target(Path(path))
        self.process, self.notify, self.on_result = process, notify, on_result
        self.last_hash = initial_hash
        self.debounce, self.settle, self.max_retries = debounce, settle, max_retries
        self.snapshot = snapshot
        self.condition = Condition()
        self.deadline = None
        self.stopping = False
        self.observer = None
        self.thread = None
        self.failed_signature = None

    def queue(self, path):
        path = Path(path)
        if path.name.startswith('~$') or path.suffix.lower() != '.xlsx' or path.resolve() != self.path:
            return
        with self.condition:
            if not self.stopping:
                self.deadline = monotonic() + self.debounce
                self.condition.notify_all()

    def on_modified(self, event):
        if not event.is_directory: self.queue(event.src_path)

    on_created = on_modified

    def on_moved(self, event):
        if not event.is_directory: self.queue(event.dest_path)

    def start(self, *, observe=True):
        if self.thread: return
        self.thread = Thread(target=self._run, name='NTP attendance watcher', daemon=True)
        self.thread.start()
        if observe:
            self.observer = Observer()
            self.observer.schedule(self, str(self.path.parent), recursive=False)
            self.observer.start()
        self.queue(self.path)

    def _pause(self, duration):
        with self.condition:
            self.condition.wait_for(lambda: self.stopping, timeout=duration)
            return self.stopping

    def _process(self):
        for attempt in range(self.max_retries):
            if self.stopping: return
            try:
                before = self.path.stat()
                if self._pause(self.settle): return
                after = self.path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise OSError('File is still being saved')
                saved = self.snapshot(self.path)
                with ZipFile(BytesIO(saved.content)) as package:
                    if package.testzip() or '[Content_Types].xml' not in package.namelist():
                        raise OSError('Incomplete XLSX package')
                if saved.sha256 == self.last_hash: return
                result = self.process(self.path)
                # Do not mark a newer save as processed when the parser used
                # different bytes. Protected results carry the observed hash.
                parsed_hash = result.get('difference', {}).get('new_hash') or result['draft'].source_hash
                if parsed_hash != saved.sha256:
                    raise OSError('Source changed during processing')
                self.last_hash = saved.sha256
                self.failed_signature = None
                self.on_result(result)
                return
            except Exception as exc:
                if attempt + 1 < self.max_retries:
                    if self._pause(min(.15 * 2**attempt, 2)): return
                else:
                    signature = (type(exc).__name__, str(exc))
                    logging.getLogger('ntp').exception('Attendance processing failed after bounded retries')
                    if signature != self.failed_signature:
                        self.failed_signature = signature
                        self.notify('อ่านไฟล์บันทึกเวลาไม่สำเร็จ กรุณาบันทึกไฟล์แล้วลองใหม่: ' + str(exc))

    def _run(self):
        while True:
            with self.condition:
                while not self.stopping:
                    if self.deadline is None:
                        self.condition.wait()
                    elif self.deadline > monotonic():
                        self.condition.wait(self.deadline-monotonic())
                    else:
                        self.deadline = None
                        break
                if self.stopping: return
            self._process()

    def stop(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        if self.thread:
            self.thread.join(timeout=30)
            return not self.thread.is_alive()
        return True
