import pandas as pd
import os

def format_chart_string(s: pd.Series):
    s = s.str.split(',').apply(lambda x: ','.join([i.strip().replace(' ','-') for i in x])
     if isinstance(x,list) else x)
    return s

def detect_header_row(
        path: os.PathLike,
        nrows:int=50,
        identifying_columns: list[str] = ['invoice id','transaction id','chart string','donor id','event name']
    ):
    """
    Iterate over the first nrows of the file and match on strings to identify the header row.
    """
    top = pd.read_excel(path, nrows=nrows, header=None)
    
    for i, row in top.iterrows():
        if all([row.str.lower().str.contains(cn).any() for cn in identifying_columns]):
            return i

def identify_sum_count(series: pd.Series):
    case1 = (series.str.contains(r'sum|count',case=False,na=False) | series.isna()).all()
    case2 = series.notna().any()
    return case1 and case2

def identify_subtotal_column(series: pd.Series):
    return series.str.contains('subtotal',case=False,na=False).any()

def parse_lightning_report(
    path: os.PathLike,
    identifying_columns: list[str],
    column_rename_dict: dict[str,str] = {},
    match_string: str | None = None,
    date_cols: list[str] | None = None,
    num_cols: list[str] | None = None
):
    header_row = detect_header_row(path,identifying_columns=identifying_columns)
    df = pd.read_excel(path, skiprows=header_row,dtype=str)
    df.columns = df.columns.str.strip().str.lower()

    sum_count_col = df.columns[df.apply(identify_sum_count,axis=0)][0]

    df = df.rename(columns={sum_count_col:'sum count'})
    df = df.reindex(columns=[c for c in df.columns if not c.startswith('unnamed')])
    df.columns = [c[-1] for c in df.columns.str.strip().str.lower().str.split(':')]
    df.columns = df.columns.str.replace(r"[^a-z0-9\s]", "", regex=True)\
            .str.strip().str.replace(r"\s+", "_", regex=True)

    subtotal_col = df.columns[df.apply(identify_subtotal_column,axis=0)][0]
    df[subtotal_col] = df[subtotal_col].ffill()

    df = df[~df['sum_count'].str.lower().str.strip().isin(['sum', 'count'])]\
        .drop(columns=['sum_count'])

    if match_string is not None:
        df = df[df[subtotal_col].str.contains(match_string,case=False,na=False)]

    df = df.rename(columns=column_rename_dict)

    if num_cols is not None:
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce').astype(float)
    if date_cols is not None:
        df[date_cols] = df[date_cols].apply(pd.to_datetime, errors='coerce')

    return df

def parse_membership_report(path: os.PathLike):
    df = parse_lightning_report(
        path,
        identifying_columns=['donor id','donor name','amount','type'],
        match_string=r'\d+/\d+/\d+',
        column_rename_dict={
            'last_pledge_gift_payment_date':'payment_date',
            'total_payment_credit_to_date':'payment_credit',
            'chartstring':'chart_string',
            'acknowledgement_description':'item_name'
        },
        date_cols=['payment_date','created_date'],
        num_cols=['amount','payment_credit']
    )
    df['event_name'] = 'Membership Payment'
    df['chart_string'] = format_chart_string(df['chart_string'])
    df['action_id'] = df['payment_date'].dt.strftime('%Y%m%d') + '-' + \
        df['donor_id'] + '-' + \
        df.groupby(['payment_date','donor_id']).cumcount().add(1).astype(str)
    df = df.set_index('action_id').reset_index()

    return df

def parse_blackthorn_report(path: os.PathLike):
    df = parse_lightning_report(
        path,
        identifying_columns=['invoice id','transaction id','chart string','donor id','event name'],
        match_string=r'IN-\d+',
        column_rename_dict={
            'full_name':'customer_name',
            'payment_gateway_fee':'fees',
            'retained_net_amount':'net',
            'payment_method_billing_email':'email',
            'payment_gateway_name':'gateway_name',
            'processed_date':'transaction_timestamp',
            'nu_chart_string':'chart_string'
        },
        date_cols=['transaction_timestamp'],
        num_cols=['amount','fees','net','total']
    )
    df['email'] = df['email'].str.lower().str.strip()

    invoice_columns = [
            'transaction_id',
            'customer_name',
            'event_name',
            'amount',
            'fees',
            'net',
            'email',
            'transaction_timestamp',
            'gateway_name'
    ]
    df['item_line_number'] = df.groupby('invoice_id').cumcount().add(1)
    df['item_id'] = df['invoice_id'].str.replace('IN-','LI-') + '-' + df['item_line_number'].astype(str)

    invoice_df = df.groupby('invoice_id')[invoice_columns].first().reset_index()
    invoice_df['transaction_timestamp'] = invoice_df['transaction_timestamp'].dt.tz_localize('America/Chicago')

    item_df = df.reindex(columns=['item_id','invoice_id','donor_id','chart_string','item_line_number','item_name','total'])
    item_df['chart_string'] = format_chart_string(item_df['chart_string'])
    return invoice_df, item_df

def parse_stripe_report(
    file_path: os.PathLike
):
    bn = os.path.basename(file_path)
    gateway = bn.split(' ')[0]

    mth = bn.split(' ')[1].split('.')[0]
    day = bn.split(' ')[1].split('.')[1]
    yr = bn.split(' ')[1].split('.')[2]

    wire_date = pd.to_datetime(f'20{yr}-{mth}-{day}').date()

    df = pd.read_csv(file_path,dtype=str).assign(wire_date=wire_date,gateway=gateway)
    df.columns = df.columns.str.strip().str.lower().str.replace(' ','_')
    df = df.reindex(columns=[c for c in df.columns if not 'metadata' in c])

    numeric_columns = ['amount','converted_amount','fees','net']
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce').astype(float)
    df['created'] = pd.to_datetime(df['created'], errors='coerce')\
        .dt.tz_localize('UTC').dt.tz_convert('America/Chicago')

    assert df['currency'].eq('usd').all(), 'Currency is not USD'
    assert df['converted_currency'].eq('usd').all(), 'Converted currency is not USD'

    df = df.rename(columns={
        'id':'transaction_id',
        'created':'transaction_timestamp',
        'customer_name':'customer_name',
        'customer_email':'email'
    }).reindex(
        columns=[
            'transaction_id',
            'wire_date',
            'gateway',
            'type',
            'transaction_timestamp',
            'customer_name',
            'email',
            'amount',
            'fees',
            'net',
            'customer_id',
            'description'
        ]
    )
    df['email'] = df['email'].str.lower().str.strip()
    
    return df

