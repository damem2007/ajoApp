"""Calendar-window funding policy. Dates are UTC civil dates; no bank-holiday guessing."""
import calendar
from datetime import date, timedelta
from app.domain import allocate

DAYS = {'daily':1,'weekly':7,'bi-weekly':14}
MONTHS = {'monthly':1,'bi-monthly':2,'quarterly':3,'semi-annual':6,'yearly':12}

def occurrence(anchor, frequency, index):
    if frequency in DAYS:
        return anchor + timedelta(days=DAYS[frequency]*index)
    total = anchor.year*12 + anchor.month-1 + MONTHS[frequency]*index
    year, month = divmod(total,12)
    return date(year,month+1,min(anchor.day,calendar.monthrange(year,month+1)[1]))

def schedule(config, member_ids, policy):
    start = date.fromisoformat(config['start_date'])
    n = len(member_ids)
    if n<2: raise ValueError("At least two members are required")
    debit_dates = contribution_dates(config,n)
    fixed = config.get('contribution_minor')
    if fixed is not None and config['target_minor'] != fixed*len(debit_dates):
        raise ValueError('The derived payout does not match the fixed contribution plan')
    result = []
    for window in range(n):
        left = occurrence(start,config['collection_frequency'],window)
        right = occurrence(start,config['collection_frequency'],window+1)
        dates = [d for d in debit_dates if left <= d < right]
        if not dates:
            raise ValueError('A payout window has no contributions; pre-funding policy is required')
        if fixed is not None and n*fixed*sum(d < right for d in debit_dates) < config['target_minor']*(window+1):
            raise ValueError('This payout date is earlier than sufficient scheduled contributions. Choose a different start date or payout frequency.')
        shares = allocate(config['target_minor'],n,window)
        for rank,user_id in enumerate(member_ids):
            installments = [fixed]*len(dates) if fixed is not None else (allocate(shares[rank],len(dates)) if shares[rank] else [0]*len(dates))
            for i,(d,amount) in enumerate(zip(dates,installments)):
                if not amount: continue
                key = f'{window}:{rank}:{i}'
                result.append(dict(user_id=user_id, window=window, kind='contribution', date=d.isoformat(),
                                   amount_minor=amount,business_key=f'contribution:{key}'))
                if policy['fee_mode'] == 'per_contribution':
                    fee = policy['fee_flat_minor'] + (amount*policy['fee_bps']+9999)//10000
                    if fee:
                        result.append(dict(user_id=user_id,window=window,kind='fee',date=d.isoformat(),
                                           amount_minor=fee,business_key=f'fee:{key}'))
        result.append(dict(user_id=member_ids[window],window=window,kind='payout',date=right.isoformat(),
                           amount_minor=config['target_minor'],business_key=f'payout:{window}'))
    if len(result)>10000: raise ValueError("Schedule exceeds 10,000 payments")
    return sorted(result,key=lambda r:(r['date'],r['kind']=='payout',r['business_key']))

def contribution_dates(config,n):
    start = date.fromisoformat(str(config['start_date']))
    end = occurrence(start,config['collection_frequency'],n)
    debit_dates = []
    for i in range(20000):
        d = occurrence(start,config['contribution_frequency'],i)
        if d >= end: break
        debit_dates.append(d)
    else:
        raise ValueError('Schedule exceeds 20,000 debit dates; choose a shorter rotation')
    return debit_dates
