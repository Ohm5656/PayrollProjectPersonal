from datetime import date
from uuid import uuid4
import json

from app.domain import ReusePolicy, decimal_value, encode, normalized_name, utc_now
from app.models import DayType


class Repository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def audit(con, action, *, employee_id=None, year=None, month=None, old=None, new=None,
              source='application', actor='user'):
        con.execute('INSERT INTO audit_log(timestamp,action,employee_id,year,month,old_value,new_value,source,actor) VALUES (?,?,?,?,?,?,?,?,?)',
                    (utc_now(), action, employee_id, year, month, encode(old), encode(new), source, actor))

    def create_employee(self, name, *, actor='user'):
        norm = normalized_name(name)
        if not norm:
            raise ValueError('Employee name is required')
        with self.db.transaction() as con:
            found = con.execute('SELECT id FROM employees WHERE name_norm=?', (norm,)).fetchone()
            if found:
                return found['id']
            eid = str(uuid4())
            con.execute('INSERT INTO employees VALUES (?,?,?,1,?,?)', (eid, name.strip(), norm, utc_now(), utc_now()))
            con.execute('INSERT INTO payroll_profiles(employee_id,updated_at) VALUES (?,?)', (eid, utc_now()))
            self.audit(con, 'EMPLOYEE_CREATED', employee_id=eid, new={'name': name}, actor=actor)
            return eid

    def employees(self):
        return self.db.query('SELECT * FROM employees ORDER BY canonical_name')

    def end_employee(self, eid, last_year, last_month, *, reason, actor='user'):
        """End employment after an explicitly confirmed payroll period.

        Historical payroll stays readable; later attendance is surfaced for
        review instead of silently being paid or erased.
        """
        if not self.db.query('SELECT id FROM employees WHERE id=?', (eid,)):
            raise ValueError('Unknown employee')
        if not isinstance(last_year, int) or not isinstance(last_month, int) or not 1 <= last_month <= 12:
            raise ValueError('Invalid final employment period')
        if not reason or not reason.strip():
            raise ValueError('A reason is required to end an employee')
        with self.db.transaction() as con:
            old = con.execute('SELECT * FROM employee_endings WHERE employee_id=?', (eid,)).fetchone()
            con.execute('INSERT INTO employee_endings VALUES (?,?,?,?,?,?) ON CONFLICT(employee_id) DO UPDATE SET '
                        'last_year=excluded.last_year,last_month=excluded.last_month,reason=excluded.reason,'
                        'confirmed_by=excluded.confirmed_by,confirmed_at=excluded.confirmed_at',
                        (eid, last_year, last_month, reason.strip(), actor, utc_now()))
            self.audit(con, 'EMPLOYEE_END_CONFIRMED', employee_id=eid, year=last_year, month=last_month,
                       old=dict(old) if old else None, new={'last_year': last_year, 'last_month': last_month, 'reason': reason}, actor=actor)

    def active_for_period(self, eid, year, month):
        ending = self.db.query('SELECT last_year,last_month FROM employee_endings WHERE employee_id=?', (eid,))
        return not ending or (year, month) <= (ending[0]['last_year'], ending[0]['last_month'])

    def confirm_alias(self, eid, alias, source, *, actor, reason):
        if not actor.strip() or not reason.strip() or not normalized_name(alias):
            raise ValueError('Explicit actor, alias and reason are required')
        with self.db.transaction() as con:
            old = con.execute('SELECT employee_id FROM employee_aliases WHERE alias_norm=? AND source=?',
                              (normalized_name(alias), source)).fetchone()
            canonical = con.execute('SELECT id FROM employees WHERE name_norm=?', (normalized_name(alias),)).fetchone()
            if (old and old['employee_id'] != eid) or (canonical and canonical['id'] != eid):
                raise ValueError('Alias conflicts with an existing employee; review instead of merging')
            con.execute('INSERT INTO employee_aliases(employee_id,alias,alias_norm,source,confirmed_by,created_at) VALUES (?,?,?,?,?,?) '
                        'ON CONFLICT(alias_norm,source) DO NOTHING',
                        (eid, alias, normalized_name(alias), source, actor, utc_now()))
            self.audit(con, 'ALIAS_CONFIRMED', employee_id=eid, new={'alias': alias, 'source': source, 'reason': reason}, actor=actor)

    def resolve(self, name, source='attendance_full'):
        norm = normalized_name(name)
        direct = self.db.query('SELECT id FROM employees WHERE name_norm=?', (norm,))
        aliases = self.db.query('SELECT employee_id AS id FROM employee_aliases WHERE alias_norm=? AND source=?', (norm, source))
        ids = {row['id'] for row in (*direct, *aliases)}
        return next(iter(ids)) if len(ids) == 1 else None

    def profile(self, eid):
        rows = self.db.query('SELECT * FROM payroll_profiles WHERE employee_id=?', (eid,))
        return rows[0] if rows else {}

    def confirm_profile(self, eid, *, actor='user', **fields):
        allowed = {'base_salary', 'attendance_bonus_default', 'phone_allowance', 'position_allowance', 'housing', 'attendance_required'}
        if set(fields) - allowed:
            raise ValueError('Unknown profile field')
        values = {k: int(v) if k == 'attendance_required' else str(decimal_value(v)) if v is not None else None
                  for k, v in fields.items()}
        with self.db.transaction() as con:
            old = dict(con.execute('SELECT * FROM payroll_profiles WHERE employee_id=?', (eid,)).fetchone())
            for key, value in values.items():
                con.execute(f'UPDATE payroll_profiles SET {key}=? WHERE employee_id=?', (value, eid))
            con.execute('UPDATE payroll_profiles SET confirmed=1,updated_at=? WHERE employee_id=?', (utc_now(), eid))
            self.audit(con, 'PROFILE_CONFIRMED', employee_id=eid, old=old, new=values, actor=actor)

    def confirm_calendar(self, day, kind, description, *, required_workday, affects_attendance_bonus=False,
                         scope='*', actor='user', source='user'):
        date.fromisoformat(str(day))
        kind = DayType(kind)
        if kind == DayType.UNKNOWN:
            raise ValueError('UNKNOWN calendar entries cannot be confirmed')
        if scope != '*' and not self.db.query('SELECT id FROM employees WHERE id=?', (scope,)):
            raise ValueError('Unknown calendar scope')
        with self.db.transaction() as con:
            old = con.execute('SELECT * FROM company_calendar WHERE date=? AND scope=?', (str(day), scope)).fetchone()
            con.execute('INSERT INTO company_calendar VALUES (?,?,?,?,?,?,1,?,?) '
                        'ON CONFLICT(date,scope) DO UPDATE SET type=excluded.type,description=excluded.description,'
                        'required_workday=excluded.required_workday,affects_attendance_bonus=excluded.affects_attendance_bonus,'
                        'confirmed=1,source=excluded.source,confirmed_by=excluded.confirmed_by',
                        (str(day), scope, kind.value, description, int(required_workday), int(affects_attendance_bonus), source, actor))
            self.audit(con, 'CALENDAR_CONFIRMED', old=dict(old) if old else None,
                       new={'date': str(day), 'scope': scope, 'type': kind.value, 'required_workday': required_workday}, actor=actor)

    def calendar(self, eid, day):
        rows = self.db.query("SELECT * FROM company_calendar WHERE date=? AND scope IN ('*',?) AND confirmed=1 ORDER BY CASE WHEN scope=? THEN 0 ELSE 1 END",
                             (str(day), eid, eid))
        return rows[0] if rows else None

    def decide(self, source_hash, key, decision, *, reason, actor='user'):
        if not reason.strip() or not actor.strip():
            raise ValueError('Human decisions require actor and reason')
        with self.db.transaction() as con:
            old = con.execute('SELECT decision FROM review_decisions WHERE source_hash=? AND issue_key=?', (source_hash, key)).fetchone()
            con.execute('INSERT INTO review_decisions VALUES (?,?,?,?,?,?) ON CONFLICT(source_hash,issue_key) '
                        'DO UPDATE SET decision=excluded.decision,reason=excluded.reason,actor=excluded.actor,created_at=excluded.created_at',
                        (source_hash, key, encode(decision), reason, actor, utc_now()))
            self.audit(con, 'REVIEW_DECISION', old=json.loads(old['decision']) if old else None,
                       new={'key': key, 'decision': decision, 'reason': reason}, source=source_hash, actor=actor)

    def decisions(self, source_hash):
        return {r['issue_key']: {**json.loads(r['decision']), '_reason': r['reason']}
                for r in self.db.query('SELECT * FROM review_decisions WHERE source_hash=?', (source_hash,))}

    def remember_rule(self, kind, match_key, value, *, scope, actor='user'):
        if scope != '*' and not self.db.query('SELECT id FROM employees WHERE id=?', (scope,)):
            raise ValueError('Unknown rule scope')
        if not actor:
            raise ValueError('Rule must be explicitly confirmed')
        with self.db.transaction() as con:
            con.execute('INSERT INTO business_rules(kind,match_key,scope,value,confirmed_by,created_at) VALUES (?,?,?,?,?,?) '
                        'ON CONFLICT(kind,match_key,scope) DO UPDATE SET value=excluded.value,confirmed_by=excluded.confirmed_by,created_at=excluded.created_at',
                        (kind, match_key.strip(), scope, encode(value), actor, utc_now()))
            self.audit(con, 'BUSINESS_RULE_CONFIRMED', new={'kind': kind, 'match_key': match_key, 'scope': scope, 'value': value}, actor=actor)

    def rule(self, kind, match_key, eid):
        rows = self.db.query("SELECT value FROM business_rules WHERE kind=? AND match_key=? AND scope IN ('*',?) ORDER BY CASE WHEN scope=? THEN 0 ELSE 1 END",
                             (kind, match_key.strip(), eid, eid))
        return json.loads(rows[0]['value']) if rows else None

    def remember_value(self, eid, field, value, valid_from, policy=ReusePolicy.ALWAYS_SUGGEST, *, valid_to=None, actor='user'):
        date.fromisoformat(valid_from)
        if valid_to:
            date.fromisoformat(valid_to)
        amount = decimal_value(value)
        if amount is None:
            raise ValueError('A remembered value must have an amount')
        with self.db.transaction() as con:
            con.execute('INSERT INTO remembered_values(employee_id,field_key,value,valid_from,valid_to,reuse_policy,confirmed_by) VALUES (?,?,?,?,?,?,?) '
                        'ON CONFLICT(employee_id,field_key,valid_from) DO UPDATE SET value=excluded.value,valid_to=excluded.valid_to,reuse_policy=excluded.reuse_policy,confirmed_by=excluded.confirmed_by',
                        (eid, field, str(amount), valid_from, valid_to, ReusePolicy(policy).value, actor))
            self.audit(con, 'VALUE_REUSE_CONFIRMED', employee_id=eid,
                       new={'field': field, 'value': str(amount), 'policy': str(policy), 'valid_from': valid_from}, actor=actor)

    def remembered(self, eid, field, day):
        rows = self.db.query('SELECT * FROM remembered_values WHERE employee_id=? AND field_key=? AND valid_from<=? '
                             'AND (valid_to IS NULL OR valid_to>=?) ORDER BY valid_from DESC LIMIT 1', (eid, field, day, day))
        return rows[0] if rows else None

    def set_recurring_value(self, eid, field, value, year, month, *, apply='FROM_THIS_MONTH', reason, actor='user'):
        """Store an explicit effective-dated recurring value without rewriting history.

        ``CURRENT_MONTH`` is a one-month exception. ``FROM_THIS_MONTH`` closes
        the previously active forward value on the prior month and starts a new
        one.  Both choices are auditable and need a human reason.
        """
        if not self.db.query('SELECT id FROM employees WHERE id=?', (eid,)):
            raise ValueError('Unknown employee')
        if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError('Invalid effective payroll period')
        if not reason or not reason.strip():
            raise ValueError('A reason is required for a recurring-value change')
        amount = decimal_value(value)
        if amount is None:
            raise ValueError('Recurring value must be numeric')
        apply = str(apply).upper()
        if apply not in {'CURRENT_MONTH', 'FROM_THIS_MONTH'}:
            raise ValueError('apply must be CURRENT_MONTH or FROM_THIS_MONTH')
        start = date(year, month, 1)
        end = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        end = end.fromordinal(end.toordinal() - 1)
        with self.db.transaction() as con:
            old = [dict(row) for row in con.execute('SELECT * FROM recurring_value_effective WHERE employee_id=? AND field_key=?', (eid, field))]
            if apply == 'FROM_THIS_MONTH':
                prior_end = start.fromordinal(start.toordinal() - 1).isoformat()
                con.execute("UPDATE recurring_value_effective SET effective_to=? WHERE employee_id=? AND field_key=? "
                            "AND scope='FROM_THIS_MONTH' AND effective_from<? AND (effective_to IS NULL OR effective_to>=?)",
                            (prior_end, eid, field, start.isoformat(), start.isoformat()))
                valid_to = None
            else:
                valid_to = end.isoformat()
            con.execute('INSERT INTO recurring_value_effective VALUES (?,?,?,?,?,?,?,?,?) '
                        'ON CONFLICT(employee_id,field_key,effective_from,scope) DO UPDATE SET '
                        'value=excluded.value,effective_to=excluded.effective_to,reason=excluded.reason,confirmed_by=excluded.confirmed_by,created_at=excluded.created_at',
                        (eid, field, str(amount), start.isoformat(), valid_to, apply, reason.strip(), actor, utc_now()))
            self.audit(con, 'RECURRING_VALUE_EFFECTIVE', employee_id=eid, year=year, month=month,
                       old=old, new={'field': field, 'value': str(amount), 'apply': apply,
                                     'effective_from': start.isoformat(), 'effective_to': valid_to, 'reason': reason}, actor=actor)

    def recurring_value(self, eid, field, year, month):
        day = date(year, month, 1).isoformat()
        rows = self.db.query('SELECT * FROM recurring_value_effective WHERE employee_id=? AND field_key=? '
                             'AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) '
                             "ORDER BY CASE scope WHEN 'CURRENT_MONTH' THEN 0 ELSE 1 END, effective_from DESC LIMIT 1",
                             (eid, field, day, day))
        return rows[0] if rows else None

    def previous_value(self, eid, field, year, month):
        previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
        final = self.db.query("SELECT i.value FROM monthly_payroll_items i JOIN monthly_payroll p ON p.id=i.payroll_id "
                              "WHERE p.employee_id=? AND p.year=? AND p.month=? AND i.item_key=? AND p.status IN ('CONFIRMED','WRITTEN','LOCKED')",
                              (eid, previous_year, previous_month, field))
        rows = final or self.db.query('SELECT value FROM payroll_observations WHERE employee_id=? AND year=? AND month=? AND field_key=?',
                                     (eid, previous_year, previous_month, field))
        return decimal_value(rows[0]['value']) if rows else None

    def run(self, year, month):
        rows = self.db.query('SELECT * FROM payroll_runs WHERE year=? AND month=?', (year, month))
        return rows[0] if rows else None

    def setting(self, key, default=None):
        rows = self.db.query('SELECT value FROM app_settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set_setting(self, key, value):
        with self.db.transaction() as con:
            con.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encode(value)))

    def audit_history(self, limit=200):
        return self.db.query('SELECT timestamp,action,year,month,actor FROM audit_log ORDER BY id DESC LIMIT ?', (limit,))

    def audit_events(self, *, limit=50, before_id=None, year=None, month=None, action=None, actor=None):
        """Read a bounded, stable page of audit evidence without changing history."""
        limit = max(1, min(int(limit), 200))
        clauses, args = [], []
        if before_id is not None:
            clauses.append('id < ?')
            args.append(int(before_id))
        for column, value in (('year', year), ('month', month), ('action', action), ('actor', actor)):
            if value is not None:
                clauses.append(f'{column} = ?')
                args.append(value)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        return self.db.query('SELECT id,timestamp,action,employee_id,year,month,old_value,new_value,source,actor '
                             'FROM audit_log' + where + ' ORDER BY id DESC LIMIT ?', (*args, limit))

    def audit_event_count(self, *, year=None, month=None, action=None, actor=None):
        clauses, args = [], []
        for column, value in (('year', year), ('month', month), ('action', action), ('actor', actor)):
            if value is not None:
                clauses.append(f'{column} = ?')
                args.append(value)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        return self.db.query('SELECT COUNT(*) AS count FROM audit_log' + where, args)[0]['count']

    def audit_event(self, event_id):
        rows = self.db.query('SELECT id,timestamp,action,employee_id,year,month,old_value,new_value,source,actor '
                             'FROM audit_log WHERE id=?', (int(event_id),))
        return rows[0] if rows else None

    def employee_name(self, employee_id):
        if not employee_id:
            return None
        rows = self.db.query('SELECT canonical_name FROM employees WHERE id=?', (employee_id,))
        return rows[0]['canonical_name'] if rows else None

    def audit_filter_values(self):
        return {
            'years': [row['year'] for row in self.db.query('SELECT DISTINCT year FROM audit_log WHERE year IS NOT NULL ORDER BY year DESC')],
            'actions': [row['action'] for row in self.db.query('SELECT DISTINCT action FROM audit_log ORDER BY action')],
            'actors': [row['actor'] for row in self.db.query('SELECT DISTINCT actor FROM audit_log ORDER BY actor')],
        }

    def pending_changes(self, run_id):
        return self.db.query('SELECT * FROM source_changes WHERE run_id=? AND acknowledged=0 ORDER BY id DESC', (run_id,))
