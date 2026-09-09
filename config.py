import os, re, glob
import pandas as pd
from parse import \
    combine_blackthorn_reports, \
    combine_membership_reports, \
    combine_stripe_reports

CONFIG_INPUT_FRAMES = {
    'parameters':{
        'columns':{
            'parameter':{
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'value': {
                'dtype': str,
                'unique': False,
                'nullable': True
            }
        }
    },
    'fee_assignment_by_event': {
        'columns': {
            'event_name': {
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'school': {
                'dtype': str,
                'unique': False,
                'nullable': False
            },
            'fee_chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': True
            }
        },
        'multi_index_columns': [
            ['event_name','school']
        ]
    },
    'chart_string_override': {
        'columns': {
            'chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'description': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'original_chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'event_name': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'item_name': {
                'dtype': str,
                'unique': False,
                'nullable': True
            }
        },
        'multi_index_columns': [
            ['chart_string','original_chart_string','event_name','item_name'],
            ['chart_string','description']
        ]
    },
    'refund_override': {
        'columns': {
            'transaction_id': {
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'amount': {
                'dtype': float,
                'nullable': True
            },
            'chart_string': {
                'dtype': str,
                'nullable': False
            }
        }
    },
    'line_item_override': {
        'columns': {
            'item_id': {
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'total': {
                'dtype': float,
                'nullable': True
            },
            'chart_string': {
                'dtype': str,
                'nullable': True
            }
        }
    }
}


class ConfigFileLoadException(Exception):
    pass

class ConfigFileValidationException(Exception):
    pass

def load_input_frame(
    path_to_input_file: os.PathLike,
    sheet_name: str,
    **kwargs
):
    if os.path.isdir(path_to_input_file):
        path_to_input_file = os.path.join(path_to_input_file, f'{sheet_name}.csv')
        if not os.path.exists(path_to_input_file):
            raise FileNotFoundError(f'{path_to_input_file} does not exist')

    extension = os.path.splitext(path_to_input_file)[1]
    if extension == '.csv':
        return pd.read_csv(path_to_input_file, **kwargs)
    elif extension == '.xlsx':
        return pd.read_excel(path_to_input_file, sheet_name=sheet_name, **kwargs)
    else:
        raise ValueError(f'unsupported file extension: {extension}')

def validate_input_frame(
    df: pd.DataFrame,
    cols_not_null: list[str] = [],
    cols_unique: list[str] = [],
    multi_index_cols: list[tuple[str, ...]] = []
):
    for col in cols_not_null:
        if df[col].isnull().any():
            raise ValueError(f'{col} contains null values')

    for col in cols_unique:
        if df[col].duplicated().any():
            raise ValueError(f'{col} contains duplicate values')

    for col_tuple in multi_index_cols:
        if df[col_tuple].duplicated().any():
            col_tuple_str = ', '.join(col_tuple)
            raise ValueError(f'{col_tuple_str} contains duplicate values')

    return df

def generate_empty_input_frame(
    columns: list[str],
    dtypes: dict[str, type]
):
    return pd.DataFrame(columns=columns).astype(dtypes)

def _get_input_frame_columns(
    sheet_name: str,
):
    return list(CONFIG_INPUT_FRAMES[sheet_name]['columns'].keys())

def _get_input_frame_dtypes(
    sheet_name: str,
):
    return {
        col: CONFIG_INPUT_FRAMES[sheet_name]['columns'][col].get('dtype', str)
        for col in _get_input_frame_columns(sheet_name)
    }

def _get_input_frame_columns_by_null_status(
    sheet_name: str,
    nullable: bool = False
):
    return [
        col for col in _get_input_frame_columns(sheet_name)
        if CONFIG_INPUT_FRAMES[sheet_name]['columns'][col].get('nullable', True) == nullable
    ]

def _get_input_frame_columns_by_unique_status(
    sheet_name: str,
    unique: bool = False
):
    return [
        col for col in _get_input_frame_columns(sheet_name)
        if CONFIG_INPUT_FRAMES[sheet_name]['columns'][col].get('unique', False) == unique
    ]

def _get_input_frame_multi_index_columns(
    sheet_name: str,
):
    return CONFIG_INPUT_FRAMES[sheet_name].get('multi_index_columns', [])

def load_and_validate_input_frame(
    path_to_input_file: os.PathLike,
    sheet_name: str
):
    cols = _get_input_frame_columns(sheet_name)
    dtypes = _get_input_frame_dtypes(sheet_name)
    not_null_cols = _get_input_frame_columns_by_null_status(sheet_name, nullable=False)
    uniq_cols = _get_input_frame_columns_by_unique_status(sheet_name, unique=True)
    multi_index_cols = _get_input_frame_multi_index_columns(sheet_name)

    try:
        df = load_input_frame(
            path_to_input_file=path_to_input_file,
            sheet_name=sheet_name,
            usecols=cols,
            dtype=dtypes
        )
    except Exception as e:
        raise ConfigFileLoadException(f"Error loading {sheet_name} input frame: {e}")
    
    try:
        df = validate_input_frame(
            df,
            cols_not_null = not_null_cols,
            cols_unique = uniq_cols,
            multi_index_cols = multi_index_cols
        )
    except Exception as e:
        raise ConfigFileValidationException(f"Error validating {sheet_name} input frame: {e}")
    
    return df

class Config:
    @staticmethod
    def parse_report_path_to_file_list(
        path: os.PathLike,
        file_glob: str = '*',
        file_regex: str | None = None
    ):
        path = os.path.expanduser(os.path.abspath(path))
        if not os.path.exists(path):
            raise FileNotFoundError(f'{path} does not exist')

        if os.path.isdir(path):
            file_list = glob.glob(os.path.join(path,file_glob))
        else:
            file_list = glob.glob(os.path.join(os.path.dirname(path),file_glob))
            file_list = [f for f in file_list if f == path]

        if len(file_list) == 0:
            raise FileNotFoundError(f'No files found in {path} matching {file_glob}')

        if file_regex is not None:
            file_list = [f for f in file_list if re.match(file_regex,os.path.basename(f))]
            if len(file_list) == 0:
                raise FileNotFoundError(f'No files found in {path} matching {file_regex}')

        return file_list

    def __init__(self, config_path: os.PathLike):
        self.raw_input = {}
        for key in CONFIG_INPUT_FRAMES.keys():
            self.raw_input[key] = load_and_validate_input_frame(
                path_to_input_file=config_path,
                sheet_name=key
            )
        self._param_dict = self.raw_input['parameters']\
            .set_index('parameter')['value'].to_dict()

    def load_blackthorn_data(self):
        blackthorn_files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_blackthorn'],
                file_glob='*.xlsx'
            )
        return combine_blackthorn_reports(blackthorn_files)

    def load_membership_data(self):
        membership_files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_membership'],
            file_glob='*.xlsx'
        )
        return combine_membership_reports(membership_files)

    def load_stripe_data(self):
        gateways = self._param_dict.get('gateways_to_process','ARD')\
            .replace(' ','').split('|')
        prefix_pat = '|'.join(re.escape(p) for p in gateways)
        file_regex = re.compile(
            rf'^({prefix_pat})\s+(\d{{2}}\.\d{{2}}\.\d{{2}})\.csv$'
        )
        stripe_files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_stripe'],
            file_glob='*.csv',
            file_regex=file_regex
        )
        return combine_stripe_reports(stripe_files)

    def process_chart_string_overrides(
        self,
        invoice_df: pd.DataFrame,
        item_df: pd.DataFrame,
        mbr_df: pd.DataFrame
    ):
        ovrd_df = self.raw_input['chart_string_override']
        cs_desc = ovrd_df[['chart_string','description']].dropna()\
            .groupby('chart_string')['description'].first().to_dict()

        ovrd_df = ovrd_df.drop(columns=['description'])\
            .rename(columns={
                'chart_string':'new_chart_string',
                'original_chart_string':'chart_string'
            })

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
            df['chart_string'].isin(ovrd_df['chart_string'].dropna()) |
            df['event_name'].isin(ovrd_df['event_name'].dropna()) |
            df['item_name'].isin(ovrd_df['item_name'].dropna())
        ]

        cs_map_df = []
        for _, row in ovrd_df.iterrows():
            to_match = row[['chart_string','event_name','item_name']].dropna().to_dict()
            match_df = df.query(
                ' & '.join([
                    f"{k} == '{v}'"
                    for k,v in to_match.items()
                ])
            ).assign(
                new_chart_string = row['new_chart_string']
            )
            cs_map_df.append(match_df)
        cs_map_df = pd.concat(cs_map_df)

        return cs_map_df, cs_desc