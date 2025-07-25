from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    credit_limit = fields.Float(related='journal_id.credit_limit', string='Credit Limit', readonly=True)
    balance = fields.Float(related='journal_id.balance', string='Balance', readonly=True)