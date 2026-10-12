"""Logical workbook preservation, not byte equality after Excel serialization."""
from copy import copy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET

from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

from app.excel.workbook_source import WorkbookSnapshot
from app.safety import SafetyError


def formula_text(value):
    if isinstance(value, ArrayFormula):
        return ('array', value.ref, value.text)
    if isinstance(value, DataTableFormula):
        return ('data_table', tuple(value))
    return value


def xml(value):
    return ET.tostring(copy(value).to_tree(), encoding='unicode')


@dataclass(frozen=True)
class WorkbookStructure:
    sheets: tuple
    cells: dict
    formulas: dict
    settings: dict

    @classmethod
    def read(cls, path):
        with WorkbookSnapshot.read(path).open() as (book, _):
            cells, formulas, settings = {}, {}, {}
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        if cell.value is not None or cell.has_style:
                            cells[(sheet.title, cell.coordinate)] = (
                                xml(cell.font), xml(cell.fill), xml(cell.border), xml(cell.alignment),
                                xml(cell.protection), cell.number_format)
                        if cell.data_type == 'f':
                            formulas[(sheet.title, cell.coordinate)] = formula_text(cell.value)
                settings[sheet.title] = {
                    'state': sheet.sheet_state, 'merges': tuple(sorted(map(str, sheet.merged_cells.ranges))),
                    'rows': {k: (d.height, d.hidden, d.outlineLevel, d.collapsed) for k, d in sheet.row_dimensions.items()},
                    'columns': {k: (d.width, d.hidden, d.min, d.max, d.outlineLevel, d.collapsed) for k, d in sheet.column_dimensions.items()},
                    'print_area': str(sheet.print_area), 'print_rows': sheet.print_title_rows,
                    'print_columns': sheet.print_title_cols, 'page_setup': xml(sheet.page_setup),
                    'margins': xml(sheet.page_margins), 'print_options': xml(sheet.print_options),
                    'freeze_panes': sheet.freeze_panes,
                }
            return cls(tuple(book.sheetnames), cells, formulas, settings)

    def validate(self, after):
        if self.sheets != after.sheets:
            raise SafetyError('Workbook sheet names/count/order changed')
        if self.formulas != after.formulas:
            changed = [key for key in self.formulas.keys() | after.formulas.keys()
                       if self.formulas.get(key) != after.formulas.get(key)]
            raise SafetyError(f'Workbook formulas changed at {changed[:4]}')
        for key, style in self.cells.items():
            if after.cells.get(key) != style:
                raise SafetyError(f'Workbook cell formatting changed at {key}')
        if self.settings != after.settings:
            changed = [(sheet, key) for sheet in self.settings for key in self.settings[sheet]
                       if self.settings[sheet][key] != after.settings.get(sheet, {}).get(key)]
            raise SafetyError(f'Workbook layout/print settings changed at {changed[:4]}')


def equivalent(a, b):
    if a is None or b is None:
        return a == b
    try:
        left, right = Decimal(str(a)), Decimal(str(b))
        return left.is_finite() and right.is_finite() and abs(left - right) <= max(Decimal('0.0000001'), abs(right) * Decimal('0.000000000001'))
    except Exception:
        return a == b


def validate_expected(path, expected):
    with WorkbookSnapshot.read(path).open() as (_, values):
        for sheet, address, wanted in expected:
            actual = values[sheet][address].value
            if not equivalent(actual, wanted):
                raise SafetyError(f'Written/recalculated value failed validation: {sheet}!{address}')
