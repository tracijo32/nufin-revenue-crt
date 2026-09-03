import os, glob

def validate_data_path(
    root_path: str,
    dir_name: str,
    file_glob: str
): 
    path_to_dir = os.path.join(root_path,dir_name)  
    assert os.path.exists(path_to_dir), '%s does not exist' % path_to_dir
    assert os.path.isdir(path_to_dir), '%s is not a directory' % path_to_dir

    files = glob.glob(os.path.join(path_to_dir,file_glob))
    assert len(files) > 0, 'no files found'

def validate_config(
    config: dict
):
    assert 'data' in config, 'config must contain a data section'
    assert 'report_path' in config['data'], 'data section must contain a report_path key'

    report_path = config['data']['report_path']

    assert os.path.exists(report_path), 'report path does not exist'
    assert os.path.isdir(report_path), 'report path is not a directory'

    
    file_check = [
        'chart_string_overides'
    ]

    return True