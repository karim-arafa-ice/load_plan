from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')
    loading_driver_id = fields.Many2one('res.users', string="Driver", readonly=True)
    car_id = fields.Many2one('fleet.vehicle', string="Car", readonly=True)
    is_second_loading = fields.Boolean(string="Is Second Loading", readonly=True)

    def button_validate(self):
        # First, call the original validation logic
        res = super(StockPicking, self).button_validate()
        if self.loading_request_id:
            if self.is_second_loading and self.loading_request_id.state == 'started_second_loading':
                self.loading_request_id.write({'state': 'second_loading_delivering'})
                _logger.info("Second loading transfer validated. Updated request %s to 'second_loading_done'", self.loading_request_id.name)
            elif not self.is_second_loading and self.loading_request_id.state == 'loading':
                self.loading_request_id.write({'state': 'ice_handled'})
                _logger.info("First loading transfer validated. Updated request %s to 'ice_handled'", self.loading_request_id.name)

        return res

