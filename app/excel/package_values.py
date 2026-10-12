"""Transfer Excel-calculated values into the unchanged original XLSX package.

Excel Save can normalize colors, fonts and column widths. Preserve every
original package part and patch only intended input values + existing formula
caches. No openpyxl save, worksheet regeneration, style or formula replacement.
"""
from io import BytesIO
from pathlib import PurePosixPath
import re
from uuid import uuid4
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from app.safety import SafetyError, development_target

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
CELL = re.compile(r'<c\b[^>]*?/>|<c\b[^>]*?>.*?</c>', re.S)
VALUE = re.compile(r'<v(?:\s[^>]*)?>.*?</v>|<v(?:\s[^>]*)?\s*/>', re.S)
INLINE = re.compile(r'<is(?:\s[^>]*)?>.*?</is>', re.S)


def sheet_parts(archive):
    relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    paths = {r.attrib['Id']: r.attrib['Target'] for r in relationships}
    result = {}
    for sheet in ET.fromstring(archive.read('xl/workbook.xml')).find('s:sheets', NS):
        target = paths[sheet.attrib['{' + NS['r'] + '}id']]
        path = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
        if '..' in PurePosixPath(path).parts:
            raise SafetyError('Unsupported workbook relationship path')
        result[sheet.attrib['name']] = path
    return result


def shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    return [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))]


def cell_values(content):
    root = ET.fromstring(content)
    return {c.attrib['r']: c for c in root.findall('.//s:sheetData/s:row/s:c', NS)}


def preserve_package_values(original, excel_path, writes):
    excel_path = development_target(excel_path)
    replacement = development_target(excel_path.with_name(uuid4().hex + '_values.xlsx'))
    intended = {(w.sheet, w.address) for w in writes}
    with ZipFile(BytesIO(original)) as source, ZipFile(excel_path) as calculated:
        source_sheets, new_sheets = sheet_parts(source), sheet_parts(calculated)
        if set(source_sheets) != set(new_sheets):
            raise SafetyError('Excel changed worksheet membership')
        strings = shared_strings(calculated)
        patched = {}
        seen = set()
        for title, part in source_sheets.items():
            raw = source.read(part).decode('utf-8')
            old_cells = cell_values(raw)
            new_cells = cell_values(calculated.read(new_sheets[title]))
            matched = set()
            def patch(match):
                text = match.group(0)
                address_match = re.search(r'\br=("|\')([^"\']+)\1', text.split('>', 1)[0])
                if not address_match:
                    raise SafetyError('Cannot safely locate source cell reference')
                address = address_match.group(2)
                matched.add(address)
                old = old_cells[address]
                formula = old.find('s:f', NS)
                is_input = (title, address) in intended
                if formula is not None and is_input:
                    raise SafetyError('An original formula cannot be replaced by an input value')
                if not is_input and formula is None:
                    return text
                new = new_cells.get(address)
                if new is None:
                    if is_input:
                        raise SafetyError('Excel did not save an intended input')
                    return text
                if formula is not None:
                    after_formula = new.find('s:f', NS)
                    if after_formula is None or formula.text != after_formula.text or formula.attrib != after_formula.attrib:
                        raise SafetyError('An original formula changed during Excel recalculation')
                value = new.find('s:v', NS)
                value_type = new.attrib.get('t')
                value_text = value.text if value is not None else None
                if value_type == 's':
                    value_text = strings[int(value_text)]
                    value_type = 'str'
                elif value_type == 'inlineStr':
                    value_text = ''.join(new.find('s:is', NS).itertext())
                    value_type = 'str'
                if is_input:
                    seen.add((title, address))
                if text.endswith('/>'):
                    head, body = text[:-2] + '>', ''
                else:
                    head, rest = text.split('>', 1)
                    head += '>'
                    body = rest[:-4]
                head = re.sub(r'\s+t=("|\')[^"\']*\1', '', head)
                if value_type and value_type != 'n':
                    head = head[:-1] + ' t="' + value_type + '">'
                body = VALUE.sub('', body)
                if formula is None:
                    body = INLINE.sub('', body)
                updated = '<v>' + escape(value_text or '') + '</v>' if value_text is not None else ''
                return head + body + updated + '</c>'
            result = CELL.sub(patch, raw)
            if matched != old_cells.keys():
                raise SafetyError('Source XML cell syntax cannot be patched without ambiguity')
            missing = [address for sheet,address in intended-seen if sheet == title]
            if missing:
                root = ET.fromstring(raw)
                dimension = root.find('s:dimension', NS)
                if dimension is None: raise SafetyError('Template bounds are missing')
                min_col,min_row,max_col,max_row = range_boundaries(dimension.attrib['ref'])
                merges = [range_boundaries(node.attrib['ref']) for node in root.findall('s:mergeCells/s:mergeCell',NS)]
                additions = {}
                for address in missing:
                    row,column = coordinate_to_tuple(address)
                    if not (min_row<=row<=max_row and min_col<=column<=max_col):
                        raise SafetyError('Approved input falls outside existing template bounds')
                    if any(c1<=column<=c2 and r1<=row<=r2 for c1,r1,c2,r2 in merges):
                        raise SafetyError('Cannot add an input inside a merged region')
                    new = new_cells.get(address)
                    if new is None or new.find('s:f',NS) is not None:
                        raise SafetyError('Calculated input is missing or became a formula')
                    value = new.find('s:v',NS)
                    if value is None or new.attrib.get('t') not in (None,'n'):
                        raise SafetyError('New blank-template input must be a saved numeric value')
                    # An absent cell has no explicit style to preserve. Keep the
                    # existing row/column defaults; add only its numeric value.
                    additions.setdefault(row,[]).append((column,address,'<c r="'+address+'"><v>'+escape(value.text or '')+'</v></c>'))
                inserted = set()
                def insert_row(match):
                    text = match.group(0)
                    row_match = re.search(r'\br=["\'](\d+)["\']',text.split('>',1)[0])
                    if not row_match: raise SafetyError('Template row is ambiguous')
                    number = int(row_match[1])
                    if number not in additions: return text
                    for column,address,node in sorted(additions[number], reverse=True):
                        later = next((m for m in CELL.finditer(text) if coordinate_to_tuple(re.search(r'\br=["\']([^"\']+)["\']',m.group(0).split('>',1)[0])[1])[1]>column),None)
                        offset = later.start() if later else text.rfind('</row>')
                        if offset < 0: raise SafetyError('Cannot expand a missing template row')
                        text = text[:offset]+node+text[offset:]
                        inserted.add((title,address))
                    return text
                result = re.sub(r'<row\b[^>]*>.*?</row>',insert_row,result,flags=re.S)
                if inserted != {(title,a) for a in missing}: raise SafetyError('Approved blank input lacks an existing row')
                seen.update(inserted)
            patched[part] = result.encode('utf-8')
        if seen != intended:
            raise SafetyError('An intended input lacks an existing template cell: ' + str(sorted(intended-seen)))
        with ZipFile(replacement, 'x') as output:
            output.comment = source.comment
            for info in source.infolist():
                output.writestr(info, patched.get(info.filename, source.read(info.filename)))
    replacement.replace(excel_path)
