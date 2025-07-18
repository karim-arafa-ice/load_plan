from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class WarehouseReturnWizard(models.TransientModel):
    _name = 'ice.warehouse.return.wizard'
    _description = 'Warehouse Return Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    line_ids = fields.One2many('ice.warehouse.return.wizard.line', 'wizard_id', string='Return Lines')

    @api.model
    def default_get(self, fields_list):
        """
        Aggregates product lines from all loading requests associated with the
        parent return request to populate the wizard.
        """
        res = super().default_get(fields_list)
        if self.env.context.get('default_loading_request_id'):
            loading_request = self.env['ice.loading.request'].browse(self.env.context.get('default_loading_request_id'))
            salesman_location = loading_request.salesman_id.accessible_location_id

            if not salesman_location:
                raise ValidationError(_("The salesman %s does not have an accessible stock location configured.") % return_request.salesman_id.name)
            product_map = {}  # To aggregate quantities: {product_id: loaded_quantity}
            if not loading_request.has_second_loading:
                # If no second loading, use the first loading product lines
                for line in loading_request.product_line_ids:
                    # Use a dictionary to sum up quantities per product
                    product_map.setdefault(line.product_id, 0.0)
                    product_map[line.product_id] += line.quantity
                    lines = []
                    for product, loaded_qty in product_map.items():
                        stock_quant = self.env['stock.quant'].search([
                            ('product_id', '=', product.id),
                            ('location_id', '=', salesman_location.id)
                        ], limit=1)
                        current_qty = stock_quant.quantity
                        lines.append((0, 0, {
                            'product_id': product.id,
                            'loaded_quantity': loaded_qty,
                        
                            'current_quantity': current_qty,
                            'returned_quantity': 0,
                            'scrap_quantity': 0,
                        }))
                    
                    res['line_ids'] = lines
            else:
                # If second loading, use the second loading product lines
                for line in loading_request.product_line_ids:
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                # Sum from second loading
                for line in loading_request.second_product_line_ids:
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                # Create wizard lines for all products
                for product_id, total_qty in product_map.items():
                    # You can also fetch current_qty here if needed
                    stock_quant = self.env['stock.quant'].search([
                            ('product_id', '=', product.id),
                            ('location_id', '=', salesman_location.id)
                        ], limit=1)
                    current_qty = stock_quant.quantity
                    lines.append((0, 0, {
                        'product_id': product_id,
                        'current_qty': current_qty,
                        'loaded_quantity': total_qty,
                        'returned_quantity': 0.0,
                        'scrap_quantity': 0.0,
                    }))
                     
                res['line_ids'] = lines           
        return res

    ###############################################

    def action_process_return(self):
        """
        This action will create the necessary stock moves for returned and scrapped goods.
        """
        self.ensure_one()
        # Logic to create an internal transfer for returned goods and a scrap order for scrapped goods
        # would be implemented here, using the data from self.line_ids.
        for line in self.line_ids:
            if line.current_quantity > 0:
                total = line.returned_quantity + line.scrap_quantity
                if abs(total - line.current_quantity) > 0.001:  # Small epsilon for float comparison
                    if total > line.current_quantity:
                        raise ValidationError(_(
                            "For product '%s', the sum of return quantity (%.2f) and scrap quantity (%.2f) "
                            "exceeds the current quantity (%.2f) by %.2f units."
                        ) % (line.product_id.name, line.returned_quantity, line.scrap_quantity, 
                             line.current_quantity, total - line.current_quantity))
                    else:
                        raise ValidationError(_(
                            "For product '%s', the sum of return quantity (%.2f) and scrap quantity (%.2f) "
                            "is less than the current quantity (%.2f) by %.2f units. All units must be accounted for."
                        ) % (line.product_id.name, line.returned_quantity, line.scrap_quantity, 
                             line.current_quantity, line.current_quantity - total))
            if line.returned_quantity > 0 or line.scrap_quantity > 0:
                if line.current_quantity <= 0:
                    # self.action_reload_products()
                    raise ValidationError(_(
                        "For product '%s', the current quantity must be greater than zero to process returns or scraps. click button refresh products"
                    ) % line.product_id.name)
        
        # Only proceed if there are quantities to return or scrap
        has_returns = any(line.returned_quantity > 0 for line in self.line_ids)
        has_scraps = any(line.scrap_quantity > 0 for line in self.line_ids)
        
        if has_returns:
            self.loading_request_id.return_picking_id = self._create_return_picking(self.line_ids.filtered(lambda l: l.returned_quantity > 0),self.loading_request_id)
            
        if has_scraps:
            self.loading_request_id.loading_scrap_orders_ids = self._create_scrap_orders(self.line_ids.filtered(lambda l: l.scrap_quantity > 0), self.loading_request_id)

        self.loading_request_id.is_warehouse_check = True

        # After processing, move the loading request to the next stage
        self.loading_request_id.message_post(body=_("Warehouse return processed by %s.") % self.env.user.name)
        return {'type': 'ir.actions.act_window_close'}

    def _create_return_picking(self, return_lines, loading_request):
        """Create an internal transfer for the returned products"""
        if not return_lines:
            return

        if not loading_request.loading_place_id.loading_location_id:
            raise UserError(_("Please specify a return warehouse."))
            
        # Find appropriate locations
        source_location = self.loading_request.salesman_id.accessible_location_id
        dest_location = loading_request.loading_place_id.loading_location_id
        
        # Create picking type - use internal transfer
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.source_location.warehouse_id.id)
        ], limit=1)
        
        if not picking_type:
            raise UserError(_("No internal transfer operation type found for the salesman warehouse."))
            
        # Create the return picking
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'scheduled_date': fields.Datetime.now(),
            'origin': self.name,
            'user_id': self.env.user.id,
            'company_id': self.company_id.id,
            'move_ids': [],
            'transfer_vehicle': self.loading_request.car_id.id,
        }
        
        # Add move lines
        for line in return_lines:
            move_vals = {
                'name': f"Return of {line.product_id.name}",
                'product_id': line.product_id.id,
                'product_uom_qty': line.returned_quantity,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            }
            picking_vals['move_ids'].append((0, 0, move_vals))
            
        # Create the picking
        picking = self.env['stock.picking'].create(picking_vals)
        self.return_picking_id = picking.id
        
        # Validate the picking immediately
        picking.action_confirm()  # Confirm the picking
        picking.action_assign()   # Reserve the picking
        
        # Check if it's immediately available 
        if picking.state == 'assigned':
            # Create a backorder if any move is not fully available
            for move_line in picking.move_line_ids:
                if move_line.quantity_product_uom != move_line.quantity:
                    move_line.quantity = move_line.quantity_product_uom
            
            # Validate the picking
            picking.button_validate()
        
        return picking

    def _create_scrap_orders(self, scrap_lines, loading_request_id):
        """Create scrap orders for the quantities to be scrapped"""
        if not scrap_lines:
            return
            
        scrap_location = self.company_id.scrap_location_id
        if not scrap_location:
            raise UserError(_("Please configure a scrap location in the company settings."))
            
        source_location = self.loading_request_id.salesman_id.accessible_location_id
        if not source_location:
            raise UserError(_("The salesman %s does not have an accessible stock location configured.") % self.loading_request_id.salesman_id.name)
            
        scrap_orders = self.env['stock.scrap']
        
        for line in scrap_lines:
            scrap_vals = {
                'product_id': line.product_id.id,
                'scrap_qty': line.scrap_quantity,
                'product_uom_id': line.product_id.uom_id.id,
                'location_id': source_location.id,
                'scrap_location_id': scrap_location.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'transfer_vehicle': self.loading_request_id.car_id.id,
            }
            
            scrap_order = self.env['stock.scrap'].create(scrap_vals)
            # line.scrap_id = scrap_order.id
            scrap_orders |= scrap_order
            
        # Do the scrap
        for scrap in scrap_orders:
            scrap.action_validate()
            
        return scrap_orders
        
    


