"""Stable byte snapshots: read saved XLSX files without interacting with Excel."""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile

from openpyxl import load_workbook


class WorkbookReadError(ValueError):
    pass


def discover_workbooks(folder: Path) -> list[Path]:
    folder = Path(folder).resolve(strict=True)
    return sorted((p for p in folder.rglob('*')
                   if p.is_file() and p.suffix.lower() == '.xlsx'
                   and not p.name.startswith('~$')), key=lambda p: p.as_posix())


def filename_month(path: Path) -> int:
    matches = re.findall(r'เดือน\s*(\d{1,2})(?!\d)', path.stem)
    if len(matches) != 1 or not 1 <= int(matches[0]) <= 12:
        raise WorkbookReadError(f'Cannot determine a unique month from {path.name}')
    return int(matches[0])


def file_hash(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return sha256(stream.read()).hexdigest()


@dataclass(frozen=True)
class WorkbookSnapshot:
    path: Path
    content: bytes
    sha256: str
    modified_ns: int

    @classmethod
    def read(cls, path: Path):
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() != '.xlsx' or path.name.startswith('~$'):
            raise WorkbookReadError('Only saved .xlsx workbooks are supported')
        before = path.stat()
        try:
            content = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            raise WorkbookReadError(f'Workbook cannot be safely read: {path.name}') from exc
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise WorkbookReadError('Workbook changed during reading; retry after Save settles')
        return cls(path, content, sha256(content).hexdigest(), after.st_mtime_ns)

    @contextmanager
    def open(self):
        """Both views come from identical bytes. Cached formulas are not recalculated."""
        books = []
        try:
            for data_only in (False, True):
                books.append(load_workbook(BytesIO(self.content), data_only=data_only,
                                           read_only=False, keep_links=True))
            yield tuple(books)
        except (BadZipFile, KeyError, OSError) as exc:
            raise WorkbookReadError(f'Invalid XLSX package: {self.path.name}') from exc
        finally:
            for book in books:
                book.close()


def safe_output_path(path: Path, reference_root: Path) -> Path:
    """Resolve links before enforcing the read-only reference boundary."""
    path = Path(path).resolve()
    reference_root = Path(reference_root).resolve()
    if path == reference_root or reference_root in path.parents:
        raise ValueError('reference_data is read-only; output must be elsewhere')
    if path.suffix.lower() == '.xlsx':
        raise ValueError('Analysis and parser commands never write XLSX workbooks')
    return path
