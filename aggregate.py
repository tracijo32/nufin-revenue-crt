import pandas as pd
from config import Config
from data import BlackthornData, StripeData

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
    df = pd.merge(
        df,
        fee_assign,
        on='event_name',
        how='left'
    )

    default_cs = config.default_stripe_fee_chart_string
    df['assignment'] = df['school'].fillna(df['gateway'])
    df['chart_string'] = df['chart_string'].fillna(default_cs)

    fees = df.groupby(['gateway','wire_date','assignment','chart_string'])\
        ['fees'].sum().abs().multiply(-1)\
            .reset_index()
    fees['description'] = fees['assignment'].apply(
        lambda x: f'Stripe Transaction Fees - {x}'
    )
    fees = fees.drop(columns=['assignment'])

    df = pd.merge(
        df.drop(columns=['chart_string','school']),
        item_df[['invoice_id','chart_string','total']],
        on='invoice_id'
    )

    gross = df[df['total'].fillna(0).gt(0)]\
        .rename(columns={'total':'gross'})\
        .groupby(['gateway','wire_date','assignment','chart_string'])\
        ['gross'].sum().abs()\
            .reset_index()

    cs_desc = config.load_chart_string_descriptions()
    cs_pfx = config.load_chart_string_prefix()

    gross['desc1'] = gross['chart_string'].map(cs_desc)

    for csp,desc in cs_pfx.items():
        gross.loc[
            gross['chart_string']\
                .str.strip()\
                    .str.replace(' ','-')\
                    .str.startswith(csp),
            'desc2'
        ] = desc + ' - Event Revenue'

    gross['description'] = gross['desc1'].fillna(gross['desc2'])\
        .fillna('<NULL>')
    gross = gross.drop(columns=['desc1','desc2'])

    return gross, fees

def aggregate_memberships(
    matched_memberships_df: pd.DataFrame,
    config: Config
):
    default_fee_chart_string = config.default_stripe_fee_chart_string
    fee_assign = config.load_fee_assignment_by_event()

    fees = pd.merge(
        matched_memberships_df[[
            'gateway',
            'wire_date',
            'event_name',
            'fees'
        ]],
        fee_assign,
        on='event_name',
        how='left'
    )
    fees['assignment'] = fees['school'].fillna(fees['gateway'])
    fees['chart_string'] = fees['chart_string'].fillna(default_fee_chart_string)

    fees = fees.groupby(['gateway','wire_date','assignment','chart_string'])\
        ['fees'].sum().abs().multiply(-1)\
            .reset_index()
    fees['description'] = fees['assignment'].apply(
        lambda x: f'Stripe Transaction Fees - {x}'
    )
    fees = fees.drop(columns=['assignment'])

    gross = matched_memberships_df\
        .rename(columns={'amount':'gross'})\
        .groupby(['gateway','wire_date','chart_string'])['gross'].sum().abs()\
            .reset_index()

    cs_desc = config.load_chart_string_descriptions()
    cs_pfx = config.load_chart_string_prefix()

    cs_desc = config.load_chart_string_descriptions()
    cs_pfx = config.load_chart_string_prefix()

    gross['desc1'] = gross['chart_string'].map(cs_desc)

    for csp,desc in cs_pfx.items():
        gross.loc[
            gross['chart_string']\
                .str.strip()\
                    .str.replace(' ','-')\
                    .str.startswith(csp),
            'desc2'
        ] = desc + ' - Club Memberships'

    gross['description'] = gross['desc1'].fillna(gross['desc2'])\
        .fillna('<NULL>')
    gross = gross.drop(columns=['desc1','desc2'])

    return gross, fees

def aggregate_usage_fees(
    stripe_data: StripeData,
    config: Config
):
    df = stripe_data.transactions.loc[
        stripe_data.transactions['type'].eq('Stripe Fee'),
        ['gateway','wire_date','amount']
    ].groupby(['gateway','wire_date'])['amount'].sum()\
        .reset_index()
    df['chart_string'] = config.default_stripe_fee_chart_string
    df['description'] = 'Stripe Usage Fees'
    return df

