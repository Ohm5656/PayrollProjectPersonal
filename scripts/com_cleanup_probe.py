"""Controlled read-only COM lifetime experiment on an independent copy."""
import argparse
import gc
import json
import shutil
from pathlib import Path
from uuid import uuid4
from app.excel.excel_gateway import ExcelGateway,excel_processes,verify_existing_excel
from app.safety import TEST_ROOT,REFERENCE_ROOT,development_target


def run(mode):
    target=development_target(TEST_ROOT/'com_lifetime'/str(uuid4())/'copy.xlsx')
    target.parent.mkdir(parents=True)
    shutil.copy2(next((REFERENCE_ROOT/'payroll').glob('* 8.xlsx')),target)
    before=excel_processes()
    print('BEFORE_ENTER',flush=True)
    with ExcelGateway() as gateway:
        print('OWNED',gateway.pid,flush=True)
        with gateway.open_copy(target) as book:
            print('BOOK_LAZY_TYPES',[type(x).__name__ for x in book.__dict__.get('_lazydata_',()) or ()],flush=True)
            from app.excel.payroll_reader import PayrollWorkbookAdapter
            adapter=PayrollWorkbookAdapter.read(target)
            cell=book.Worksheets(adapter.sheet_name).Range(adapter.employees[0].cells['travel'].coordinate)
            cell.Value2=1325
            del cell
            gateway.app.CalculateFull()
            print('CALCULATION_STATE',gateway.app.CalculationState,flush=True)
            book.Save()
        print('BOOK_CLOSED',flush=True)
        with gateway.open_copy(target,read_only=True):pass
        print('BOOK_REOPENED_AND_CLOSED',flush=True)
        if mode=='release_lazy':
            book.__dict__['_lazydata_']=None
            gateway.app.Quit  # Bind while metadata is alive; no call yet.
            gateway.app.__dict__['_lazydata_']=None
            gc.collect()
            print('LAZY_METADATA_RELEASED_BEFORE_QUIT',flush=True)
    print('AFTER_QUIT',flush=True)
    del book
    gc.collect()
    print('AFTER_CALLER_PROXY_RELEASE',flush=True)
    verify_existing_excel(before)
    print('DONE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['legacy','release_lazy']);run(p.parse_args().mode)
