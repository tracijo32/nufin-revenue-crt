import sys
from config import Config
from pipeline import run_pipeline

if __name__ == '__main__':
    config_path = sys.argv[1]
    config = Config(config_path)
    run_pipeline(config)