from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class LoadingWorkerWizard(models.TransientModel):
    _name = 'second.ice.loading.worker.wizard'
    _description = 'Loading Worker Wizard'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    
    # Store the product data directly in the wizard
    product_1_id = fields.Many2one('product.product', string='Product 1', readonly=True)
    product_1_requested = fields.Float(string='Requested Qty 1', readonly=True)
    product_1_loaded = fields.Float(string='Actually Loaded 1')
    
    product_2_id = fields.Many2one('product.product', string='Product 2', readonly=True)
    product_2_requested = fields.Float(string='Requested Qty 2', readonly=True)
    product_2_loaded = fields.Float(string='Actually Loaded 2')
    
    product_3_id = fields.Many2one('product.product', string='Product 3', readonly=True)
    product_3_requested = fields.Float(string='Requested Qty 3', readonly=True)
    product_3_loaded = fields.Float(string='Actually Loaded 3')
    
    # Display fields
    car_name = fields.Char(related='loading_request_id.car_id.license_plate', readonly=True)
    salesman_name = fields.Char(related='loading_request_id.salesman_id.name', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        loading_request_id = self.env.context.get('default_loading_request_id')
        
        if loading_request_id:
            loading_request = self.env['ice.loading.request'].browse(loading_request_id)
            defaults['loading_request_id'] = loading_request_id
            
            # Get the product lines and populate fields directly
            product_lines = loading_request.second_product_line_ids.filtered(lambda l: l.quantity > 0)
            
            if len(product_lines) >= 1:
                line = product_lines[0]
                defaults['product_1_id'] = line.product_id.id
                defaults['product_1_requested'] = line.quantity
                defaults['product_1_loaded'] = line.quantity
                
            if len(product_lines) >= 2:
                line = product_lines[1]
                defaults['product_2_id'] = line.product_id.id
                defaults['product_2_requested'] = line.quantity
                defaults['product_2_loaded'] = line.quantity
                
            if len(product_lines) >= 3:
                line = product_lines[2]
                defaults['product_3_id'] = line.product_id.id
                defaults['product_3_requested'] = line.quantity
                defaults['product_3_loaded'] = line.quantity
        
        return defaults
    
    def action_confirm_loading(self):
        """Confirm and complete the loading"""
        self.ensure_one()
        
        # Check permissions
        if not self.env.user.has_group('loading_plans_management.group_loading_worker'):
            raise UserError(_('Only Loading Workers can complete loading operations.'))
        
        # Get the stock picking
        picking = self.loading_request_id.second_internal_transfer_id
        if not picking:
            raise UserError(_('No internal transfer found.'))
        
        # Check for differences and show confirmation if needed
        differences = []
        if self.product_1_id and self.product_1_loaded < self.product_1_requested:
            raise UserError(_('Product 1 loaded quantity cannot be less than requested.'))
        if self.product_2_id and self.product_2_loaded < self.product_2_requested:
            raise UserError(_('Product 2 loaded quantity cannot be less than requested.'))
        if self.product_3_id and self.product_3_loaded < self.product_3_requested:
            raise UserError(_('Product 3 loaded quantity cannot be less than requested.'))
        if self.product_1_id and self.product_1_loaded > self.product_1_requested:
            differences.append(f"{self.product_1_id.name}: {self.product_1_loaded} vs {self.product_1_requested}")
        if self.product_2_id and self.product_2_loaded > self.product_2_requested:
            differences.append(f"{self.product_2_id.name}: {self.product_2_loaded} vs {self.product_2_requested}")
        if self.product_3_id and self.product_3_loaded > self.product_3_requested:
            differences.append(f"{self.product_3_id.name}: {self.product_3_loaded} vs {self.product_3_requested}")
        
        if differences:
            # Show confirmation dialog
            return {
                'type': 'ir.actions.act_window',
                'name': 'Confirm Differences',
                'res_model': 'second.ice.loading.confirm.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_parent_wizard_id': self.id,
                    'default_differences': '\n'.join(differences),
                }
            }
        else:
            # No differences, complete directly
            return self._complete_loading()
    
    def _complete_loading(self):
        """Complete the actual loading process"""
        picking = self.loading_request_id.second_internal_transfer_id
        
        # Track quantity changes for chatter
        quantity_changes = []
        
        # Update quantities in loading request product lines AND stock moves
        if self.product_1_id:
            # Find the product line in loading request
            product_line = self.loading_request_id.second_product_line_ids.filtered(
                lambda l: l.product_id == self.product_1_id
            )
            if product_line:
                old_qty = product_line.quantity
                if old_qty != self.product_1_loaded:
                    quantity_changes.append({
                        'product': self.product_1_id.name,
                        'old_qty': old_qty,
                        'new_qty': self.product_1_loaded
                    })
                    # Update the loading request line
                    product_line.write({'quantity': self.product_1_loaded})
            
            # Update stock move
            move = picking.move_ids_without_package.filtered(lambda m: m.product_id == self.product_1_id)
            if move:
                move.write({'product_uom_qty': self.product_1_loaded, 'quantity': self.product_1_loaded})
        
        if self.product_2_id:
            # Find the product line in loading request
            product_line = self.loading_request_id.second_product_line_ids.filtered(
                lambda l: l.product_id == self.product_2_id
            )
            if product_line:
                old_qty = product_line.quantity
                if old_qty != self.product_2_loaded:
                    quantity_changes.append({
                        'product': self.product_2_id.name,
                        'old_qty': old_qty,
                        'new_qty': self.product_2_loaded
                    })
                    # Update the loading request line
                    product_line.write({'quantity': self.product_2_loaded})
            
            # Update stock move
            move = picking.move_ids_without_package.filtered(lambda m: m.product_id == self.product_2_id)
            if move:
                move.write({'product_uom_qty': self.product_2_loaded, 'quantity': self.product_2_loaded})
        
        if self.product_3_id:
            # Find the product line in loading request
            product_line = self.loading_request_id.second_product_line_ids.filtered(
                lambda l: l.product_id == self.product_3_id
            )
            if product_line:
                old_qty = product_line.quantity
                if old_qty != self.product_3_loaded:
                    quantity_changes.append({
                        'product': self.product_3_id.name,
                        'old_qty': old_qty,
                        'new_qty': self.product_3_loaded
                    })
                    # Update the loading request line
                    product_line.write({'quantity': self.product_3_loaded})
            
            # Update stock move
            move = picking.move_ids_without_package.filtered(lambda m: m.product_id == self.product_3_id)
            if move:
                move.write({'product_uom_qty': self.product_3_loaded, 'quantity': self.product_3_loaded})
        
        # Create/update move lines
        for move in picking.move_ids_without_package:
            if move.move_line_ids:
                for move_line in move.move_line_ids:
                    move_line.quantity = move.product_uom_qty
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': move.product_uom_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'picking_id': picking.id,
                })
        
        # Validate picking
        picking.button_validate()
        
        # Update loading request
        self.loading_request_id.write({'state': 'second_loading_done'})
        
        # Create detailed chatter message
        message_parts = [f"<p><strong>Loading completed by {self.env.user.name}</strong></p>"]
        
        # Add quantity changes to message
        if quantity_changes:
            message_parts.append("<p><strong>📝 Quantity Changes:</strong></p><ul>")
            for change in quantity_changes:
                message_parts.append(
                    f"<li><strong>{change['product']}:</strong> "
                    f"Changed from <span style='color: #dc3545;'>{change['old_qty']:.0f}</span> "
                    f"to <span style='color: #28a745;'>{change['new_qty']:.0f}</span></li>"
                )
            message_parts.append("</ul>")
        
        # Add final loaded quantities
        message_parts.append("<p><strong>📦 Final Loaded Quantities:</strong></p><ul>")
        if self.product_1_id:
            message_parts.append(f"<li><strong>{self.product_1_id.name}:</strong> {self.product_1_loaded:.0f}</li>")
        if self.product_2_id:
            message_parts.append(f"<li><strong>{self.product_2_id.name}:</strong> {self.product_2_loaded:.0f}</li>")
        if self.product_3_id:
            message_parts.append(f"<li><strong>{self.product_3_id.name}:</strong> {self.product_3_loaded:.0f}</li>")
        message_parts.append("</ul>")
        
        # Add transfer information
        message_parts.append(f"<p><strong>📋 Transfer Details:</strong></p>")
        message_parts.append(f"<ul><li><strong>Transfer:</strong> {picking.name}</li>")
        message_parts.append(f"<li><strong>Status:</strong> Validated</li>")
        message_parts.append(f"<li><strong>Loading Date:</strong> {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}</li></ul>")
        
        final_message = ''.join(message_parts)
        
        # Post message to chatter
        self.loading_request_id.message_post(
            body=final_message,
            subject='🚛 Loading Completed - Quantities Updated',
            message_type='comment'
        )
        
        # Also update the total weight computation
        # self.loading_request_id._compute_total_weight()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Loading Completed Successfully',
                'message': f'Transfer {picking.name} validated and quantities updated.',
                'type': 'success',
                'sticky': False,
            }
        }


class LoadingConfirmWizard(models.TransientModel):
    _name = 'second.ice.loading.confirm.wizard'
    _description = 'Loading Confirmation Wizard'
    
    parent_wizard_id = fields.Many2one('second.ice.loading.worker.wizard', required=True)
    differences = fields.Text(string='Differences Found', readonly=True)
    
    def action_proceed(self):
        """Proceed with the differences"""
        return self.parent_wizard_id._complete_loading()
    
    def action_cancel(self):
        """Go back to edit"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'second.ice.loading.worker.wizard',
            'res_id': self.parent_wizard_id.id,
            'view_mode': 'form',
            'target': 'new',
        }