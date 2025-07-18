from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')
    loading_driver_id = fields.Many2one('res.users',string="Driver",readonly=True)
    car_id = fields.Many2one('fleet.vehicle',string="Car",readonly=True)
    is_second_loading = fields.Boolean(string="Is Second Loading", readonly=True)

    def button_validate(self):
        # Storekeeper validation check
        if self.loading_request_id and self.loading_request_id.state not in ['loading']:
            raise UserError(_("You cannot validate the transfer. The car for request '%s' is not yet loaded.", self.loading_request_id.name))
        
        res = super(StockPicking, self).button_validate()
        
        if self.loading_request_id:
            if self.loading_request_id.state == 'loading':
                # Update loading request state to 'ice_handled' after validation
                request = self.loading_request_id
                request.write({'state': 'ice_handled'})

                if request.is_concrete:
                    # Create deliveries for each customer line
                    for line in request.customer_line_ids.filtered(lambda l: l.quantity > 0):
                        if line.sale_order_id:
                            picking = line.sale_order_id.picking_ids.filtered(lambda p: p.state == 'assigned' and p.picking_type_id.code == 'outgoing')
                            picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing'), ('warehouse_id', '=', request.car_id.location_id.warehouse_id.id)], limit=1)
                            picking.write({
                                'loading_request_id': request.id,
                                'loading_driver_id': self.loading_driver_id.id,
                                'car_id': self.car_id.id,
                                'picking_type_id': picking_type.id,
                                'location_id': request.car_id.location_id.id,
                            })
                            for line in picking.move_ids:
                                line.location_id = request.car_id.location_id.id
                            for move in picking.move_ids_without_package:
                                move.location_id = request.car_id.location_id.id
                            line.delivery_id = picking.id
        
        return res
    
    