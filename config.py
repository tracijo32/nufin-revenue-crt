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
    },
    'chart_string_prefix': {
        'columns': {
            'chart_string_prefix': {
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'description_prefix': {
                'dtype': str,
                'unique': True,
                'nullable': False
            }
        }
    }
}

class ConfigFileLoadException(Exception):
    pass

class ConfigFileValidationException(Exception):
    pass

class Config:
    def __init__(self, config_path: os.PathLike):
        try:
            self.config_path = self.validate_dir_path(config_path)
        except Exception as e:
            raise ConfigFileLoadException(f'Config path error: {e}')

        self.raw_input = {}
        for key in CONFIG_INPUT_FRAMES.keys():
            self.raw_input[key] = self.load_and_validate_input_frame(
                path_to_input_file=os.path.join(self.config_path,'input'),
                sheet_name=key
            )
        self._param_dict = self.raw_input['parameters']\
            .set_index('parameter')['value'].to_dict()
        self.default_stripe_fee_chart_string = self._param_dict\
            .get('default_stripe_fee_chart_string','<STRIPE FEE CHART STRING>')
        self.set_discounts_to_zero = 'T' in self._param_dict.get('set_discounts_to_zero','T').upper()
        self.default_membership_chart_string_description = self._param_dict.get(
            'default_membership_chart_string_description','Club Membership Purchases')
        self.default_event_chart_string_description = self._param_dict.get(
            'default_event_chart_string_description','Event Revenue'
        )
        self.default_refund_chart_string_description = self._param_dict.get(
            'default_refund_chart_string_description','Refund'
        )
        output_path = self._param_dict.get('path_to_output','.')
        output_path = os.path.expanduser(os.path.abspath(output_path))
        assert os.path.isdir(output_path), f'designated output path {output_path} is not a directory'
        self.output_path = output_path

    @staticmethod
    def validate_dir_path(
        path: os.PathLike,
    ):
        path = os.path.expanduser(os.path.abspath(path))
        if not os.path.exists(path):
            raise FileNotFoundError(f'{path} does not exist')
        if not os.path.isdir(path):
            raise NotADirectoryError(f'{path} is not a directory')

        return path

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

    @staticmethod
    def _get_input_frame_columns(
        sheet_name: str,
    ):
        return list(CONFIG_INPUT_FRAMES[sheet_name]['columns'].keys())

    @staticmethod
    def _get_input_frame_dtypes(
        sheet_name: str,
    ):
        return {
            col: data.get('dtype', str)
            for col, data in CONFIG_INPUT_FRAMES[sheet_name]['columns'].items()
        }

    @staticmethod
    def _get_input_frame_columns_by_null_status(
        sheet_name: str,
        nullable: bool = False
    ):
        return [
            col for col, data in CONFIG_INPUT_FRAMES[sheet_name]['columns'].items()
            if data.get('nullable', True) == nullable
        ]

    @staticmethod
    def _get_input_frame_columns_by_unique_status(
        sheet_name: str,
        unique: bool = False
    ):
        return [
            col for col, data in CONFIG_INPUT_FRAMES[sheet_name]['columns'].items()
            if data.get('unique', False) == unique
        ]

    @staticmethod
    def _get_input_frame_multi_index_columns(
        sheet_name: str,
    ):
        return CONFIG_INPUT_FRAMES[sheet_name].get('multi_index_columns', [])

    def load_and_validate_input_frame(
        self,
        path_to_input_file: os.PathLike,
        sheet_name: str
    ):
        cols = self._get_input_frame_columns(sheet_name)
        dtypes = self._get_input_frame_dtypes(sheet_name)
        not_null_cols = self._get_input_frame_columns_by_null_status(sheet_name, nullable=False)
        uniq_cols = self._get_input_frame_columns_by_unique_status(sheet_name, unique=True)
        multi_index_cols = self._get_input_frame_multi_index_columns(sheet_name)

        try:
            df = self.load_input_frame(
                path_to_input_file=path_to_input_file,
                sheet_name=sheet_name,
                usecols=cols,
                dtype=dtypes
            )
        except Exception as e:
            raise ConfigFileLoadException(f"Error loading {sheet_name} input frame: {e}")
        
        try:
            df = self.validate_input_frame(
                df,
                cols_not_null = not_null_cols,
                cols_unique = uniq_cols,
                multi_index_cols = multi_index_cols
            )
        except Exception as e:
            raise ConfigFileValidationException(f"Error validating {sheet_name} input frame: {e}")
        
        return df

    @staticmethod
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

    @staticmethod
    def validate_input_frame(
        df: pd.DataFrame,
        cols_not_null: list[str] = [],
        cols_unique: list[str] = [],
        multi_index_cols: list[tuple[str, ...]] = []
    ):
        ## Drop rows that are completely null
        ## sometimes Excel adds blank rows when it edits CSVs
        df = df[~df.isnull().all(axis=1)]

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

    @staticmethod
    def generate_empty_input_frame(
        columns: list[str],
        dtypes: dict[str, type]
    ):
        return pd.DataFrame(columns=columns).astype(dtypes)

    def load_blackthorn_data(self):
        files = self.parse_report_path_to_file_list(
            os.path.join(self.config_path,'reports','blackthorn'),
            file_glob='*.xlsx'
        )
        return BlackthornData().load_from_files(files)

    def load_membership_data(self):
        files = self.parse_report_path_to_file_list(
            os.path.join(self.config_path,'reports','membership'),
            file_glob='*.xlsx'
        )
        return MembershipData().load_from_files(files)

    def load_stripe_data(self):
        gateways = self._param_dict.get('gateways_to_process','ARD')\
            .replace(' ','').split('|')
        prefix_pat = '|'.join(re.escape(p) for p in gateways)
        file_regex = re.compile(
            rf'^({prefix_pat})\s+(\d{{2}}\.\d{{2}}\.\d{{2}})\.csv$'
        )
        files = self.parse_report_path_to_file_list(
            os.path.join(self.config_path,'reports','stripe'),
            file_glob='*.csv',
            file_regex=file_regex
        )
        return StripeData().load_from_files(files)

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

    def load_chart_string_prefix(self):
        return self.raw_input['chart_string_prefix']\
            .set_index('chart_string_prefix')['description_prefix'].to_dict()