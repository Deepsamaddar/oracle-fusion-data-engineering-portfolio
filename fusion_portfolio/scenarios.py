"""Three regional scenario contracts and analytics; no live Oracle access."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

CURRENCIES = {'apac_procurement': {'INR', 'SGD', 'AUD'},
              'emea_payables': {'EUR', 'GBP', 'AED'},
              'americas_close': {'USD', 'CAD', 'BRL'}}


def decimal(value, nonnegative=True):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('invalid decimal') from None
    if not amount.is_finite() or (nonnegative and amount < 0):
        raise ValueError('amount must be finite and nonnegative')
    if abs(amount) > Decimal('1000000000000'):
        raise ValueError('amount exceeds demo precision bound')
    if amount != amount.quantize(Decimal('0.01')):
        raise ValueError('only two decimal places supported')
    return amount


def validate(scenario, raw):
    common = ['record_id', 'updated_at', 'currency']
    required = {'apac_procurement': ['order_id', 'ordered_qty', 'received_qty', 'agreed_price', 'invoice_price'],
                'emea_payables': ['invoice_id', 'invoice_amount', 'paid_amount', 'due_date'],
                'americas_close': ['journal_id', 'ledger', 'period', 'debit', 'credit']}[scenario]
    for field in common + required:
        if raw.get(field) is None or not str(raw[field]).strip():
            raise ValueError('missing ' + field)
    row = {key: raw[key] for key in common + required}
    row['currency'] = str(row['currency']).strip().upper()
    if row['currency'] not in CURRENCIES[scenario]:
        raise ValueError('unsupported regional currency')
    numeric = {'apac_procurement': ['ordered_qty', 'received_qty', 'agreed_price', 'invoice_price'],
               'emea_payables': ['invoice_amount', 'paid_amount'],
               'americas_close': ['debit', 'credit']}[scenario]
    for field in numeric:
        row[field] = format(decimal(row[field]), '.2f')
    if scenario == 'apac_procurement' and Decimal(row['ordered_qty']) == 0:
        raise ValueError('ordered_qty must be positive')
    if scenario == 'emea_payables':
        row['due_date'] = date.fromisoformat(str(row['due_date'])).isoformat()
        if Decimal(row['paid_amount']) > Decimal(row['invoice_amount']):
            raise ValueError('paid amount exceeds invoice amount')
    if scenario == 'americas_close':
        if Decimal(row['debit']) and Decimal(row['credit']):
            raise ValueError('a journal line cannot have both debit and credit')
        date.fromisoformat(str(row['period']) + '-01')
    return row


def procurement(rows):
    results, totals = [], defaultdict(lambda: Decimal('0'))
    for row in rows:
        ordered, received = Decimal(row['ordered_qty']), Decimal(row['received_qty'])
        price_delta = Decimal(row['invoice_price']) - Decimal(row['agreed_price'])
        flags = []
        if received < ordered:
            flags.append('under_received')
        if received > ordered:
            flags.append('over_received')
        if abs(price_delta) > Decimal('0.01'):
            flags.append('price_variance')
        exposure = (max(ordered - received, Decimal('0')) * Decimal(row['agreed_price'])).quantize(Decimal('0.01'))
        totals[row['currency']] += exposure
        results.append(dict(record_id=row['record_id'], order_id=row['order_id'],
                            currency=row['currency'], exceptions=flags,
                            open_commitment=format(exposure, '.2f')))
    return dict(records=len(rows), exception_records=sum(bool(r['exceptions']) for r in results),
                open_commitment_by_currency={k:format(v,'.2f') for k,v in sorted(totals.items())}, details=results)


def payables(rows, as_of):
    as_of = date.fromisoformat(as_of)
    totals, details = {}, []
    for row in rows:
        days = (as_of - date.fromisoformat(row['due_date'])).days
        outstanding = Decimal(row['invoice_amount']) - Decimal(row['paid_amount'])
        bucket = ('settled' if not outstanding else 'not_due' if days <= 0 else
                  '1_30' if days <= 30 else '31_60' if days <= 60 else '61_90' if days <= 90 else '90_plus')
        currency = totals.setdefault(row['currency'], {})
        currency[bucket] = currency.get(bucket, Decimal('0')) + outstanding
        details.append(dict(record_id=row['record_id'], invoice_id=row['invoice_id'], currency=row['currency'],
                            days_overdue=max(days,0), bucket=bucket, outstanding=format(outstanding,'.2f')))
    return dict(records=len(rows), as_of=as_of.isoformat(),
                overdue_records=sum(r['bucket'] not in {'settled','not_due'} for r in details),
                aging_by_currency={c:{b:format(v,'.2f') for b,v in sorted(buckets.items())}
                                   for c,buckets in sorted(totals.items())},details=details)


def close_checks(rows):
    groups = defaultdict(lambda: [Decimal('0'), Decimal('0'), 0])
    for row in rows:
        key = (row['ledger'], row['period'], row['journal_id'], row['currency'])
        group = groups[key]
        group[0] += Decimal(row['debit'])
        group[1] += Decimal(row['credit'])
        group[2] += 1
    details = []
    for (ledger, period, journal, currency), (debit, credit, count) in sorted(groups.items()):
        delta = debit - credit
        details.append(dict(ledger=ledger,period=period,journal_id=journal,currency=currency,
                            debit=format(debit,'.2f'),credit=format(credit,'.2f'),delta=format(delta,'.2f'),
                            line_count=count,balanced=abs(delta)<=Decimal('0.01')))
    return dict(records=len(rows),journals=len(details),
                unbalanced_journals=sum(not r['balanced'] for r in details),details=details)


def analyze(scenario, rows, as_of='2026-10-23'):
    if scenario == 'apac_procurement': return procurement(rows)
    if scenario == 'emea_payables': return payables(rows,as_of)
    if scenario == 'americas_close': return close_checks(rows)
    raise ValueError('unknown scenario')
