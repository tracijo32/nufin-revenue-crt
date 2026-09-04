import pandas as pd

def aggregate_blackthorn(
    matched_blackthorn_df: pd.DataFrame,
    invoice_df: pd.DataFrame,
    item_df: pd.DataFrame,
    li_ovrd: pd.DataFrame,
    cs_ovrd: pd.DataFrame,
    fb_ovrd: pd.DataFrame,
    default_fee_chart_string: str = '110-1640610-78680',
    set_discounts_to_zero=True
):

    df = pd.merge(
        matched_blackthorn_df[['transaction_id','wire_date',
            'gateway','amount_blackthorn','fees_blackthorn']],
        invoice_df[['transaction_id','invoice_id','event_name']],
        on='transaction_id'
    ).rename(columns={'amount_blackthorn':'amount','fees_blackthorn':'fees'})

    fees = pd.merge(
        df,
        fb_ovrd,
        on='event_name',
        how='left'
    )
    
    fees['fee_bucket'] = fees['fee_bucket'].fillna(fees['gateway'])
    fees['chart_string'] = fees['chart_string'].fillna(default_fee_chart_string)

    fees = fees.groupby(['gateway','wire_date','fee_bucket','chart_string'])\
        ['fees'].sum()\
        .reset_index()

    df = pd.merge(
        df,
        item_df,
        on='invoice_id'
    )

    df = pd.merge(
        df,
        li_ovrd,
        on='item_id',
        how='left',
        suffixes=('_orig','_ovrd')
    )
    df['total_orig'] = df['total_orig'].fillna(0)

    if set_discounts_to_zero:
        df.loc[df['total_orig'].lt(0) & df['total_ovrd'].isna(),'total_ovrd'] = 0

    df['total_to_use'] = df['total_ovrd'].fillna(df['total_orig'])

    cs_ovrd_item = cs_ovrd.loc[
        cs_ovrd['item_name'].notna(),
        ['event_name','item_name','chart_string']
    ]
    cs_ovrd_event = cs_ovrd.loc[
        cs_ovrd['item_name'].isna(),
        ['event_name','chart_string']
    ]

    df = pd.merge(
        df,
        cs_ovrd_event,
        on='event_name',
        how='left',
        suffixes=('','_ovrd_event')
    )

    df = pd.merge(
        df,
        cs_ovrd_item,
        on=['event_name','item_name'],
        how='left',
        suffixes=('_orig','_ovrd_item')
    )

    df['chart_string_ovrd'] = df['chart_string_ovrd_item'].fillna(df['chart_string_ovrd_event'])
    df['chart_string_to_use'] = df['chart_string_ovrd'].fillna(df['chart_string_orig'])

    df = df.drop(columns=['chart_string_ovrd_item','chart_string_ovrd_event'])
    df = df[df['total_to_use'].gt(0)]

    gross = df.groupby(['gateway','wire_date','chart_string_to_use'])['total_to_use'].sum()\
        .reset_index().rename(columns={'chart_string_to_use':'chart_string','total_to_use':'amount'})

    return gross, fees

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

