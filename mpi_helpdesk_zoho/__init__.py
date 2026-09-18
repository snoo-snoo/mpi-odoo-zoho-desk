# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

try:
    from . import controllers
    from . import models
except ImportError:
    # Policy tests import lib without an Odoo install on PYTHONPATH.
    pass
