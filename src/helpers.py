import re
from datetime import date, timedelta

def decompose_chart_string(
    chart_string: str
) -> dict:
    if re.match(r'[A-Za-z]+', chart_string):
        return {}

    s = chart_string.strip().lower()
    s = re.sub(r'[^0-9\s-]', '', s)
    s = re.sub(r'-+', '-', s)
    s = re.sub(r'^-|-$', '', s)
    s = s.replace(' ','-')

    x = s.split('-')

    n3 = [x for x in x if len(x) == 3]
    fund = n3[0] if len(n3) == 1 else None  

    n7 = [x for x in x if len(x) == 7]
    dept = n7[0] if len(n7) == 1 else None

    n8 = [x for x in x if len(x) == 8]
    proj = n8[0] if len(n8) == 1 else None

    n2 = [x for x in x if len(x) == 2]
    act = n2[0] if len(n2) == 1 else None

    n4 = [x for x in x if len(x) == 4]
    cf1 = n4[0] if len(n4) == 1 else None

    n5 = [x for x in x if len(x) == 5]
    acct = n5[0] if len(n5) == 1 else None

    return {
        'fund':fund,
        'dept':dept,
        'proj':proj,
        'act':act,
        'cf1':cf1,
        'acct':acct
    }

def get_transaction_window(
    wire_date: date
):
    wire_day = wire_date.weekday()
    
    n_start = 5 if wire_day <= 2 else 3
    n_end = 4 if wire_day <= 1 else 2

    start_date = wire_date - timedelta(days=n_start)
    end_date = wire_date - timedelta(days=n_end)

    return start_date, end_date