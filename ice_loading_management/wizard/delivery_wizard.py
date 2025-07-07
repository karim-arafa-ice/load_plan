from odoo import models, fields, api, _

class DeliveryWizard(models.TransientModel):
    _name = 'delivery.wizard'
    _description = 'Delivery Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    line_ids = fields.One2many('delivery.wizard.line', 'wizard_id', string='Delivery Lines')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loading_request_id = self.env.context.get('active_id')
        if loading_request_id:
            loading_request = self.env['ice.loading.request'].browse(loading_request_id)
            res['loading_request_id'] = loading_request.id
            lines = []
            for customer_line in loading_request.customer_line_ids.filtered(lambda l: l.delivery_id and not l.is_delivered):
                lines.append((0, 0, {
                    'customer_line_id': customer_line.id,
                    'delivery_id': customer_line.delivery_id.id,
                    'quantity_to_deliver': customer_line.quantity,
                    'delivered_quantity': customer_line.quantity,
                }))
            res['line_ids'] = lines
        return res

    def action_validate(self):
        for line in self.line_ids:
            delivery = line.delivery_id
            if delivery and delivery.state not in ('done', 'cancel'):
                for move in delivery.move_ids_without_package:
                    move.quantity = line.delivered_quantity
                
                delivery.with_context(skip_backorder=False).button_validate()
                
                line.customer_line_id.is_delivered = True
        
        loading_request = self.loading_request_id
        if all(line.is_delivered for line in loading_request.customer_line_ids if line.quantity > 0):
            loading_request.state = 'delivered'

class DeliveryWizardLine(models.TransientModel):
    _name = 'delivery.wizard.line'
    _description = 'Delivery Wizard Line'

    wizard_id = fields.Many2one('delivery.wizard', string='Wizard', required=True, ondelete='cascade')
    customer_line_id = fields.Many2one('ice.loading.customer.line', string='Customer Line', required=True, readonly=True)
    customer_id = fields.Many2one(related='customer_line_id.customer_id', string='Customer', readonly=True)
    delivery_id = fields.Many2one('stock.picking', string='Delivery', required=True, readonly=True)
    quantity_to_deliver = fields.Float(string='Planned Quantity', readonly=True)
    delivered_quantity = fields.Float(string='Actual Delivered Qty')