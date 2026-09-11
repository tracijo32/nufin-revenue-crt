import sys
from config import Config
from pipeline import run_pipeline

def test_install():
    try:
        import pandas as pd
        import rapidfuzz
        import openpyxl
    except ImportError:
        print('Some of the required packages are not installed. Please install them using the following command:')
        print('$ python -m pip install -r requirements.txt')
        sys.exit(1)

    try:
        from config import Config
    except ImportError:
        print('could not import config')
        sys.exit(1)

    print('All required packages are installed.')
    print('You can now run the pipeline by running the following command:')
    print('$ python main.py <config_path>')
    sys.exit(0)

def main(config_path: str):
    from config import Config
    config = Config(config_path)
    run_pipeline(config)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('Usage: python main.py <config_path>')
        sys.exit(1)
    
    arg = sys.argv[1]
    if arg == '--test':
        test_install()
    else:
        main(arg)