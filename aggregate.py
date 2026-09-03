import pandas as pd

def get_crt_lines_charges(
    all_match_df: pd.DataFrame,
    chart_string_desc: pd.DataFrame
):
    cs = all_match_df.loc[
            all_match_df['chart_string'].notnull() &
            all_match_df['item_amount'].fillna(0).ne(0),
        ['gateway','chart_string','event_name','item_name']
    ].drop_duplicates()

    cs['cs'] = cs['chart_string'].str.split(',')
    cs = cs.explode('cs')

    cs['fund_code'] = cs['cs'].str.split('-').str[0]
    assert cs['fund_code'].str.len().eq(3).all()
    cs['department'] = cs['cs'].str.split('-').str[1]
    assert cs['department'].str.len().eq(7).all()

    cs['project'] = cs['cs'].str.split('-').str[2]
    cs.loc[cs['project'].str.len().ne(8),'project'] = None

    cs['activity'] = cs['project'].str.replace(r'\d+','01',regex=True)

    general_no_proj = cs['fund_code'].eq('110') & cs['project'].isna()
    rest_has_proj = cs['fund_code'].ne('110') & cs['project'].notna()
    assert (general_no_proj | rest_has_proj).all()

    cs['cf1'] = cs['cs'].str.split('-').str[-2]
    cs.loc[cs['cf1'].str.len().ne(4),'cf1'] = None

    cs['account'] = cs['cs'].str.split('-').str[-1]
    cs.loc[cs['account'].str.len().ne(5),'account'] = None
    
    cs['account'] = cs['account'].fillna(
            cs['gateway'].map(
                {
                    'ARD': '40756',
                    'FSM': '40755'
                }
            )
        )

    cs['chart_string_full'] = cs[['fund_code','department','project','activity','cf1','account']].apply(
        lambda x: "-".join(x.dropna().astype(str)),axis=1
    )

    assert cs.apply(lambda x: x['cs'] in x['chart_string_full'],axis=1).all()
    cs['trunc_name'] = cs['event_name'].str.split(':').str[0].str.replace('.','')

    grp = cs.groupby('chart_string_full').agg(
        event_name = pd.NamedAgg(column='event_name', aggfunc='first'),
        n_events = pd.NamedAgg(column='event_name', aggfunc='nunique'),
        item_name = pd.NamedAgg(column='item_name', aggfunc='first'),
        n_items = pd.NamedAgg(column='item_name', aggfunc='nunique'),
        trunc_name = pd.NamedAgg(column='trunc_name', aggfunc='first'),
        n_truncs = pd.NamedAgg(column='trunc_name', aggfunc='nunique')
    )

    grp = pd.merge(
        grp,
        chart_string_desc,
        on='chart_string_full',
        how='left'
    )

    ifill = grp['n_items'].eq(1) & grp['description'].isnull()
    grp.loc[ifill,'description'] = grp.loc[ifill,'item_name']
    tfill = grp['n_truncs'].eq(1) & grp['description'].isnull()
    grp.loc[tfill,'description'] = grp.loc[tfill,'trunc_name']
    efill = grp['n_events'].eq(1) & grp['description'].isnull()
    grp.loc[efill,'description'] = grp.loc[efill,'event_name']

    assert grp['description'].notnull().all()

    cs = pd.merge(
        cs,
        grp[['chart_string_full','description']],
        on='chart_string_full',
        how='left'
    )

    assert cs.groupby('chart_string')['description'].nunique().eq(1).all()

    cs = cs.sort_values(by='chart_string').groupby('chart_string')\
        [['chart_string_full','description']].first().reset_index()

    validated_df = pd.merge(
        all_match_df,
        cs,
        on='chart_string',
        how='left'
    ).rename(columns={'chart_string':'original_chart_string'})\
        .rename(columns={'chart_string_full':'chart_string'})

    validated_df['chart_string'] = validated_df['chart_string'].fillna('unassigned')

    df = validated_df.groupby(['gateway','wire_date','chart_string','description'])['item_amount'].sum()\
        .reset_index().rename(columns={'item_amount':'amount'})

    return df

def get_crt_lines_transaction_fees(
    all_match_df: pd.DataFrame,
    stripe_fee_chart_string: str
):
    df = all_match_df[['transaction_id','wire_date','event_name','gateway','transaction_fees']].drop_duplicates()

    assert not df['transaction_id'].duplicated().any()

    fee_map = pd.read_csv('fee_map.csv',dtype=str)
    df = pd.merge(
        df,
        fee_map,
        on='event_name',
        how='left'
    )

    df['fee_designation'] = df['fee_designation'].fillna(df['gateway'])

    df = df.groupby(['gateway','wire_date','fee_designation'])['transaction_fees'].sum().reset_index()
    df['amount'] = -df['transaction_fees'].abs()

    df['chart_string'] = stripe_fee_chart_string
    df['description'] = 'Stripe Fees - ' + df['fee_designation']

    return df[['gateway','wire_date','chart_string','amount','description']]

def get_crt_lines_usage_fees(
    stripe_df: pd.DataFrame,
    stripe_fee_chart_string: str
):
    df = stripe_df.loc[
        stripe_df['type'].eq('stripe_fee')
    ].groupby(['gateway','wire_date'])['amount'].sum()\
        .reset_index()

    df['amount'] = -df['amount'].abs()
    df['chart_string'] = stripe_fee_chart_string
    df['description'] = 'Stripe Fees - Usage'

    return df
