"""Classify historical differences without creating business rules to fit them."""
from collections import Counter
from pathlib import Path
import json

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import encode
from app.excel.payroll_reader import PayrollWorkbookAdapter, TemplateError
from app.excel.workbook_source import filename_month, discover_workbooks
from app.services.history_service import import_history
from app.services.payroll_service import PayrollService
from app.safety import ROOT, development_target

CATEGORIES = {'MATCH', 'MANUAL_OVERRIDE', 'BUSINESS_EXCEPTION', 'UNKNOWN_RULE', 'PARSER_ERROR', 'TEMPLATE_DIFFERENCE'}


def compare_history(copies, database):
    repo = Repository(Database(development_target(database)))
    evidence = json.loads((ROOT/'reports/historical_analysis.json').read_text(encoding='utf-8'))
    import_history(repo, evidence, Path(copies))
    service = PayrollService(repo)
    attendance = {filename_month(p):p for p in discover_workbooks(Path(copies)/'attendance')}
    rows = []
    for path in discover_workbooks(Path(copies)/'payroll'):
        month = filename_month(path)
        try:
            payroll = PayrollWorkbookAdapter.read(path)
            draft = service.prepare(attendance[month],path,year=2026,month=month)['draft']
        except TemplateError as exc:
            rows.append({'month':month,'employee':None,'field':None,'category':'TEMPLATE_DIFFERENCE','reason':str(exc)})
            continue
        for employee in draft.employees:
            if not employee.employee_id:
                rows.append({'month':month,'employee':employee.name,'field':None,'category':'UNKNOWN_RULE','reason':'Unconfirmed identity; no fuzzy merge'})
                continue
            person = payroll.employee(employee.name)
            for field,value in employee.values.items():
                historical = person.cells[field].value
                source_errors = [i for i in employee.issues if i.critical and i.kind.startswith('SOURCE_')]
                if source_errors and field in {'travel','allowance','normal_ot','holiday_ot','holiday_days','bonus'}:
                    category, reason = 'PARSER_ERROR', 'Source validation errors require correction/review, not amount coercion'
                elif value.user_override is not None:
                    category, reason = 'MANUAL_OVERRIDE', value.reason
                elif value.final_value is None:
                    category, reason = 'UNKNOWN_RULE', 'No confirmed monthly value or deterministic business rule'
                elif value.final_value == historical:
                    category, reason = 'MATCH', 'Validated draft agrees with saved historical payroll'
                else:
                    category, reason = 'UNKNOWN_RULE', 'Saved historical amount differs; business exception not established'
                rows.append({'month':month,'employee':employee.name,'field':field,'category':category,
                             'historical':historical,'source':value.source_value,'draft':value.final_value,
                             'difference':value.final_value-historical if value.final_value is not None and historical is not None else None,
                             'reason':reason})
    return {'months':sorted(attendance),'categories':sorted(CATEGORIES),'counts':dict(Counter(r['category'] for r in rows)),
            'note':'BUSINESS_EXCEPTION is reserved for evidenced confirmed exceptions; mismatches alone do not prove one.', 'rows':rows}


def write_comparison(result, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(encode(result)+'\n', encoding='utf-8')
