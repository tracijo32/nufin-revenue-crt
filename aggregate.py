import pandas as pd

def aggregate_blackthorn(
    matched_blackthorn_df: pd.DataFrame,
    blackthorn_data: BlackthornData,
    config: Config
):

    invoice_df = blackthorn_data.invoices
    item_df = blackthorn_data.items

    df = pd.merge(
        matched_blackthorn_df[['transaction_id','wire_date',
            'gateway','amount_blackthorn','fees_blackthorn']],
        invoice_df[['transaction_id','invoice_id','event_name']],
        on='transaction_id'
    ).rename(columns={'amount_blackthorn':'amount','fees_blackthorn':'fees'})

    fee_assign = config.load_fee_assignment_by_event()
    fees = pd.merge(
        df,
        fee_assign,
        on='event_name',
        how='left'
    )

    default_cs = config.default_stripe_fee_chart_string
    fees['assignment'] = fees['school'].fillna(fees['gateway'])
    fees['chart_string'] = fees['chart_string'].fillna(default_cs)

    fees = fees.groupby(['gateway','wire_date','assignment','chart_string'])\
        ['fees'].sum().reset_index()

    df = pd.merge(
        df,
        item_df[['invoice_id','chart_string','total']],
        on='invoice_id'
    )
    
    df['total_sum_transaction'] = df.groupby(['transaction_id'])['total'].transform('sum')

    unbalanced_transactions = df[
        df['amount'].ne(df['total_sum_transaction'])
    ]

    gross = df[df['total'].fillna(0).gt(0)]\
        .groupby(['gateway','wire_date','chart_string'])\
        ['total'].sum()\
        .reset_index()\
        .rename(columns={'total':'gross'})

    return gross, fees, unbalanced_transactions

def aggregate_memberships(
    matched_memberships_df: pd.DataFrame,
    default_fee_chart_string: str = '110-1640610-78680'
):
    gross = matched_memberships_df\
        .groupby(['gateway','wire_date','chart_string'])['amount'].sum()\
        .reset_index()

    fees = matched_memberships_df\
        .groupby(['gateway','wire_date'])['fees'].sum()\
        .reset_index()
    fees['fee_bucket'] = fees['gateway']
    fees['chart_string'] = default_fee_chart_string

    return gross, fees

