from app.db.database import Database
from app.db.repositories import Repository


def test_effective_recurring_value_can_apply_once_or_from_month_onward(workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'effective.db'))
    employee = repo.create_employee('effective value test')
    repo.set_recurring_value(employee, 'base', 19360, 2026, 9, apply='FROM_THIS_MONTH', reason='initial value')
    repo.set_recurring_value(employee, 'base', 20000, 2026, 10, apply='CURRENT_MONTH', reason='October adjustment')
    assert repo.recurring_value(employee, 'base', 2026, 9)['value'] == '19360'
    assert repo.recurring_value(employee, 'base', 2026, 10)['value'] == '20000'
    assert repo.recurring_value(employee, 'base', 2026, 11)['value'] == '19360'
    repo.set_recurring_value(employee, 'base', 20000, 2026, 10, apply='FROM_THIS_MONTH', reason='permanent adjustment')
    assert repo.recurring_value(employee, 'base', 2026, 9)['value'] == '19360'
    assert repo.recurring_value(employee, 'base', 2026, 10)['value'] == '20000'
    assert repo.recurring_value(employee, 'base', 2026, 11)['value'] == '20000'
