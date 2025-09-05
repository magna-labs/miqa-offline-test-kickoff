from pathlib import Path
import runpy, sys

def main():
    # Ensure argv[0] shows the right command name
    sys.argv[0] = "miqa-offline"

    # Run your existing run-miqa.py in the same process
    script_path = Path(__file__).resolve().parent.parent / "run-miqa.py"
    runpy.run_path(str(script_path), run_name="__main__")