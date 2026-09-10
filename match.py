import pandas as pd
from rapidfuzz import fuzz
from data import BlackthornData, MembershipData, StripeData
from config import Config

def match_stripe_to_blackthorn(
    stripe_data: StripeData,
    blackthorn_data: BlackthornData
):
    common = ['amount','fees','net','email','transaction_timestamp']
    stripe_df = stripe_data.transactions
    invoice_df = blackthorn_data.invoices

    trans_df = pd.merge(
        stripe_df.loc[
            stripe_df['type'].eq('Charge'),
            ['transaction_id','type','wire_date','amount','fees','net',
            'gateway','email','transaction_timestamp']
        ],
        invoice_df[['transaction_id','invoice_id','amount','fees','net',
            'gateway_name','email','transaction_timestamp']],
        on='transaction_id',
        how='left',
        suffixes=('_stripe','_blackthorn'),
        indicator=True
    )

    bt_match_df = trans_df.loc[
        trans_df['_merge'].eq('both'),
    ].drop(columns=['_merge'])

    col_order = []
    for c in common:
        bt_match_df[f'{c}_match'] = bt_match_df[f'{c}_stripe'].eq(trans_df[f'{c}_blackthorn'])
        col_order.extend([f'{c}_stripe',f'{c}_blackthorn',f'{c}_match'])

    match_cols = [c for c in col_order if c.endswith('_match')]
    bt_match_df['match_score'] = bt_match_df[match_cols].mean(axis=1)
    col_order = [c for c in bt_match_df.columns if c not in col_order] + col_order
    blackthorn_match_df = bt_match_df[col_order]

    unmatched_stripe_df = pd.merge(
        stripe_df,
        trans_df.loc[
            trans_df['_merge'].eq('left_only'),
            ['transaction_id','type']
        ],
        how='inner',
        on=['transaction_id','type']
    )

    return blackthorn_match_df, unmatched_stripe_df

def match_stripe_to_memberships(
    unmatched_stripe_df: pd.DataFrame,
    membership_data: MembershipData
) -> pd.DataFrame:

    if unmatched_stripe_df.empty:
        return pd.DataFrame()

    mbr_df = membership_data.memberships

    start = unmatched_stripe_df['transaction_timestamp'].min().floor('D') - pd.Timedelta(days=1)
    end = unmatched_stripe_df['transaction_timestamp'].max().floor('D') + pd.Timedelta(days=2)

    m = mbr_df.loc[
        mbr_df['payment_date'].dt.date.between(start.date(),end.date()) &
        mbr_df['tender_type'].eq('Credit Card'),
        ['action_id','donor_name','payment_date','amount',
        'item_name','event_name','chart_string']
    ]
    m['payment_date'] = pd.to_datetime(m['payment_date'])

    s = unmatched_stripe_df.loc[
        unmatched_stripe_df['type'].eq('Charge'),
        ['gateway','wire_date','transaction_id','customer_name',
        'amount','fees','transaction_timestamp']
    ]
    s['transaction_date'] = s['transaction_timestamp'].dt.date
    s['date_buffer'] = s['transaction_date'].apply(
        lambda x: [x+pd.Timedelta(days=i) for i in range(-2,3)]
    ).apply(pd.to_datetime)

    s = s.explode('date_buffer',ignore_index=True)

    df = pd.merge(
        s,
        m,
        left_on=['date_buffer'],
        right_on=['payment_date'],
        suffixes=('','_membership')
    )

    df['name_match_score'] = df.apply(lambda x: fuzz.WRatio(x['customer_name'],x['donor_name']),axis=1) / 100
    df['amount_match_score'] = (df['amount_membership'].div(df['amount']).apply(lambda x: x if x <= 1 else 1/x))
    df['day_match_score'] = df['date_buffer'].eq(df['payment_date']).astype(int)
    
    df['match_score'] = df[['name_match_score','amount_match_score','day_match_score']].mean(axis=1)
    df = df.loc[
        df.groupby('transaction_id')['match_score'].idxmax()
    ]

    return df

def auto_match_refunds(
    stripe_data: StripeData,
    blackthorn_data: BlackthornData,
):

    stripe_df = stripe_data.transactions
    invoice_df = blackthorn_data.invoices
    item_df = blackthorn_data.items

    refund_df = pd.merge(
        stripe_df.loc[
            stripe_df['type'].eq('Refund'),
            ['gateway','transaction_id','wire_date','amount']
        ],
        invoice_df[['transaction_id','invoice_id','event_name']],
        on=['transaction_id'],
        how='left',
        suffixes=('_stripe','_blackthorn'),
        indicator=True
    )

    df = refund_df.loc[
        refund_df['_merge'].eq('both'),
    ].drop(columns=['_merge'])

    df = pd.merge(
        df,
        item_df.loc[
            item_df['total'].fillna(0).gt(0),
            ['invoice_id','item_id','item_name','total','chart_string']
        ],
        on='invoice_id',
        how='inner'
    )

    df['balanced'] = df[['amount','total']].sum(axis=1).round(2).eq(0)
    bal = df.loc[df['balanced']]\
        .groupby(['transaction_id','wire_date','invoice_id','amount'])\
        .agg(
            chart_string = ('chart_string','first'),
            n = ('chart_string','nunique'),
        )
        
    bal.loc[bal['n'].ne(1),'chart_string'] = None
    bal = bal.drop(columns=['n'])

    unbal = df.groupby(['transaction_id','wire_date','invoice_id','amount'])\
        .agg(
            chart_string = ('chart_string','first'),
            n = ('chart_string','nunique'),
        )

    unbal.loc[unbal['n'].ne(1),'chart_string'] = None
    unbal = unbal.drop(columns=['n'])

    df = pd.merge(
        bal,
        unbal,
        on=['transaction_id','wire_date','invoice_id','amount'],
        how='outer',
        suffixes=('_bal','_unbal')
    )
    df['chart_string'] = df['chart_string_bal'].fillna(df['chart_string_unbal'])
    df = df.drop(columns=['chart_string_bal','chart_string_unbal'])\
        .reset_index()

    refund_df = pd.merge(
        refund_df[['gateway','transaction_id','wire_date','invoice_id','amount']],
        df[['transaction_id','chart_string']],
        on='transaction_id',
        how='left'
    )

    return refund_df

def apply_overrides_to_refunds(
    refund_df: pd.DataFrame,
    config: Config
):
    ovrd_df = config.load_refund_override()
    df = pd.merge(
        refund_df,
        ovrd_df,
        on=['transaction_id'],
        how='left',
        suffixes=('_auto','_ovrd'),
        indicator=True
    )

    df['chart_string'] = df['chart_string_ovrd'].fillna(df['chart_string_auto'])\
        .fillna('<NULL>')
    df['amount'] = df['amount_ovrd'].fillna(df['amount_auto'])
    df = df.reindex(columns=refund_df.columns)

    return df

def match_refunds(
    bt_data: BlackthornData,
    stripe_data: StripeData,
    config: Config
):
    auto_df = auto_match_refunds(stripe_data, bt_data)
    refund_df = apply_overrides_to_refunds(auto_df, config)
    return refund_df

def match_charges(
    stripe_data: StripeData,
    bt_data: BlackthornData,
    mbr_data: MembershipData,
):
    bt_match_df, unmatched_stripe_df = match_stripe_to_blackthorn(stripe_data, bt_data)
    mbr_match_df = match_stripe_to_memberships(unmatched_stripe_df, mbr_data)
    return bt_match_df, mbr_match_df
