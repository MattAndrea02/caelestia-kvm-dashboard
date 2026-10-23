import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
import vm_config as config
import vm_monitor as monitor
import ssh_connect as ssh

spec = importlib.util.spec_from_file_location("vm_setup", REPO / "scripts/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
