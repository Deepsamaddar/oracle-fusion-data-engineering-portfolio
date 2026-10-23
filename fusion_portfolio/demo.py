"""Generate deterministic fictional feeds, load all scenarios, and export evidence."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from .engine import ingest, records
from .scenarios import validate, analyze
from .report import write_report

AS_OF = '2026-10-23'


def write_extract(folder, scenario, rows, kind='rest_pages', page_size=75):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    chunks = [rows[i:i+page_size] for i in range(0,len(rows),page_size)] or [[]]
    for index, chunk in enumerate(chunks):
        path = folder / f'part-{index+1:03d}.{ "json" if kind == "rest_pages" else "csv"}'
        if kind == 'rest_pages':
            path.write_text(json.dumps({'items':chunk,'hasMore':index<len(chunks)-1},indent=2)+'\n')
        else:
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]) if rows else ['record_id'])
                writer.writeheader(); writer.writerows(chunk)
        files.append(dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest=folder/'manifest.json'
    manifest.write_text(json.dumps(dict(scenario=scenario,format=kind,files=files,expected_rows=len(rows)),indent=2)+'\n')
    return manifest


def fixture(scenario, count):
    if count < 2 or count % 2:
        raise ValueError('rows per scenario must be an even integer of at least 2')
    rows=[]
    currencies={'apac_procurement':['INR','SGD','AUD'], 'emea_payables':['EUR','GBP','AED'],
                'americas_close':['USD','CAD','BRL']}[scenario]
    for i in range(count):
        row=dict(record_id=f'{scenario}-{i:06d}',updated_at='2026-10-20T09:00:00Z',currency=currencies[i%3])
        if scenario=='apac_procurement':
            row.update(order_id=f'PO-{i//2:05d}',ordered_qty='10.00',
                       received_qty='8.00' if i%5==0 else '12.00' if i%7==0 else '10.00',
                       agreed_price='25.00',invoice_price='26.25' if i%11==0 else '25.00')
        elif scenario=='emea_payables':
            row.update(invoice_id=f'INV-{i:05d}',invoice_amount='1000.00',
                       paid_amount='1000.00' if i%7==0 else '250.00',
                       due_date=(date.fromisoformat(AS_OF)-timedelta(days=(i%130)-10)).isoformat())
        else:
            pair=i//2
            row['currency']=currencies[pair%3]
            row.update(journal_id=f'JRN-{pair:05d}',ledger=f'LEDGER-{pair%3}',period='2026-10',
                       debit='100.00' if i%2==0 else '0.00',
                       credit=('99.00' if pair%10==0 else '100.00') if i%2 else '0.00')
        rows.append(row)
    return rows


def run_demo(out, count=300):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    db=out/'warehouse.sqlite'
    runs, scenario_results={},{}
    for scenario in ('apac_procurement','emea_payables','americas_close'):
        rows=fixture(scenario,count)
        bad_currency=dict(rows[0],record_id='bad-currency',currency='XXX')
        bad_key=dict(rows[1],record_id='')
        manifest=write_extract(out/'landing'/scenario,scenario,rows+[bad_currency,bad_key,rows[0]],
                               'csv' if scenario=='americas_close' else 'rest_pages')
        first=ingest(manifest,db,validate)
        replay=ingest(manifest,db,validate)
        assert replay['replayed']
        runs[scenario]=dict(initial=first,replay_confirmed=True)
    # An updated invoice and a genuinely late-arriving invoice demonstrate CDC
    # without blindly dropping records older than a global high watermark.
    update=fixture('emea_payables',count)[1]
    update.update(paid_amount='500.00',updated_at='2026-10-22T09:00:00Z')
    late=dict(update,record_id='late-arrival',invoice_id='INV-LATE',updated_at='2026-10-01T09:00:00Z')
    incremental=write_extract(out/'landing'/'emea_incremental','emea_payables',[update,late])
    runs['emea_payables']['incremental']=ingest(incremental,db,validate)
    for scenario in runs:
        scenario_results[scenario]=analyze(scenario,records(db,scenario),AS_OF)
    report=dict(owner='Deep Samaddar',data_type='synthetic',as_of=AS_OF,
                rows_per_scenario=count,runs=runs,scenarios=scenario_results)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    write_report(report,out/'report.html')
    return report


def main():
    parser=argparse.ArgumentParser(description='Run Deep Samaddar’s three Oracle Fusion portfolio scenarios')
    parser.add_argument('--out',type=Path,default=Path('artifacts/demo'))
    parser.add_argument('--rows',type=int,default=300,help='even number of valid base rows per scenario')
    args=parser.parse_args()
    report=run_demo(args.out,args.rows)
    for scenario,value in report['scenarios'].items():
        print(scenario,json.dumps({k:v for k,v in value.items() if k!='details'}))
    print('Report:',args.out/'report.html')


if __name__=='__main__': main()