def balance_charges(
    stripe_data: StripeData,
    gross_df: pd.DataFrame,
    fees_df: pd.DataFrame
):
    cc_totals = pd.merge(
        gross_df.groupby(['gateway','wire_date'])['gross'].sum(),
        fees_df.groupby(['gateway','wire_date'])['fees'].sum(),
        left_index=True,
        right_index=True,
        how='outer'
    ).fillna(0)

    stripe_totals = stripe_data.transactions.loc[
        stripe_data.transactions['type'].eq('Charge'),
        ['gateway','wire_date','amount','fees']
    ].groupby(['gateway','wire_date'])[['amount','fees']].sum()\
        .rename(columns={'amount':'gross'})
    stripe_totals['gross'] = stripe_totals['gross'].abs()
    stripe_totals['fees'] = stripe_totals['fees'].abs().multiply(-1)

    df = pd.merge(
        stripe_totals,
        cc_totals,
        left_index=True,
        right_index=True,
        how='left',
        suffixes=('_stripe','_cc')
    ).fillna(0)

    df['gross_diff'] = df['gross_cc'].subtract(df['gross_stripe']).round(2)
    df['fees_diff'] = df['fees_cc'].subtract(df['fees_stripe']).round(2)

    df['balanced'] = df['gross_diff'].eq(0) & df['fees_diff'].eq(0)

    return df.reset_index()

def balance_refunds(
    stripe_data: StripeData,
    refund_df: pd.DataFrame
):
    cc_totals = refund_df.groupby(['gateway','wire_date'])['amount'].sum()
    stripe_totals = stripe_data.transactions.loc[
        stripe_data.transactions['type'].eq('Refund'),
        ['gateway','wire_date','amount']
    ].groupby(['gateway','wire_date'])['amount'].sum()

    df = pd.merge(
        stripe_totals,
        cc_totals,
        left_index=True,
        right_index=True,
        how='left',
        suffixes=('_stripe','_cc')
    ).fillna(0)

    df['amount_diff'] = df['amount_cc'].subtract(df['amount_stripe']).round(2)
    df['balanced'] = df['amount_diff'].eq(0)

    return df.reset_index()

def get_crt_lines(
    gross_df: pd.DataFrame,
    fees_df: pd.DataFrame,
    refund_df: pd.DataFrame,
    usage_df: pd.DataFrame,
    config: Config
):
    
    cols = ['gateway','wire_date','chart_string','description','amount']

    df = pd.concat([
        gross_df.rename(columns={'gross':'amount'})\
            .reindex(columns=cols).assign(type='Gross'),
        fees_df.rename(columns={'fees':'amount'})\
            .reindex(columns=cols).assign(type='Transaction Fees'),
        usage_df.reindex(columns=cols).assign(type='Billing Fees'),
        refund_df.reindex(columns=cols).assign(type='Refund')
    ])

    df['description'] = df['description'].fillna(
        df.groupby(['gateway','chart_string'])['description']\
            .transform('first')
    ).fillna(config.default_refund_chart_string_description)

    crt_lines = df.groupby([
        'gateway','wire_date','chart_string','description','type'])\
        ['amount'].sum().reset_index()

    return crt_lines

def balance_crt(
    crt_lines: pd.DataFrame,
    stripe_data: StripeData
) -> pd.DataFrame:

    stripe_df = stripe_data.transactions[
    ['gateway','wire_date','type','amount','fees','net']
]
    stripe_df['fees'] = -stripe_df['fees'].abs()

    stripe_df = pd.melt(stripe_df,
        id_vars=['gateway','wire_date','type'],
        value_vars=['amount','fees','net'],
    )
    stripe_df['type'] = stripe_df.apply(
        lambda x: 'Net' if x['variable'] == 'net'
        else 'Gross' if x['type'] == 'Charge' and x['variable'] == 'amount'
        else 'Transaction Fees' if x['type'] == 'Charge' and x['variable'] == 'fees'
        else 'Refund' if x['type'].startswith('Refund')
        else 'Billing Fees' if x['type'] == 'Stripe Fee'
        else x['type'],
        axis=1
    ).str.strip()
    stripe_totals = stripe_df.groupby(['gateway','wire_date','type'])['value'].sum()\
        .reset_index().rename(columns={'value':'amount'})

    crt_totals = crt_lines.groupby(['gateway','wire_date','type'])['amount'].sum()\
        .reset_index()
    crt_net = crt_totals.groupby(['gateway','wire_date'])['amount'].sum()\
        .reset_index().assign(type='Net')
    crt_totals = pd.concat([crt_totals, crt_net])
    df = pd.merge(
        crt_totals,
        stripe_totals,
        on=['gateway','wire_date','type'],
        how='outer',
        suffixes=('_crt','_stripe')
    ).fillna(0).sort_values(by=['gateway','wire_date','type'])
    df['amount_diff'] = df['amount_crt'].subtract(df['amount_stripe']).round(2)

    return df

    