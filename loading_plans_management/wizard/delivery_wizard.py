from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class DeliveryWizard(models.TransientModel):
    _name = 'delivery.wizard'
    _description = 'Delivery Wizard'

    # Fields for the wizard form
    customer_line_id = fields.Many2one('ice.loading.customer.line', string='Customer Line', required=True, readonly=True)
    customer_id = fields.Many2one(related='customer_line_id.customer_id', string='Customer', readonly=True)
    delivery_id = fields.Many2one('stock.picking', string='Delivery', required=True, readonly=True)
    quantity_to_deliver = fields.Float(string='Planned Quantity', readonly=True)
    delivered_quantity = fields.Float(string='Actual Delivered Qty', required=True)
    delivery_notes = fields.Text(string='Delivery Notes')

    @api.model
    def default_get(self, fields_list):
        """Populates the wizard with data from the customer line."""
        res = super().default_get(fields_list)
        
        customer_line_id = self.env.context.get('default_customer_line_id')
        if customer_line_id:
            customer_line = self.env['ice.loading.customer.line'].browse(customer_line_id)
            car_location = customer_line.loading_request_id.car_id.location_id
                
            # Filter the sale order's pickings to find the one from the car's location
            delivery_picking = customer_line.sale_order_id.picking_ids.filtered(
                lambda p: p.location_id == car_location and p.state not in ('done', 'cancel')
            )


            if customer_line.exists():
                res.update({
                    'customer_line_id': customer_line.id,
                    'delivery_id': delivery_picking[0].id if delivery_picking else False,
                    'quantity_to_deliver': customer_line.quantity,
                    'delivered_quantity': customer_line.quantity,
                })
        
        return res

    @api.constrains('delivered_quantity')
    def _check_delivered_quantity(self):
        """Validates the delivered quantity."""
        for record in self:
            if record.delivered_quantity < 0:
                raise ValidationError(_('Delivered quantity cannot be negative.'))
            # Allow a small tolerance for over-delivery if needed, e.g., 10%
            if record.delivered_quantity > record.quantity_to_deliver * 1.1:
                raise ValidationError(_('Delivered quantity (%.2f) cannot exceed planned quantity (%.2f) by more than 10%%.') % (record.delivered_quantity, record.quantity_to_deliver))

    def action_validate(self):
        """
        Processes the delivery. It sets the done quantity on the picking's move lines
        and then calls the standard button_validate method, which will handle
        backorder creation if the delivered quantity is less than the demand.
        """
        self.ensure_one()
        picking = self.delivery_id

        if not picking:
            raise UserError(_('No delivery found for this customer line.'))
        if picking.state in ('done', 'cancel'):
            raise UserError(_('This delivery is already processed or cancelled.'))

        # Assuming one product line for simplicity in this workflow.
        if len(picking.move_ids_without_package) != 1:
            raise UserError(_("This wizard currently only supports deliveries with a single product line."))

        move = picking.move_ids_without_package[0]

        # Clear any existing detailed operations for this move to avoid conflicts.
        move.move_line_ids.unlink()

        # Create a new move line with the actual delivered quantity.
        # This explicitly sets the "Done" quantity for the operation.
        self.env['stock.move.line'].create({
            'move_id': move.id,
            'picking_id': picking.id,
            'product_id': move.product_id.id,
            'location_id': move.location_id.id,
            'location_dest_id': move.location_dest_id.id,
            'quantity': self.delivered_quantity,
            'product_uom_id': move.product_uom.id,
        })

        # Call the standard validate button, but with a context key to bypass the
        # negative stock check that is causing the issue during backorder creation.
        res = picking.with_context(skip_negative_qty_check=True).button_validate()

        # Update our loading request records
        self.customer_line_id.write({
            'is_delivered': True,
            'quantity': self.delivered_quantity, # Update the line with the actual delivered qty
        })

        if self.delivery_notes:
            picking.message_post(body=f"Delivery Notes: {self.delivery_notes}")

        # Check if all lines in the loading request are now delivered
        loading_request = self.customer_line_id.loading_request_id
        if all(line.is_delivered for line in loading_request.customer_line_ids if line.quantity > 0):
            loading_request.write({'can_close_session': True})
            _logger.info(f"All deliveries completed for loading request {loading_request.name}")
        
        # If button_validate returned an action (like the backorder wizard), we must return it to the user.
        if isinstance(res, dict) and res.get('type') == 'ir.actions.act_window':
            return res
        
        # Otherwise, the validation is complete. Close the wizard and show a success notification.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Delivery processed for customer %s. Quantity: %.2f') % (self.customer_id.name, self.delivered_quantity),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Closes the wizard."""
        return {'type': 'ir.actions.act_window_close'}