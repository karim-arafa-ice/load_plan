from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class LoadingQuantityChange(models.Model):
    _name = 'ice.loading.quantity.change'
    _description = 'Loading Request Quantity Change History'
    _order = 'change_date desc'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    old_quantity = fields.Float(string='Old Quantity', required=True)
    new_quantity = fields.Float(string='New Quantity', required=True)
    change_reason = fields.Text(string='Reason for Change', required=True)
    changed_by_id = fields.Many2one('res.users', string='Changed By', required=True, default=lambda self: self.env.user)
    change_date = fields.Datetime(string='Change Date', required=True, default=fields.Datetime.now)