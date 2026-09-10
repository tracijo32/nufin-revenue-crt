import pandas as pd
import os
from datetime import date
from data import BlackthornData

def generate_crt_sheet(
    wire_date: date, 
    gateway: str,
    crt_lines: pd.DataFrame
):
    from helpers import decompose_chart_string

    crt_sheet = crt_lines.loc[
        crt_lines['wire_date'].eq(wire_date) &  
        (crt_lines['gateway'].eq(gateway)),
        ['chart_string','description','amount']
    ].sort_values(by='chart_string')

    cs = crt_sheet['chart_string']\
        .apply(decompose_chart_string)\
        .apply(pd.Series)

    crt_sheet = pd.merge(
        crt_sheet,
        cs,
        left_index=True,
        right_index=True
    )

    return crt_sheet

def generate_balance_sheet(
    wire_date: date,
    gateway: str,
    crt_bal: pd.DataFrame
):
    df = crt_bal.loc[
        crt_bal['gateway'].eq(gateway) &
        crt_bal['wire_date'].eq(wire_date),
        ['type','amount_crt','amount_stripe','amount_diff']
    ]

    df['type'] = pd.Categorical(
        df['type'],
        categories=['Gross','Transaction Fees',
        'Billing Fees','Refund','Net','Other'],
        ordered=True
    )
    df = df.sort_values(by=['type'])
    return df

def generate_member_match_score_sheet(
    wire_date: date,
    gateway: str,
    mbr_match_df: pd.DataFrame,
):
    df = mbr_match_df.loc[
        mbr_match_df['wire_date'].eq(wire_date)
        & (mbr_match_df['gateway'] == gateway)
    ].drop(columns=['gateway','wire_date'])\
        .reindex(columns=[
            'action_id',
            'transaction_id',
            'match_score',
            'customer_name',
            'donor_name',
            'name_match_score',
            'donor_id',
            'amount',
            'amount_membership',
            'amount_match_score',
            'transaction_date',
            'payment_date',
            'date_match_score',
            'event_name',
            'item_name',
            'chart_string'
        ]).rename(columns={'amount':'amount_stripe'})

    return df

def generate_blackthorn_match_score_sheet(
    wire_date: date,
    gateway: str,
    bt_match_df: pd.DataFrame
):
    df = bt_match_df.loc[
        bt_match_df['wire_date'].eq(wire_date)
        & (bt_match_df['gateway'] == gateway)
    ].reindex(columns=[
        'transaction_id',
        'invoice_id',
        'match_score',
        'amount_stripe','amount_blackthorn','amount_match',
        'fees_stripe','fees_blackthorn','fees_match',
        'net_stripe','net_blackthorn','net_match',
        'email_stripe','email_blackthorn','email_match',
        'transaction_timestamp_stripe',
        'transaction_timestamp_blackthorn',
        'transaction_timestamp_match'
    ])
    df['transaction_timestamp_stripe'] = df['transaction_timestamp_stripe']\
        .dt.strftime('%m/%d/%Y %I:%M %p %Z')
    df['transaction_timestamp_blackthorn'] = df['transaction_timestamp_blackthorn']\
        .dt.strftime('%m/%d/%Y %I:%M %p %Z')

    return df

def generate_blackthorn_item_sheet(
    wire_date: date,
    gateway: str,
    bt_data: BlackthornData,
    bt_match_df: pd.DataFrame
):
    df = bt_data.get_merged_data()

    trans_ids = bt_match_df.loc[
        bt_match_df['wire_date'].eq(wire_date) &
        bt_match_df['gateway'].eq(gateway),
        'transaction_id'
    ]

    df = df[
        df['transaction_id'].isin(trans_ids)
    ].rename(columns={'amount':'invoice_amount','total':'item_total'})
    df['invoice_sum_item_total'] = df.groupby('invoice_id')['item_total'].transform('sum')

    df['invoice_amount_diff'] = df['invoice_amount'].subtract(df['invoice_sum_item_total']).round(2)
    df['invoice_balanced'] = df['invoice_amount_diff'].eq(0)

    df = df.reindex(columns=[   
            'transaction_id',
            'invoice_id',
            'transaction_timestamp',
            'event_name',
            'invoice_amount',
            'item_name',
            'chart_string',
            'item_total',
            'invoice_sum_item_total',
            'invoice_amount_diff',
            'invoice_balanced'
        ]
    )

    return df

def generate_daily_gateway_output_file(
    wire_date: date,
    gateway: str,
    path_to_output: os.PathLike,
    crt_lines: pd.DataFrame,
    crt_bal: pd.DataFrame,
    mbr_match_df: pd.DataFrame,
    bt_match_df: pd.DataFrame,
    bt_data: BlackthornData
):

    crt_sheet = generate_crt_sheet(
        wire_date=wire_date,
        gateway=gateway,
        crt_lines=crt_lines
    )

    bal_sheet =generate_balance_sheet(
        wire_date=wire_date,
        gateway=gateway,
        crt_bal=crt_bal
    )

    mbr_match_sheet = generate_member_match_score_sheet(
        wire_date=wire_date,
        gateway=gateway,
        mbr_match_df=mbr_match_df
    )

    bt_match_sheet = generate_blackthorn_match_score_sheet(
        wire_date=wire_date,
        gateway=gateway,
        bt_match_df=bt_match_df
    )

    bt_item_sheet = generate_blackthorn_item_sheet(
        wire_date=wire_date,
        gateway=gateway,
        bt_data=bt_data,
        bt_match_df=bt_match_df
    )

    sheet_dict = {
        'CRT Lines': crt_sheet,
        'Stripe vs Blackthorn': bal_sheet,
        'Member Match': mbr_match_sheet,
        'Blackthorn Match': bt_match_sheet,
        'Blackthorn Items': bt_item_sheet
    }

    fn = f'{gateway}_{wire_date.strftime("%Y-%m-%d")}.xlsx'
    path_to_file = os.path.join(path_to_output, fn)

    with pd.ExcelWriter(path_to_file) as writer:
        for sheet_name, df in sheet_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)