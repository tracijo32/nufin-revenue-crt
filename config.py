import os
import pandas as pd

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
    'fee_bucket_override': {
        'columns': {
            'event_name': {
                'dtype': str,
                'unique': True,
                'nullable': False
            },
            'fee_bucket': {
                'dtype': str,
                'unique': False,
                'nullable': False
            },
            'chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': True
            }
        }
    },
    'chart_string_override': {
        'columns': {
            'event_name': {
                'dtype': str,
                'unique': False,
                'nullable': False
            },
            'item_name': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'chart_string': {
                'dtype': str,
                'unique': False,
                'nullable': True
            },
            'description': {
                'dtype': str,
                'unique': False,
                'nullable': True
            }
        },
        'multi_index_columns': [
            ['event_name', 'item_name']
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