import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import date,timedelta
from fusion_portfolio.demo import fixture,run_demo,write_extract
from fusion_portfolio.engine import ingest,read_manifest,records,timestamp
from fusion_portfolio.scenarios import analyze,validate
from fusion_portfolio.report import write_report
AP,EMEA,AM='apac_procurement','emea_payables','americas_close'

class PortfolioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.db=self.root/'warehouse.sqlite'
    def load(self,rows,scenario=EMEA,folder='batch',**kwargs):
        return ingest(write_extract(self.root/folder,scenario,rows,page_size=2),self.db,validate,**kwargs)
    def query(self,sql):
        with sqlite3.connect(self.db) as db:return db.execute(sql).fetchall()
    def test_all_three_contracts(self):
        for s in (AP,EMEA,AM):
            result=self.load(fixture(s,6),s,s)
            self.assertEqual((result['inserted'],result['quarantined']),(6,0))
    def test_replay(self):
        data=fixture(EMEA,4);self.load(data)
        self.assertTrue(self.load(data)['replayed'])
        self.assertEqual(self.query('select count(*) from records'),[(4,)])
        self.assertEqual(self.query('select count(*) from runs'),[(1,)])
    def test_new_version(self):
        row=fixture(EMEA,2)[1];self.load([row])
        result=self.load([dict(row,paid_amount='500.00',updated_at='2026-10-21T09:00:00Z')],folder='delta')
        self.assertEqual(result['updated'],1)
        self.assertEqual(records(self.db,EMEA)[0]['paid_amount'],'500.00')
    def test_stale_version(self):
        row=fixture(EMEA,2)[1];self.load([row])
        result=self.load([dict(row,updated_at='2026-10-01T00:00:00Z',paid_amount='0.00')],folder='old')
        self.assertEqual(result['stale'],1)
        self.assertEqual(records(self.db,EMEA)[0]['paid_amount'],'250.00')
    def test_late_arrival(self):
        row=fixture(EMEA,2)[0];self.load([row]);before=self.query('select * from watermarks')
        result=self.load([dict(row,record_id='late',updated_at='2026-09-01T00:00:00Z')],folder='late')
        self.assertEqual(result['inserted'],1);self.assertEqual(self.query('select * from watermarks'),before)
    def test_same_version_conflict(self):
        row=fixture(EMEA,2)[1];self.load([row])
        result=self.load([dict(row,paid_amount='500.00')],folder='conflict')
        self.assertEqual(result['quarantined'],1)
        self.assertIn('conflicting',self.query('select reason from quarantine')[0][0])
        self.assertEqual(records(self.db,EMEA)[0]['paid_amount'],'250.00')
    def test_unchanged(self):
        rows=fixture(EMEA,4);self.load(rows[:2]);result=self.load(rows,folder='expanded')
        self.assertEqual((result['unchanged'],result['inserted']),(2,2))
    def test_cross_page_duplicates(self):
        rows=fixture(EMEA,4);result=self.load(rows+[rows[0]])
        self.assertEqual((result['inserted'],result['quarantined']),(4,1))
    def test_atomic_rollback_and_retry(self):
        rows=fixture(EMEA,4);self.load(rows[:1])
        before={t:self.query('select * from '+t) for t in ('records','runs','watermarks','quarantine')}
        def fail(db):raise RuntimeError('simulated crash')
        with self.assertRaises(RuntimeError):
            self.load(rows+[dict(rows[0],record_id='',currency='XXX')],folder='failure',before_commit=fail)
        for table,value in before.items():self.assertEqual(self.query('select * from '+table),value)
        self.assertEqual(self.load(rows,folder='retry')['inserted'],3)
    def test_corrupt_checksum(self):
        path=write_extract(self.root/'files',EMEA,fixture(EMEA,2))
        (path.parent/'part-001.json').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'checksum'):ingest(path,self.db,validate)
        self.assertFalse(self.db.exists())
    def test_row_count_mismatch(self):
        path=write_extract(self.root/'files',EMEA,fixture(EMEA,2))
        value=json.loads(path.read_text());value['expected_rows']=999;path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'row-count'):read_manifest(path)
    def test_missing_page(self):
        path=write_extract(self.root/'files',EMEA,fixture(EMEA,4),page_size=2)
        value=json.loads(path.read_text());value['files']=value['files'][:1];value['expected_rows']=2
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'page chain'):read_manifest(path)
    def test_path_traversal(self):
        path=write_extract(self.root/'files',EMEA,fixture(EMEA,2))
        value=json.loads(path.read_text());value['files'][0]['path']='../outside.json';path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'unsafe'):read_manifest(path)
    def test_repeated_file(self):
        path=write_extract(self.root/'files',AM,fixture(AM,2),kind='csv')
        value=json.loads(path.read_text());value['files']*=2;path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'repeated'):read_manifest(path)
    def test_csv_identity(self):
        rows=fixture(AM,2);rows[0]['record_id']='000001'
        path=write_extract(self.root/'csv',AM,rows,kind='csv',page_size=1)
        self.assertEqual(ingest(path,self.db,validate)['inserted'],2)
        self.assertIn('000001',[r['record_id'] for r in records(self.db,AM)])
    def test_bad_rows_quarantined(self):
        row=fixture(EMEA,2)[0]
        result=self.load([dict(row,currency='XXX'),dict(row,record_id=''),dict(row,due_date='2026-99-01')])
        self.assertEqual(result['quarantined'],3)
        self.assertEqual(self.query('select count(*) from watermarks'),[(0,)])
    def test_invalid_decimal(self):
        row=fixture(EMEA,2)[1]
        for v in ('NaN','Infinity','-1','1.001','1000000000001','bad'):
            with self.subTest(value=v),self.assertRaises(ValueError):validate(EMEA,dict(row,invoice_amount=v))
    def test_overpayment(self):
        with self.assertRaisesRegex(ValueError,'paid amount'):
            validate(EMEA,dict(fixture(EMEA,2)[1],paid_amount='1001.00'))
    def test_aging_boundaries(self):
        for days,bucket in ((-1,'not_due'),(0,'not_due'),(1,'1_30'),(30,'1_30'),(31,'31_60'),(60,'31_60'),(61,'61_90'),(90,'61_90'),(91,'90_plus')):
            row=dict(fixture(EMEA,2)[1],due_date=(date(2026,10,23)-timedelta(days=days)).isoformat())
            with self.subTest(days=days):self.assertEqual(analyze(EMEA,[row])['details'][0]['bucket'],bucket)
    def test_settled_not_overdue(self):
        row=dict(fixture(EMEA,2)[0],due_date='2020-01-01');result=analyze(EMEA,[row])
        self.assertEqual(result['overdue_records'],0)
        self.assertEqual(result['details'][0]['bucket'],'settled')
    def test_procurement_tolerance(self):
        row=fixture(AP,2)[1]
        self.assertEqual(analyze(AP,[dict(row,invoice_price='25.01',received_qty='10.00')])['exception_records'],0)
        result=analyze(AP,[dict(row,invoice_price='25.02',received_qty='8.00')])
        self.assertEqual(result['details'][0]['exceptions'],['under_received','price_variance'])
        self.assertEqual(result['details'][0]['open_commitment'],'50.00')
    def test_currency_separation(self):
        row=fixture(AP,2)[0]
        result=analyze(AP,[dict(row,currency='INR'),dict(row,record_id='other',currency='SGD')])
        self.assertEqual(result['open_commitment_by_currency'],{'INR':'50.00','SGD':'50.00'})
    def test_journal_scope(self):
        rows=fixture(AM,2);rows[1]['credit']='100.00'
        self.assertEqual(analyze(AM,rows)['unbalanced_journals'],0)
        rows[1]['currency']='CAD';self.assertEqual(analyze(AM,rows)['unbalanced_journals'],2)
        rows[1]['currency']=rows[0]['currency'];rows[1]['ledger']='other'
        self.assertEqual(analyze(AM,rows)['unbalanced_journals'],2)
    def test_debit_credit_exclusive(self):
        with self.assertRaisesRegex(ValueError,'both debit'):validate(AM,dict(fixture(AM,2)[0],credit='1.00'))
    def test_timezone_normalization(self):
        self.assertEqual(timestamp('2026-10-20T14:30:00+05:30'),timestamp('2026-10-20T09:00:00Z'))
        with self.assertRaises(ValueError):timestamp('2026-10-20T09:00:00')
    def test_empty_batch(self):
        self.assertEqual(self.load([])['rows_in'],0)
        for scenario in (AP,EMEA,AM):self.assertEqual(analyze(scenario,[])['records'],0)
    def test_full_demo_replay_and_control_totals(self):
        report=run_demo(self.root/'demo',20)
        for value in report['runs'].values():
            initial=value['initial'];self.assertEqual(initial['rows_in'],23);self.assertEqual(initial['quarantined'],3)
            self.assertEqual(sum(initial[k] for k in ('inserted','updated','unchanged','stale','quarantined')),23)
        self.assertEqual(report['runs'][EMEA]['incremental']['updated'],1)
        self.assertEqual(report['runs'][EMEA]['incremental']['inserted'],1)
        again=run_demo(self.root/'demo',20)
        self.assertEqual(report['scenarios'],again['scenarios'])
        self.assertTrue(again['runs'][EMEA]['incremental']['replayed'])
    def test_html_escaping(self):
        report=run_demo(self.root/'demo',2);report['owner']='<script>alert(1)</script>'
        output=self.root/'report.html';write_report(report,output)
        self.assertNotIn('<script>',output.read_text());self.assertIn('&lt;script&gt;',output.read_text())

if __name__=='__main__':unittest.main()
