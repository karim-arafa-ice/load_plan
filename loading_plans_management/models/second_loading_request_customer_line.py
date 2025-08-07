from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)
class SecondLoadingCustomerLine(models.Model):
    _name = 'second.ice.loading.customer.line'
    _description = 'Loading Request Customer Line'

    

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    
    customer_id = fields.Many2one(
        'res.partner', string='Customer', required=True
    )

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    quantity = fields.Float(string='Quantity to Deliver')
    delivery_id = fields.Many2one('stock.picking', string='Delivery', readonly=True)

    # def open_delivery_wizard(self):
    #     """Open wizard for delivery scheduling"""
    #     return {
    #         'name': 'Set Actual Delivery Quantity',
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'delivery.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {
    #             'default_customer_line_id': self.id,
    #         }
    #     }

    
            

    @api.constrains('quantity')
    def _check_car_capacity(self):
        for line in self:
            if line.loading_request_id.is_concrete:
                total_quantity = sum(line.loading_request_id.second_customer_line_ids.mapped('quantity'))
                product = self.env['product.template'].search([('ice_product_type', '=', '25kg')], limit=1)
                # Assuming 25kg bags for concrete requests
                total_weight = total_quantity * product.weight if product.weight else 0
                if total_weight > line.loading_request_id.car_id.total_weight_capacity:
                    raise ValidationError(_("Total weight of customer lines (%.2f kg) cannot exceed the car's capacity (%.2f kg).") % (total_weight, line.loading_request_id.car_id.total_weight_capacity))

    def button_print_delivery_slip(self):
        self.ensure_one()
        if self.delivery_id:
            return self.env.ref('stock.action_report_delivery').report_action(self.delivery_id)
        else:
            raise UserError(_("There is no delivery associated with this line yet. Deliveries are created after the main transfer is validated."))