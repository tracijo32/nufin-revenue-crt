import pandas as pd
import os
from parse import \
    combine_blackthorn_reports, \
    combine_membership_reports, \
    combine_stripe_reports

class BlackthornData:
    def __init__(self):
        self.data_files = []
        self.invoices = None
        self.items = None
        self.coverage = None

    def load_from_files(self, data_files: list[str]):
        self.data_files = data_files
        self.invoices, \
        self.items,\
        self.coverage = combine_blackthorn_reports(data_files)
        return self
    
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

    def get_merged_data(self):
        df = pd.merge(
            self.invoices.drop(columns=['source']),
            self.items,
            on='invoice_id'
        ).sort_values(by=['invoice_id','item_id'])
        df['transaction_timestamp'] = pd.to_datetime(df['transaction_timestamp'])\
            .dt.strftime('%m/%d/%Y %I:%M %p %Z')

        return df

    def dump_data(
        self,
        path: os.PathLike
    ):
        self.get_merged_data().to_csv(path,index=False)

class MembershipData:
    def __init__(self):
        self.data_files = []
        self.memberships = None
        self.coverage = None

    def load_from_files(self, data_files: list[str]):
        self.data_files = data_files
        self.memberships, \
            self.coverage = combine_membership_reports(data_files)
        return self

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

    def dump_data(
        self,
        path: os.PathLike
    ):
        self.memberships.to_csv(path,index=False)

class StripeData:
    def __init__(self):
        self.data_files = []
        self.transactions = None

    def load_from_files(self, data_files: list[str]):
        self.data_files = data_files
        self.transactions = combine_stripe_reports(data_files)
        return self

    def dump_data(
        self,
        path: os.PathLike
    ):
        self.transactions.to_csv(path,index=False)