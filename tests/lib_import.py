# Load mpi_helpdesk_zoho.lib without executing the Odoo addon __init__.

import sys
import types
from pathlib import Path


def ensure_lib_package():
    root = Path(__file__).resolve().parents[1]
    addon = root / "mpi_helpdesk_zoho"
    if "mpi_helpdesk_zoho" not in sys.modules:
        pkg = types.ModuleType("mpi_helpdesk_zoho")
        pkg.__path__ = [str(addon)]
        pkg.__file__ = str(addon / "__init__.py")
        sys.modules["mpi_helpdesk_zoho"] = pkg
    if "mpi_helpdesk_zoho.lib" not in sys.modules:
        lib = types.ModuleType("mpi_helpdesk_zoho.lib")
        lib.__path__ = [str(addon / "lib")]
        lib.__file__ = str(addon / "lib" / "__init__.py")
        sys.modules["mpi_helpdesk_zoho.lib"] = lib
        sys.modules["mpi_helpdesk_zoho"].lib = lib
