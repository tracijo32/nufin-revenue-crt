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

    chart_string_desc = config.load_chart_string_descriptions()
    gross['desc1'] = gross['chart_string'].map(chart_string_desc)
    gross['desc2'] = gross['assignment'].apply(
        lambda x: f'Event Revenue - {x}'
    )
    gross['description'] = gross['desc1'].fillna(gross['desc2'])
    gross = gross.drop(columns=['desc1','desc2','assignment'])

    return gross, fees

def aggregate_memberships(
    matched_memberships_df: pd.DataFrame,
    config: Config
):
    default_fee_chart_string = config.default_stripe_fee_chart_string
    fee_assign = config.load_fee_assignment_by_event()
    chart_string_desc = config.load_chart_string_descriptions()

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

    chart_string_desc = config.load_chart_string_descriptions()
    default_cs_desc = config.default_membership_chart_string_description
    gross['description'] = gross['chart_string'].map(chart_string_desc)\
        .fillna(default_cs_desc)

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

    return df

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

    return df

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
            .reindex(columns=cols),
        fees_df.rename(columns={'fees':'amount'})\
            .reindex(columns=cols),
        usage_df.reindex(columns=cols),
        refund_df.reindex(columns=cols)
    ])

    df['description'] = df['description'].fillna(
        df.groupby(['gateway','chart_string'])['description']\
            .transform('first')
    ).fillna(config.default_refund_chart_string_description)

    crt_lines = df.groupby(['gateway','wire_date','chart_string','description'])\
        ['amount'].sum().reset_index()

    return crt_lines

def balance_crt(
    stripe_data: StripeData,
    crt_lines: pd.DataFrame
) -> pd.DataFrame:

    df = stripe_data.transactions
    df['transaction_date'] = pd.to_datetime(df['transaction_timestamp']).dt.date
    df.loc[df['type'].ne('Charge'),'transaction_date'] = None

    stripe_net = df.groupby(['gateway','wire_date']).agg(
        transaction_dates = pd.NamedAgg('transaction_date',lambda x: sorted(x.dropna().unique())),
        net_amount = pd.NamedAgg('net','sum')
    )

    crt_net = crt_lines.groupby(['gateway','wire_date'])['amount']\
        .sum().rename('net_amount')

    bal = pd.merge(
        stripe_net,
        crt_net,
        left_index = True,
        right_index = True,
        how = 'left',
        suffixes = ['_stripe','_crt']
    )
    bal['net_amount_diff'] = bal['net_amount_stripe'].subtract(bal['net_amount_crt']).round(2)
    bal['balanced'] = bal['net_amount_diff'].eq(0)

    return bal
