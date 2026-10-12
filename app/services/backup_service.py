from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
from io import BytesIO

from app.excel.workbook_source import file_hash
from app.safety import SafetyError, development_target


@dataclass(frozen=True)
class Backup:
    path: Path
    sha256: str


class BackupService:
    def __init__(self, root):
        self.root = Path(root)

    def create(self, target, content, year, month):
        with ZipFile(BytesIO(content)) as archive:
            if archive.testzip() or 'xl/workbook.xml' not in archive.namelist():
                raise SafetyError('Backup source is not a valid workbook package')
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid4().hex[:8] + '_' + target.name
        path = development_target(self.root / f'{year:04}-{month:02}' / name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)
            stream.flush()
        digest = sha256(content).hexdigest()
        if not path.is_file() or file_hash(path) != digest:
            raise SafetyError('Backup verification failed; write is forbidden')
        return Backup(path, digest)
