from app.analysis.draft_regression import compare_history, CATEGORIES, write_comparison
from app.safety import ROOT


def test_all_nine_months_classify_drafts_without_forcing_historical_match(copied_reference, workbook_workspace):
    result = compare_history(copied_reference, workbook_workspace/'regression.db')
    assert result['months'] == list(range(1,10))
    assert {r['month'] for r in result['rows']} == set(range(1,10))
    assert set(result['counts']) <= CATEGORIES
    assert result['counts']['UNKNOWN_RULE'] > 0
    assert result['counts']['MATCH'] > 0
    assert not result['counts'].get('MANUAL_OVERRIDE', 0)
    write_comparison(result, ROOT/'reports/draft_regression.json')