class WarehouseReturnWizardLine(models.TransientModel):
    _name = 'ice.warehouse.return.wizard.line'
    _description = 'Warehouse Return Wizard Line'

    wizard_id = fields.Many2one('ice.warehouse.return.wizard', string='Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True)
    loaded_quantity = fields.Float(string='Total Loaded Qty', readonly=True)
    current_quantity = fields.Float(string='Current Qty in Van', readonly=True, store=True)
    returned_quantity = fields.Float(string='Returned Qty')
    scrap_quantity = fields.Float(string='Scrap Qty')

    @api.constrains('returned_quantity', 'scrap_quantity', 'current_quantity')
    def _check_quantities(self):
        """
        Ensures that the sum of returned and scrapped quantities equals the
        current quantity in the van.
        """
        for line in self:
            if line.returned_quantity < 0 or line.scrap_quantity < 0:
                raise ValidationError(_("Return and scrap quantities cannot be negative."))
            
            total_processed = line.returned_quantity + line.scrap_quantity
            if total_processed != line.current_quantity:
                raise ValidationError(_(
                    "For product '%s', the sum of Returned Qty (%.2f) and Scrap Qty (%.2f) must be exactly equal to the Current Qty in Van (%.2f)."
                ) % (line.product_id.name, line.returned_quantity, line.scrap_quantity, line.current_quantity))
