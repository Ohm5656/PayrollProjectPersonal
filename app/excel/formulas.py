"""Evaluate only the literal arithmetic actually present in employee rows.

No guessed statutory formulas, functions, external references or eval(). Excel
remains the authoritative recalculation engine for writing and validation.
"""
import ast
from decimal import Decimal
import re


class FormulaUnsupported(ValueError):
    pass


def arithmetic(formula, resolve):
    if not isinstance(formula, str) or not formula.startswith('='):
        raise FormulaUnsupported('Not a supported Excel formula')
    expression = re.sub(r'\$([A-Z]+)\$(\d+)|\$([A-Z]+)(\d+)|([A-Z]+)\$(\d+)',
        lambda m: ''.join(v for v in m.groups() if v), formula[1:])
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as exc:
        raise FormulaUnsupported('Unsupported Excel formula syntax') from exc
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return Decimal(ast.get_source_segment(expression, node))
        if isinstance(node, ast.Name) and re.fullmatch(r'[A-Z]{1,3}\d+', node.id):
            return resolve(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if b == 0: raise FormulaUnsupported('Division by zero')
            return a / b
        raise FormulaUnsupported('Only literal arithmetic and same-row cell references are supported')
    return visit(tree)


def row_values(person, proposed):
    cells = {cell.coordinate: (field, cell) for field, cell in person.cells.items()}
    active, cache = set(), {}
    def resolve(address):
        if address in cache:
            return cache[address]
        if address in active or address not in cells:
            raise FormulaUnsupported('Unknown or cyclic employee-row formula reference')
        field, cell = cells[address]
        active.add(address)
        try:
            if field in proposed:
                value = proposed[field]
                if value is None:
                    raise FormulaUnsupported('An input has not been confirmed')
            elif cell.formula:
                value = arithmetic(cell.formula, resolve)
            elif cell.raw is None:
                value = Decimal(0)  # Excel's observed blank reference semantics.
            elif cell.value is not None:
                value = cell.value
            else:
                raise FormulaUnsupported('Non-numeric payroll formula input')
            cache[address] = value
            return value
        finally:
            active.remove(address)
    return resolve
