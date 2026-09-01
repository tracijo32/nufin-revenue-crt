import pandas as pd
from rapidfuzz import process, fuzz

def get_transaction_window(wire_date: pd.Timestamp | str):
    """
    Helper function for getting the transaction window for a given wire date
    """
    ## key is the weekday #, 0 is Monday, 4 is Friday
    ## value is a list of the # of days to subtract off of the wire date
    ## to get the start/end dates of the transaction window
    wire_dict = {
        0:[-5,-4],
        1:[-5,-4],
        2:[-5,-2],
        3:[-3,-2],
        4:[-3,-2],
    }
    
    wire_date = pd.to_datetime(wire_date).date()   
    wire_ts_local = pd.to_datetime(wire_date).tz_localize('America/Chicago') + pd.to_timedelta(19,unit='h')
    start, end = wire_dict[wire_date.weekday()]

    start_dt = wire_ts_local + pd.to_timedelta(start, unit='D')
    end_dt = wire_ts_local + pd.to_timedelta(end, unit='D')

    return start_dt, end_dt

def match_blackthorn_to_stripe_charges(
    stripe_df: pd.DataFrame,
    invoice_df: pd.DataFrame,
    item_df: pd.DataFrame
) -> tuple[list[str],list[str]]:

    """
    Here we try to match invoices in Blackthorn to Stripe transactions (charges only)

    Args:
        stripe_df: pd.DataFrame - Stripe transactions
        invoice_df: pd.DataFrame - Blackthorn invoices (items not needed at this time)

    matched_transactions: list[str] will be a list of transaction_ids that are common to both
        Stripe charges and Blackthorn invoices, and are confirmed to have the same transaction time,
        customer email, amount, fees, and net.
    unmatched_transactions: list[str] will be a list of transaction_ids that are only in Blackthorn
        these are likely membership dues for NU clubs and need to be matched with another report
    """

    ## we only want invoices on the blackthorn report that are within the transaction windows
    ## for the stripe wire dates, which are 7:00 pm to 6:59 pm the following business day
    ## this eliminates irrelevant invoices that are going to be on other stripe reports
    ## this also assumes that you have back-to-back reports, gaps are going to be a problem

    trans_start, _ = get_transaction_window(stripe_df['wire_date'].min())
    _, trans_end = get_transaction_window(stripe_df['wire_date'].max())

    common = list(set(stripe_df.columns) & set(invoice_df.columns))

    trans_df = pd.merge(
        stripe_df.loc[
            stripe_df['type'].eq('charge'),
            common + ['wire_date']
        ],
        invoice_df.loc[
            invoice_df['transaction_timestamp'].ge(trans_start) &
            invoice_df['transaction_timestamp'].le(trans_end),
            common
        ],
        on='transaction_id',
        how='left',
        suffixes=('_str','_bt'),
        indicator=True
    )

    unmatched_transactions = trans_df.loc[
        trans_df['_merge'].eq('left_only'),
        'transaction_id'].unique().tolist()

    trans_df = trans_df[trans_df['_merge'].eq('both')].drop(columns=['_merge'])
    validate = list(set(common) - set(['transaction_id','customer_name']))
    for col in validate:
        trans_df[f'{col}_equal'] = trans_df[f'{col}_str'].eq(trans_df[f'{col}_bt'])
    assert trans_df[[col + '_equal' for col in validate]].all().all()

    matched_df = trans_df[['transaction_id','wire_date']]\
        .drop_duplicates()

    matched_df = pd.merge(
        matched_df,
        invoice_df[['invoice_id','transaction_id']],
        on='transaction_id',
    )
    matched_df = pd.merge(
        matched_df,
        item_df[['invoice_id','chart_string','item_name','total']],
        on='invoice_id',
        how='inner'
    )

    return matched_df, unmatched_transactions

def clean_name_column(s: pd.Series):
    # 1. Convert to string, lowercase, and replace NaN with empty string
    s = s.str.lower().fillna("")
    
    # 2. Strip common titles and suffixes (using regex word boundaries '\b')
    noise_pattern = r'\b(dr|mr|mrs|ms|prof|jr|sr|ii|iii|phd|md)\b'
    s = s.str.replace(noise_pattern, '', regex=True)
    
    # 3. Replace punctuation and special characters with a space
    s = s.str.replace(r'[^\w\s]', ' ', regex=True)
    
    # 4. Remove extra internal, leading, and trailing whitespaces
    # 'split' and 'join' via regex collapses multiple spaces into a single space
    s = s.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    return s
    
def match_memberships_to_stripe_charges(
    stripe_df: pd.DataFrame,
    mbr_df: pd.DataFrame,
    unmatched_transactions: list[str]
):
    """
    Match the Stripe transactions missing from the Blackthorn report to membership subscription purchases
    found in a separate report.

    We don't have transaction ID, we only have the donor name, the transaction date, and the purchase amount.
    We can do a fuzzy match on the donor name (usually the middle name or initial is absent and select for each transaction
    the highest scoring string fuzzy match that also has an exact match for transaction date and amount.
    """
    to_match_df = stripe_df.loc[
        stripe_df['transaction_id'].isin(unmatched_transactions),
        ['transaction_id','customer_name','transaction_timestamp','amount','wire_date']
    ]

    to_match_df['clean_name'] = clean_name_column(to_match_df['customer_name'])

    choices = mbr_df[['donor_name','donor_id']].drop_duplicates()
    choices['clean_name'] = clean_name_column(choices['donor_name'])
    choices = choices.set_index('donor_id')['donor_name']

    to_match_df['fuzzy_match_results'] = to_match_df['clean_name'].apply(
        lambda x: process.extract(x,choices,scorer=fuzz.token_set_ratio,limit=3)
    )

    to_match_df = to_match_df.explode('fuzzy_match_results')
    to_match_df[['match_name','match_score','donor_id']] = to_match_df['fuzzy_match_results'].apply(pd.Series)
    to_match_df['match_rank'] = to_match_df.groupby('transaction_id')['match_score'].rank(method='dense',ascending=False)

    comp = pd.merge(
        to_match_df,
        mbr_df[['donor_name','donor_id','amount','payment_date']],
        on='donor_id',
        suffixes=('_str','_mbr')
    ).drop(columns=['clean_name','fuzzy_match_results'])
    comp['transaction_date'] = comp['transaction_timestamp'].dt.date

    comp['match_date'] = comp['payment_date'].eq(comp['transaction_date'])
    comp['match_amount'] = comp['amount_str'].eq(comp['amount_mbr'])

    final_match = comp.loc[comp.loc[
            comp['match_date'] & comp['match_amount']
        ].groupby('transaction_id')['match_score'].idxmax()
    ]

    # this may not actually be true, but we would certainly hope that the best matching name also happens
    # to be the one with the exact transaction date and amount
    # this could not be true if there were donors that had similar names who happen to be on the same report
    # highly unlikely, but possible
    assert final_match['match_rank'].eq(1).all()

    df = pd.merge(
        final_match[['transaction_id','wire_date','donor_id','payment_date']],
        mbr_df[['donor_id','donor_name','amount','chart_string','payment_date','item_name']],
        on=['donor_id','payment_date'],
        how='inner'
    )

    ## return the transaction ID, donor ID, and payment date so we can link the transactions
    ## to the correct membership purchase
    return df