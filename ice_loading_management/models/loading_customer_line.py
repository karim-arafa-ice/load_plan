from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class LoadingCustomerLine(models.Model):
    _name = 'ice.loading.customer.line'
    _description = 'Loading Request Customer Line'

    def _get_customer_domain(self):
        """
        This method computes the domain for customers with open sale orders.
        An open sale order has a delivered quantity less than the ordered quantity.
        This is the corrected logic.
        """
        # Search for all potentially relevant sale orders
        all_orders = self.env['sale.order'].search([
            ('state', 'in', ['sale', 'done']),
            ('open_order', '=', True),  # Assuming 'open_order' is a computed field indicating open orders
            
        ])
        # ('order_line.qty_delivered', '!=', order_line.product_uom_qty)

        # Filter in Python to find orders with open lines
        # open_orders = all_orders.filtered(
        #     lambda order: any(line.qty_delivered < line.product_uom_qty for line in order.order_line)
        # )

        # Get the unique partners from these orders
        customer_ids = all_orders.mapped('partner_id').ids
        return [('customer_rank', '>', 0), ('id', 'in', customer_ids)]

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    customer_id = fields.Many2one(
        'res.partner', string='Customer', required=True,
        domain=lambda self: self._get_customer_domain()
    )
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    remaining_qty = fields.Float(string='Remaining Quantity', readonly=True)
    quantity = fields.Float(string='Quantity to Deliver')
    delivery_id = fields.Many2one('stock.picking', string='Delivery', readonly=True)
    is_delivered = fields.Boolean(string='Delivered', default=False)

    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        if self.customer_id:
            # Find the latest open sale order for the selected customer
            all_orders = self.env['sale.order'].search([
                ('partner_id', '=', self.customer_id.id),
                ('state', '=', 'sale'),
            ], order='date_order desc')

            last_open_order = self.env['sale.order']
            for order in all_orders:
                if any(line.product_uom_qty > line.qty_delivered for line in order.order_line):
                    last_open_order = order
                    break

            if last_open_order:
                self.sale_order_id = last_open_order.id
                remaining_qty = sum(
                    line.product_uom_qty - line.qty_delivered
                    for line in last_open_order.order_line
                )
                self.remaining_qty = remaining_qty
            else:
                self.sale_order_id = False
                self.remaining_qty = 0
        else:
            self.sale_order_id = False
            self.remaining_qty = 0

    @api.constrains('quantity', 'remaining_qty')
    def _check_quantity(self):
        for line in self:
            if line.quantity > line.remaining_qty:
                raise ValidationError(_("Quantity to deliver (%.2f) cannot be more than the remaining quantity (%.2f) for the selected sale order.") % (line.quantity, line.remaining_qty))

    @api.constrains('quantity')
    def _check_car_capacity(self):
        for line in self:
            if line.loading_request_id.is_concrete:
                total_quantity = sum(line.loading_request_id.customer_line_ids.mapped('quantity'))
                # Assuming 25kg bags for concrete requests
                total_weight = total_quantity * 25
                if total_weight > line.loading_request_id.car_id.total_weight_capacity:
                    raise ValidationError(_("Total weight of customer lines (%.2f kg) cannot exceed the car's capacity (%.2f kg).") % (total_weight, line.loading_request_id.car_id.total_weight_capacity))

    def button_print_delivery_slip(self):
        self.ensure_one()
        if self.delivery_id:
            return self.env.ref('stock.action_report_delivery').report_action(self.delivery_id)
        else:
            raise UserError(_("There is no delivery associated with this line yet. Deliveries are created after the main transfer is validated."))