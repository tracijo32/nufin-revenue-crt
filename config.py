import os, re, glob
import pandas as pd
from data import BlackthornData, MembershipData, StripeData

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
                'unique': False,
                'nullable': False
            },
            'amount': {
                'dtype': float,
                'nullable': True
            },
            'chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': False
            }
        },
        'multi_index_columns': [
            ['transaction_id','chart_string']
        ]
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
        self.default_stripe_fee_chart_string = self._param_dict\
            .get('default_stripe_fee_chart_string','<STRIPE FEE CHART STRING>')
        self.set_discounts_to_zero = 'T' in self._param_dict.get('set_discounts_to_zero','T').upper()

    def load_blackthorn_data(self):
        files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_blackthorn'],
            file_glob='*.xlsx'
        )
        return BlackthornData(files)

    def load_membership_data(self):
        files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_membership'],
            file_glob='*.xlsx'
        )
        return MembershipData(files)

    def load_stripe_data(self):
        gateways = self._param_dict.get('gateways_to_process','ARD')\
            .replace(' ','').split('|')
        prefix_pat = '|'.join(re.escape(p) for p in gateways)
        file_regex = re.compile(
            rf'^({prefix_pat})\s+(\d{{2}}\.\d{{2}}\.\d{{2}})\.csv$'
        )
        files = self.parse_report_path_to_file_list(
            self._param_dict['path_to_stripe'],
            file_glob='*.csv',
            file_regex=file_regex
        )
        return StripeData(files)

    def load_chart_string_descriptions(self):
        df = self.raw_input['chart_string_override']
        return df[['chart_string','description']].dropna()\
            .groupby('chart_string')['description'].first().to_dict()

    def load_chart_string_mapping(self):
        df = self.raw_input['chart_string_override']
        return df.drop(columns=['description'])\
            .rename(columns={
                'chart_string':'new_chart_string',
                'original_chart_string':'chart_string'
            })
    def load_fee_assignment_by_event(self):
        df = self.raw_input['fee_assignment_by_event']\
            .rename(columns={'fee_chart_string':'chart_string'})
        df['chart_string'] = df['chart_string']\
            .fillna(self.default_stripe_fee_chart_string)
        return df

    def load_line_item_override(self):
        return self.raw_input['line_item_override']

    def load_refund_override(self):
        return self.raw_input['refund_override']