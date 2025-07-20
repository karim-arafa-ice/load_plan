from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class WarehouseReturnWizard(models.TransientModel):
    _name = 'ice.warehouse.return.wizard'
    _description = 'Warehouse Return Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    line_ids = fields.One2many('ice.warehouse.return.wizard.line', 'wizard_id', string='Return Lines')

    @api.model_create_multi  
    def create(self, vals_list):
        """Override create to debug wizard creation"""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== WIZARD CREATE DEBUG ===")
        for vals in vals_list:
            _logger.info(f"Creating wizard with vals: {vals}")
            if 'line_ids' in vals:
                _logger.info(f"Line IDs data: {vals['line_ids']}")
        
        result = super().create(vals_list)
        _logger.info(f"Created wizard: {result.id}")
        return result

    @api.model
    def default_get(self, fields_list):
        """
        Aggregates product lines from all loading requests associated with the
        parent return request to populate the wizard.
        """
        res = super().default_get(fields_list)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== WIZARD DEBUG: Starting default_get ===")
        _logger.info(f"Context: {self.env.context}")
        _logger.info(f"Fields list: {fields_list}")
        
        # Only populate lines if we have the loading request context and line_ids is requested
        if self.env.context.get('default_loading_request_id') and 'line_ids' in fields_list:
            loading_request = self.env['ice.loading.request'].browse(self.env.context.get('default_loading_request_id'))
            salesman_location = loading_request.salesman_id.accessible_location_id

            if not salesman_location:
                raise ValidationError(_("The salesman %s does not have an accessible stock location configured.") % loading_request.salesman_id.name)
            
            product_map = {}  # To aggregate quantities: {product_id: loaded_quantity}
            lines = []  # Initialize lines list outside conditions
            
            _logger.info(f"Loading request: {loading_request.name}")
            _logger.info(f"Has second loading: {loading_request.has_second_loading}")
            
            if not loading_request.has_second_loading:
                # If no second loading, use the first loading product lines
                _logger.info("Processing first loading only")
                for line in loading_request.product_line_ids:
                    _logger.info(f"Processing product: {line.product_id.name} (ID: {line.product_id.id}), qty: {line.quantity}")
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                
                # Create wizard lines for all products
                for product_id, loaded_qty in product_map.items():
                    product = self.env['product.product'].browse(product_id)
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product_id),
                        ('location_id', '=', salesman_location.id)
                    ], limit=1)
                    current_qty = stock_quant.quantity if stock_quant else 0.0
                    
                    line_vals = {
                        'product_id': product_id,
                        'loaded_quantity': loaded_qty,
                        'current_quantity': current_qty,
                        'returned_quantity': 0.0,
                        'scrap_quantity': 0.0,
                    }
                    _logger.info(f"Creating line for product {product.name}: {line_vals}")
                    lines.append((0, 0, line_vals))
            else:
                # If second loading, use both first and second loading product lines
                _logger.info("Processing both first and second loading")
                # Sum from first loading
                for line in loading_request.product_line_ids:
                    _logger.info(f"First loading - Product: {line.product_id.name} (ID: {line.product_id.id}), qty: {line.quantity}")
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                
                # Sum from second loading
                for line in loading_request.second_product_line_ids:
                    _logger.info(f"Second loading - Product: {line.product_id.name} (ID: {line.product_id.id}), qty: {line.quantity}")
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                
                # Create wizard lines for all products
                for product_id, total_qty in product_map.items():
                    product = self.env['product.product'].browse(product_id)
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product_id),
                        ('location_id', '=', salesman_location.id)
                    ], limit=1)
                    current_qty = stock_quant.quantity if stock_quant else 0.0
                    
                    line_vals = {
                        'product_id': product_id,
                        'loaded_quantity': total_qty,
                        'current_quantity': current_qty,
                        'returned_quantity': 0.0,
                        'scrap_quantity': 0.0,
                    }
                    _logger.info(f"Creating line for product {product.name}: {line_vals}")
                    lines.append((0, 0, line_vals))
            
            _logger.info(f"Final lines to be created: {len(lines)} lines")
            for i, line in enumerate(lines):
                _logger.info(f"Line {i}: {line}")
            
            res['line_ids'] = lines
        
        _logger.info(f"=== WIZARD DEBUG: Final res = {res} ===")
        return res

    def action_reload_products(self):
        """Reload products from loading request"""
        self.ensure_one()
        if not self.loading_request_id:
            return
            
        # Clear existing lines
        self.line_ids.unlink()
        
        # Reload lines using same logic as default_get
        salesman_location = self.loading_request_id.salesman_id.accessible_location_id
        if not salesman_location:
            raise ValidationError(_("The salesman %s does not have an accessible stock location configured.") % self.loading_request_id.salesman_id.name)
        
        product_map = {}
        lines = []
        
        if not self.loading_request_id.has_second_loading:
            for line in self.loading_request_id.product_line_ids:
                if line.product_id.id not in product_map:
                    product_map[line.product_id.id] = 0.0
                product_map[line.product_id.id] += line.quantity
        else:
            # Sum from both loadings
            for line in self.loading_request_id.product_line_ids:
                if line.product_id.id not in product_map:
                    product_map[line.product_id.id] = 0.0
                product_map[line.product_id.id] += line.quantity
            
            for line in self.loading_request_id.second_product_line_ids:
                if line.product_id.id not in product_map:
                    product_map[line.product_id.id] = 0.0
                product_map[line.product_id.id] += line.quantity
        
        # Create new lines
        for product_id, loaded_qty in product_map.items():
            stock_quant = self.env['stock.quant'].search([
                ('product_id', '=', product_id),
                ('location_id', '=', salesman_location.id)
            ], limit=1)
            current_qty = stock_quant.quantity if stock_quant else 0.0
            
            self.env['ice.warehouse.return.wizard.line'].create({
                'wizard_id': self.id,
                'product_id': product_id,
                'loaded_quantity': loaded_qty,
                'current_quantity': current_qty,
                'returned_quantity': 0.0,
                'scrap_quantity': 0.0,
            })

    def action_process_return(self):
        """
        This action will create the necessary stock moves for returned and scrapped goods.
        """
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_("No products to return or scrap. Please add product lines first."))
        
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
                    raise ValidationError(_(
                        "For product '%s', the current quantity must be greater than zero to process returns or scraps. click button refresh products"
                    ) % line.product_id.name)
        
        # Only proceed if there are quantities to return or scrap
        has_returns = any(line.returned_quantity > 0 for line in self.line_ids)
        has_scraps = any(line.scrap_quantity > 0 for line in self.line_ids)
        
        if has_returns:
            self.loading_request_id.return_picking_id = self._create_return_picking(
                self.line_ids.filtered(lambda l: l.returned_quantity > 0), 
                self.loading_request_id
            )
            
        if has_scraps:
            self.loading_request_id.loading_scrap_orders_ids = self._create_scrap_orders(
                self.line_ids.filtered(lambda l: l.scrap_quantity > 0), 
                self.loading_request_id
            )

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
        source_location = loading_request.salesman_id.accessible_location_id
        dest_location = loading_request.loading_place_id.loading_location_id
        
        # Create picking type - use internal transfer
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', source_location.warehouse_id.id)
        ], limit=1)
        
        if not picking_type:
            raise UserError(_("No internal transfer operation type found for the salesman warehouse."))
            
        # Create the return picking
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'scheduled_date': fields.Datetime.now(),
            'origin': loading_request.name,  # Fixed: was using self.name which doesn't exist
            'user_id': self.env.user.id,
            'move_ids': [],
            'transfer_vehicle': loading_request.car_id.id,
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

    def _create_scrap_orders(self, scrap_lines, loading_request):
        """Create scrap orders for the quantities to be scrapped"""
        if not scrap_lines:
            return
            
        scrap_location = self.env.company.scrap_location_id 
        if not scrap_location:
            raise UserError(_("Please configure a scrap location in the company settings."))
            
        source_location = loading_request.salesman_id.accessible_location_id
        if not source_location:
            raise UserError(_("The salesman %s does not have an accessible stock location configured.") % loading_request.salesman_id.name)
            
        scrap_orders = self.env['stock.scrap']
        
        for line in scrap_lines:
            scrap_vals = {
                'product_id': line.product_id.id,
                'scrap_qty': line.scrap_quantity,
                'product_uom_id': line.product_id.uom_id.id,
                'location_id': source_location.id,
                'scrap_location_id': scrap_location.id,
                'origin': loading_request.name,  # Fixed: use loading_request.name
                'transfer_vehicle': loading_request.car_id.id,
            }
            
            scrap_order = self.env['stock.scrap'].create(scrap_vals)
            scrap_orders |= scrap_order
            
        # Do the scrap
        for scrap in scrap_orders:
            scrap.action_validate()
            
        return scrap_orders


