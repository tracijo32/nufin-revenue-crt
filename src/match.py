import pandas as pd
from rapidfuzz import fuzz
from data import BlackthornData, MembershipData, StripeData
from config import Config

def complete_chart_string_mapping(
    blackthorn_data: BlackthornData,
    membership_data: MembershipData,
    config: Config
):
    invoice_df = blackthorn_data.invoices
    item_df = blackthorn_data.items
    mbr_df = membership_data.memberships
    cs_map_df = config.load_chart_string_mapping()
       ## pull in event,item,cs combos from invoices
    df1 = pd.merge(
        item_df[['invoice_id','chart_string','item_name']],
        invoice_df[['invoice_id','event_name']],
        on='invoice_id'
    ).drop(columns=['invoice_id'])\
        .drop_duplicates().fillna('<NULL>')

    ## pull in event,item,cs combos from membership
    df2 = mbr_df[['chart_string','event_name','item_name']]\
        .drop_duplicates().fillna('<NULL>')

    ## combine the two dataframes
    df = pd.concat([df1,df2]).drop_duplicates()

    ## filter to only include combos that are in the chart string mapping
    df = df[
        df['chart_string'].isin(cs_map_df['chart_string'].dropna()) |
        df['event_name'].isin(cs_map_df['event_name'].dropna()) |
        df['item_name'].isin(cs_map_df['item_name'].dropna())
    ]

    ## generate all possible combinations of the columns
    from itertools import combinations
    cols = ['chart_string','event_name','item_name']
    combos = [
        [*combo] 
        for n in range(1,len(cols)+1)[::-1]
        for combo in combinations(cols,n)
    ]

    ## iterate through each combination of the match columns,
    ## starting with the most specific and working up to the least specific
    ## join the mapped rows to the chart string mapping
    ## add the mapped rows to the full chart string mapping
    full_cs_map_df = []
    for combo in combos:
        mapped_df, df, cs_map_df = join_map(
            df,
            cs_map_df,
            combo
        )
        full_cs_map_df.append(mapped_df)
    full_cs_map_df = pd.concat(full_cs_map_df)\
        .reset_index(drop=True)

    ## restore the original null values
    for col in cols:
        full_cs_map_df.loc[
            full_cs_map_df[col].eq('<NULL>'),
            col
        ] = None
    return full_cs_map_df

def join_map(
    to_map_df: pd.DataFrame,
    map_df: pd.DataFrame,
    join_cols: list[str]
):
    ## select only rows that have just the join columns
    join_df = map_df.loc[
        map_df[join_cols].notna().all(axis=1),
        ['new_chart_string']+join_cols
    ]
    ## select only rows that have any of the join columns
    not_join_df = map_df.loc[
        map_df[join_cols].isna().any(axis=1)
    ]
    assert len(not_join_df) + len(join_df) == len(map_df)

    df = pd.merge(
        to_map_df,
        join_df,
        on=join_cols,
        how='left',
        indicator=True
    )
    mapped_df = df.loc[df['_merge'].eq('both')]\
        .reindex(columns=map_df.columns)
    remaining_df = df.loc[df['_merge'].ne('both')]\
        .reindex(columns=to_map_df.columns)\
            .drop_duplicates()

    return mapped_df, remaining_df, not_join_df

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
            stripe_df['type'].str.startswith('Refund'),
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
