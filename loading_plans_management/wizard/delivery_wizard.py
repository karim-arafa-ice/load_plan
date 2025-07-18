from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class DeliveryWizard(models.TransientModel):
    _name = 'delivery.wizard'
    _description = 'Delivery Wizard'

    # Direct fields instead of lines
    customer_line_id = fields.Many2one('ice.loading.customer.line', string='Customer Line', required=True, readonly=True)
    customer_id = fields.Many2one(related='customer_line_id.customer_id', string='Customer', readonly=True)
    delivery_id = fields.Many2one('stock.picking', string='Delivery', required=True, readonly=True)
    quantity_to_deliver = fields.Float(string='Planned Quantity', readonly=True)
    delivered_quantity = fields.Float(string='Actual Delivered Qty', required=True)
    delivery_notes = fields.Text(string='Delivery Notes')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Get the customer line from context
        customer_line_id = self.env.context.get('default_customer_line_id')
        if customer_line_id:
            customer_line = self.env['ice.loading.customer.line'].browse(customer_line_id)
            if customer_line.exists():
                res.update({
                    'customer_line_id': customer_line.id,
                    'delivery_id': customer_line.delivery_id.id if customer_line.delivery_id else False,
                    'quantity_to_deliver': customer_line.quantity,
                    'delivered_quantity': customer_line.quantity,  # Default to planned quantity
                })
        
        return res

    @api.constrains('delivered_quantity')
    def _check_delivered_quantity(self):
        """Validate delivered quantity"""
        for record in self:
            if record.delivered_quantity < 0:
                raise ValidationError(_('Delivered quantity cannot be negative.'))
            if record.delivered_quantity > record.quantity_to_deliver * 1.1:  # Allow 10% tolerance
                raise ValidationError(_('Delivered quantity (%.2f) cannot exceed planned quantity (%.2f) by more than 10%%.') % (record.delivered_quantity, record.quantity_to_deliver))

    def action_validate(self):
        """Process the delivery for this single line"""
        self.ensure_one()
        
        try:
            delivery = self.delivery_id
            customer_line = self.customer_line_id
            
            if delivery and delivery.state not in ('done', 'cancel'):
                # Update stock moves with delivered quantity
                for move in delivery.move_ids_without_package:
                    move.write({
                        'product_uom_qty': self.delivered_quantity,
                        'quantity': self.delivered_quantity,
                    })
                
                # Validate the delivery
                if delivery.state == 'assigned':
                    delivery.with_context(skip_backorder=True).button_validate()
                
                # Update customer line with delivery info
                customer_line.write({
                    'is_delivered': True,
                    'quantity': self.delivered_quantity,  # Update actual delivered quantity
                })
                
                
                
                # Check if all lines in the loading request are delivered
                loading_request = customer_line.loading_request_id
                if all(line.is_delivered for line in loading_request.customer_line_ids if line.quantity > 0):
                    loading_request.write({'state': 'delivered'})
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Delivery completed successfully for customer %s') % self.customer_id.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Delivery is already processed or cancelled.'))
                
        except Exception as e:
            raise UserError(_('Error processing delivery: %s') % str(e))

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}