from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

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
            
            if not delivery:
                raise UserError(_('No delivery found for this customer line.'))
            
            if delivery.state in ('done', 'cancel'):
                raise UserError(_('Delivery is already processed or cancelled.'))
            
            _logger.info(f"Processing delivery {delivery.name} - updating quantity from {self.quantity_to_deliver} to {self.delivered_quantity}")
            
            # Method 1: Handle the stock moves and move lines properly
            self._update_delivery_quantities(delivery)
            
            # Update customer line with delivery info
            customer_line.write({
                'is_delivered': True,
                'quantity': self.delivered_quantity,  # Update actual delivered quantity
            })
            
            # Add delivery notes to picking if provided
            if self.delivery_notes:
                delivery.note = (delivery.note or '') + f"\nDelivery Notes: {self.delivery_notes}"
            
            # Check if all lines in the loading request are delivered
            loading_request = customer_line.loading_request_id
            if all(line.is_delivered for line in loading_request.customer_line_ids if line.quantity > 0):
                loading_request.write({'state': 'delivered'})
                _logger.info(f"All deliveries completed for loading request {loading_request.name}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Delivery completed successfully for customer %s. Quantity: %.2f') % (self.customer_id.name, self.delivered_quantity),
                    'type': 'success',
                    'sticky': False,
                }
            }
                
        except Exception as e:
            _logger.error(f"Error processing delivery: {str(e)}")
            raise UserError(_('Error processing delivery: %s') % str(e))

    def _update_delivery_quantities(self, delivery):
        """Update delivery quantities properly handling stock moves and move lines"""
        _logger.info(f"Updating delivery quantities for picking {delivery.name}")
        
        # Step 1: Unreserve the picking to free up stock reservations
        delivery.do_unreserve()
        _logger.info(f"Unreserved picking {delivery.name}")
        
        # Step 2: Update the demand quantities on stock moves
        for move in delivery.move_ids_without_package:
            old_qty = move.product_uom_qty
            move.write({
                'product_uom_qty': self.delivered_quantity,
            })
            _logger.info(f"Updated move {move.name}: {old_qty} -> {self.delivered_quantity}")
        
        # Step 3: Try to reserve the new quantities
        try:
            delivery.action_assign()
            _logger.info(f"Successfully reserved new quantities for picking {delivery.name}")
        except Exception as e:
            _logger.warning(f"Could not fully reserve picking {delivery.name}: {str(e)}. Will force assign.")
            self._force_assign_delivery_quantities(delivery)
        
        # Step 4: Validate the delivery
        if delivery.state == 'assigned' or delivery.move_line_ids:
            delivery.with_context(skip_backorder=True).button_validate()
            _logger.info(f"Successfully validated delivery {delivery.name}")
        else:
            raise UserError(_('Could not validate delivery. No stock available or reserved.'))

    def _force_assign_delivery_quantities(self, delivery):
        """Force assign quantities when automatic assignment fails"""
        _logger.info(f"Force assigning quantities for delivery {delivery.name}")
        
        # Delete existing move lines to start fresh
        delivery.move_line_ids.unlink()
        
        # Create new move lines with the delivered quantities
        for move in delivery.move_ids_without_package:
            if move.product_uom_qty > 0:
                move_line_vals = {
                    'move_id': move.id,
                    'picking_id': delivery.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': self.delivered_quantity,
                    'quantity_product_uom': self.delivered_quantity,
                }
                
                # Try to find an existing lot/serial if needed
                if move.product_id.tracking != 'none':
                    # For tracked products, you might need to handle lots/serials
                    # This is a simplified approach - adjust based on your needs
                    existing_quant = self.env['stock.quant'].search([
                        ('product_id', '=', move.product_id.id),
                        ('location_id', '=', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    if existing_quant and existing_quant.lot_id:
                        move_line_vals['lot_id'] = existing_quant.lot_id.id
                
                move_line = self.env['stock.move.line'].create(move_line_vals)
                _logger.info(f"Created move line for {move.product_id.name}: {self.delivered_quantity}")
        
        # Update picking state
        if delivery.state != 'assigned':
            delivery.write({'state': 'assigned'})

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}