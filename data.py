import pandas as pd
from parse import \
    combine_blackthorn_reports, \
    combine_membership_reports, \
    combine_stripe_reports

class BlackthornData:
    def __init__(self, data_files: list[str]):
        self.data_files = data_files
        self.invoices, \
        self.items,\
        self.coverage = combine_blackthorn_reports(data_files)
    
    def apply_chart_string_overrides(
        self,
        full_cs_map_df: pd.DataFrame
    ):
        assert full_cs_map_df.notnull().all().all(), \
            'full_cs_map_df must not contain any null values'
        
        new_invoice_df = self.invoices.copy()
        new_invoice_df['event_name'] = new_invoice_df['event_name'].fillna('<NULL>')

        new_item_df = self.items.copy()
        new_item_df['chart_string'] = new_item_df['chart_string'].fillna('<NULL>')
        new_item_df['item_name'] = new_item_df['item_name'].fillna('<NULL>')

        new_item_df = pd.merge(
            new_item_df,
            new_invoice_df[['invoice_id','event_name']],
            on='invoice_id'
        )

        new_item_df = pd.merge(
            new_item_df,
            full_cs_map_df,
            on=['chart_string','item_name','event_name'],
            how='left'
        )

        new_item_df['chart_string'] = new_item_df['new_chart_string']\
            .fillna(new_item_df['chart_string'])
        new_item_df = new_item_df.reindex(columns=self.items.columns)

        self.invoices = new_invoice_df
        self.items = new_item_df

    def apply_line_item_overrides(
        self,
        li_ovrd_df: pd.DataFrame
    ):
        assert not li_ovrd_df['item_id'].duplicated().any(), \
            'li_ovrd_df must not contain any duplicate item_id values'
        
        df = self.items.copy()
        df = pd.merge(df, li_ovrd_df, on='item_id', how='left',suffixes=('','_ovrd'))
        df['chart_string'] = df['chart_string_ovrd'].fillna(df['chart_string'])
        df['total'] = df['total_ovrd'].fillna(df['total'])
        df = df.reindex(columns=self.items.columns)
        self.items = df

class MembershipData:
    def __init__(self, data_files: list[str]):
        self.data_files = data_files
        self.memberships, \
            self.coverage = combine_membership_reports(data_files)

    def apply_chart_string_overrides(
        self,
        full_cs_map_df: pd.DataFrame
    ):
        assert full_cs_map_df.notnull().all().all(), \
            'full_cs_map_df must not contain any null values'
        
        df = self.memberships.copy()
        df['chart_string'] = df['chart_string'].fillna('<NULL>')
        df['item_name'] = df['item_name'].fillna('<NULL>')

        df = pd.merge(
            df,
            full_cs_map_df,
            on=['chart_string','item_name','event_name'],
            how='left'
        )

        df['chart_string'] = df['new_chart_string']\
            .fillna(df['chart_string'])

        self.memberships = df

class StripeData:
    def __init__(self, data_files: list[str]):
        self.data_files = data_files
        self.transactions = combine_stripe_reports(data_files)

def complete_chart_string_mapping(
    invoice_df: pd.DataFrame,
    item_df: pd.DataFrame,
    mbr_df: pd.DataFrame,
    cs_map_df: pd.DataFrame
):
    df1 = pd.merge(
        item_df[['invoice_id','chart_string','item_name']].fillna('<NULL>'),
        invoice_df[['invoice_id','event_name']].fillna('<NULL>'),
        on='invoice_id'
    ).drop(columns=['invoice_id'])\
        .drop_duplicates()

    df2 = mbr_df[['chart_string','event_name','item_name']]\
        .fillna('<NULL>').drop_duplicates()
    
    df = pd.concat([df1,df2]).drop_duplicates()
    df = df[
        df['chart_string'].isin(cs_map_df['chart_string'].dropna()) |
        df['event_name'].isin(cs_map_df['event_name'].dropna()) |
        df['item_name'].isin(cs_map_df['item_name'].dropna())
    ]

    full_cs_map_df = []
    for _, row in cs_map_df.iterrows():
        to_match = row[['chart_string','event_name','item_name']].dropna().to_dict()
        match_df = df.query(
            ' & '.join([
                f"{k} == '{v}'"
                for k,v in to_match.items()
            ])
        ).assign(
            new_chart_string = row['new_chart_string']
        )
        full_cs_map_df.append(match_df)
    full_cs_map_df = pd.concat(full_cs_map_df)

    return full_cs_map_df