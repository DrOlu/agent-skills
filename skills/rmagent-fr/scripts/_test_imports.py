import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib          # engine (fr copy)
import drift        # drift
import correlate    # correlate

# REV 20: patient_zero lives in the rmagent-so tree, not this one. Resolve it
# across the known skill locations instead of failing the whole suite when the
# fr tree is installed standalone.
import importlib.util as _ilu


def _load_patient_zero():
    here = Path(__file__).resolve().parent
    for cand in (here.parent.parent / "rmagent-so" / "scripts",
                 Path.home() / ".agents" / "skills" / "rmagent-so" / "scripts",
                 Path.home() / ".claude" / "skills" / "rmagent-so" / "scripts",
                 here):
        f = cand / "patient_zero.py"
        if f.exists():
            spec = _ilu.spec_from_file_location("patient_zero", f)
            m = _ilu.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("patient_zero.py not found in any rmagent tree")


patient_zero = _load_patient_zero()
