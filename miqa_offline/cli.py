import sys
from miqa_offline._run_miqa import main as _runner_main  # created at build time

def main():
    sys.argv[0] = "miqa-offline"
    _runner_main()
