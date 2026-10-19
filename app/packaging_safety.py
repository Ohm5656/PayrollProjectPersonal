"""Deterministic, private-data-free staging for the Windows test candidate."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import argparse
import json
import shutil
from uuid import uuid4


CANDIDATE_NAME = 'NTP Payroll Assistant - Test Candidate'
CANDIDATE_EXE = f'{CANDIDATE_NAME}.exe'
ALLOWED_TOP_LEVEL = {CANDIDATE_EXE, '_internal'}
PROHIBITED_PARTS = {
    'test_workspace', 'reference_data', 'reports', 'logs', 'backups',
    '_staging', 'staging', 'recovery', 'qa_sessions', 'app_state',
}
PROHIBITED_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.wal', '.shm', '.log', '.jsonl', '.bak', '.xlsx', '.xlsm', '.xls'}


class PackagingSafetyError(RuntimeError):
    pass


def _inside(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def _prohibited(relative: Path) -> bool:
    parts = {part.casefold() for part in relative.parts}
    return bool(parts & PROHIBITED_PARTS) or relative.suffix.casefold() in PROHIBITED_SUFFIXES


def _validate_payload_item(path: Path, root: Path) -> list[Path]:
    if path.is_symlink() or not _inside(path, root):
        raise PackagingSafetyError(f'Payload link escapes staging root: {path}')
    files = []
    for value in path.rglob('*') if path.is_dir() else (path,):
        if value.is_symlink() or not _inside(value, root):
            raise PackagingSafetyError(f'Payload link escapes staging root: {value}')
        if value.is_file():
            relative = value.relative_to(root)
            if _prohibited(relative):
                raise PackagingSafetyError(f'Prohibited payload file: {relative}')
            files.append(value)
    return files


def validate_payload(stage: Path) -> list[Path]:
    """Require an exact PyInstaller onedir allowlist and no generated data."""
    raw_stage = Path(stage)
    if raw_stage.is_symlink():
        raise PackagingSafetyError('Installer staging directory must not be a link')
    stage = raw_stage.resolve()
    if not stage.is_dir():
        raise PackagingSafetyError('Installer staging directory must be a real directory')
    names = {entry.name for entry in stage.iterdir()}
    if names != ALLOWED_TOP_LEVEL:
        raise PackagingSafetyError(f'Installer staging must contain only {sorted(ALLOWED_TOP_LEVEL)}')
    exe = stage / CANDIDATE_EXE
    internal = stage / '_internal'
    if not exe.is_file() or not internal.is_dir():
        raise PackagingSafetyError('Installer staging is missing the EXE or _internal payload')
    return _validate_payload_item(exe, stage) + _validate_payload_item(internal, stage)


def stage_distribution(project_root: Path, distribution_path: Path | None = None) -> tuple[Path, Path, list[Path]]:
    """Copy only allowlisted build output into a fresh, never-overwritten stage."""
    project = Path(project_root).resolve()
    dist = Path(distribution_path).resolve() if distribution_path else project / 'dist' / CANDIDATE_NAME
    build = project / 'build'
    if not _inside(dist, project / 'dist') or not _inside(build, project):
        raise PackagingSafetyError('Build paths must remain inside the project workspace')
    if not dist.is_dir():
        raise PackagingSafetyError('Candidate distribution directory is missing')
    exe, internal = dist / CANDIDATE_EXE, dist / '_internal'
    if not exe.is_file() or not internal.is_dir():
        raise PackagingSafetyError('Candidate distribution is incomplete')
    # Validate selected inputs before copying. Extra runtime state beside the
    # distribution is intentionally not copied and cannot enter the payload.
    _validate_payload_item(exe, dist)
    _validate_payload_item(internal, dist)
    stage = build / 'installer-staging' / uuid4().hex
    manifest = build / 'installer-manifests' / f'{stage.name}.json'
    if stage.exists() or manifest.exists():
        raise PackagingSafetyError('Refusing to overwrite an existing staging result')
    stage.mkdir(parents=True)
    shutil.copy2(exe, stage / exe.name)
    shutil.copytree(internal, stage / internal.name, symlinks=False)
    files = validate_payload(stage)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    evidence = [
        {'path': str(file.relative_to(stage)).replace('\\', '/'), 'size': file.stat().st_size,
         'sha256': sha256(file.read_bytes()).hexdigest()}
        for file in sorted(files)
    ]
    manifest.write_text(json.dumps({'stage': str(stage), 'files': evidence}, indent=2) + '\n', encoding='utf-8')
    return stage, manifest, files


def _main() -> int:
    parser = argparse.ArgumentParser(description='Prepare a verified installer payload')
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--distribution-path')
    args = parser.parse_args()
    stage, manifest, files = stage_distribution(Path(args.project_root), args.distribution_path)
    print(json.dumps({'stage': str(stage), 'manifest': str(manifest), 'files': len(files)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
