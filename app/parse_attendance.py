"""Developer-only parser entry point. The desktop UI is a later phase."""
from dataclasses import asdict
from pathlib import Path
import argparse
import json

from app.analysis.historical import _json_default
from app.excel.attendance_reader import read_attendance
from app.excel.workbook_source import safe_output_path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Read saved attendance XLSX without opening Excel')
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--year', type=int)
    parser.add_argument('--month', type=int)
    parser.add_argument('--output', type=Path, required=True, help='Local JSON evidence output')
    args = parser.parse_args()
    output = safe_output_path(args.output, root / 'reference_data')
    if output.suffix.lower() != '.json':
        parser.error('--output must be a .json file')
    result = read_attendance(args.workbook, year=args.year, month=args.month)
    content = json.dumps(asdict(result), ensure_ascii=False, indent=2, default=_json_default) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding='utf-8')
    print(f'Parsed {len(result.employees)} sheets for {result.year}-{result.month:02}; '
          f'{sum(e.requires_review for e in result.employees)} sheets require source review.')


if __name__ == '__main__':
    main()