class WarehouseReturnWizardLine(models.TransientModel):
    _name = 'ice.warehouse.return.wizard.line'
    _description = 'Warehouse Return Wizard Line'

    wizard_id = fields.Many2one('ice.warehouse.return.wizard', string='Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    loaded_quantity = fields.Float(string='Total Loaded Qty', readonly=True)
    current_quantity = fields.Float(string='Current Qty in Van', readonly=True, store=True)
    returned_quantity = fields.Float(string='Returned Qty')
    scrap_quantity = fields.Float(string='Scrap Qty')

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure product_id and loaded_quantity are set"""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== WIZARD LINE CREATE DEBUG ===")
        _logger.info(f"vals_list: {vals_list}")
        
        # Get the wizard to retrieve the original line data
        wizard_id = vals_list[0].get('wizard_id') if vals_list else None
        if wizard_id:
            wizard = self.env['ice.warehouse.return.wizard'].browse(wizard_id)
            loading_request = wizard.loading_request_id
            salesman_location = loading_request.salesman_id.accessible_location_id
            
            # Rebuild the product map like in default_get
            product_map = {}
            if not loading_request.has_second_loading:
                for line in loading_request.product_line_ids:
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
            else:
                for line in loading_request.product_line_ids:
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
                for line in loading_request.second_product_line_ids:
                    if line.product_id.id not in product_map:
                        product_map[line.product_id.id] = 0.0
                    product_map[line.product_id.id] += line.quantity
            
            # Convert product_map to a list matching the order of vals_list
            product_list = list(product_map.items())
            
            # Ensure we have the same number of products as vals
            if len(product_list) != len(vals_list):
                _logger.warning(f"Mismatch: {len(product_list)} products vs {len(vals_list)} vals")
            
            # Fill in missing product_id and loaded_quantity for each vals
            for i, vals in enumerate(vals_list):
                if i < len(product_list):
                    product_id, loaded_qty = product_list[i]
                    if 'product_id' not in vals or not vals.get('product_id'):
                        vals['product_id'] = product_id
                        _logger.info(f"Set missing product_id to {product_id}")
                    
                    if 'loaded_quantity' not in vals:
                        vals['loaded_quantity'] = loaded_qty
                        _logger.info(f"Set missing loaded_quantity to {loaded_qty}")
                
                _logger.info(f"Final vals for line {i}: {vals}")
        
        result = super().create(vals_list)
        _logger.info(f"Created wizard lines: {result.ids}")
        return result

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