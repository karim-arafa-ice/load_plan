
from odoo import models, fields, api

class AccountJournal(models.Model):
    """Populate factory part for account.journal."""

    _inherit = "account.journal"
        
    credit_limit = fields.Float(string='Credit Limit', help="The maximum allowed credit for this partner, used for salesman loading checks.")
