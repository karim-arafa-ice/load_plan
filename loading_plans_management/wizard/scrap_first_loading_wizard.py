from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class ScrapProductsWizard(models.TransientModel):
    _name = 'ice.scrap.products.wizard'
    _description = 'Scrap Products Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    line_ids = fields.One2many('ice.scrap.products.line', 'wizard_id', string='Products')

    def _get_current_quantity_in_display_units(self, product, salesman_location):
        """Helper method to get current quantity in display units"""
        # Get the database cursor for a direct query
        cr = self.env.cr
        
        
        sql_query = """
            SELECT SUM(quantity)
            FROM stock_quant
            WHERE product_id = %s AND location_id = %s
        """
        cr.execute(sql_query, (product.id, salesman_location.id))
        query_result = cr.fetchone()
        
        current_qty_in_pcs = query_result[0] if query_result and query_result[0] is not None else 0.0
        
        # Convert the quantity from Pcs to the user-facing unit (Bags/Baskets) for display
        current_qty_display = current_qty_in_pcs
        
        if product.ice_product_type == '4kg' and (product.pcs_per_bag or 8) > 0:
            current_qty_display = current_qty_in_pcs / (product.pcs_per_bag or 8)
        elif product.ice_product_type == 'cup' and (product.pcs_per_basket or 24) > 0:
            current_qty_display = current_qty_in_pcs / (product.pcs_per_basket or 24)
            
        return current_qty_display, current_qty_in_pcs

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loading_request = self.env['ice.loading.request'].browse(self.env.context.get('default_loading_request_id'))
        
        if not loading_request:
            raise UserError(_("No loading request found in context."))
        salesman_location = False
        if loading_request.is_concrete:
            salesman_location = loading_request.car_id.location_id
        else:
            salesman_location = loading_request.salesman_id.accessible_location_id
        if not salesman_location:
            raise UserError(_("Salesman's stock location is not configured."))


        lines = []

        for line in loading_request.product_line_ids:
            product = line.product_id
            
            _logger.info(f"Processing product: {product.display_name} (ID: {product.id})")
            
            current_qty_display, current_qty_in_pcs = self._get_current_quantity_in_display_units(product, salesman_location)
            
            # Multiple method logging for debugging
            # Method 2: Using Odoo's stock quant method (for comparison)
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', salesman_location.id)
            ])
            current_qty_in_pcs_odoo = sum(quants.mapped('quantity'))
            _logger.info(f"SQL Query result for {product.display_name}: {current_qty_in_pcs} Pcs")
            _logger.info(f"Odoo quant search result for {product.display_name}: {current_qty_in_pcs_odoo} Pcs")
            
            # Method 3: Using product's qty_available (for comparison)
            product_with_location = product.with_context(location=salesman_location.id)
            current_qty_in_pcs_available = product_with_location.qty_available
            _logger.info(f"qty_available for {product.display_name}: {current_qty_in_pcs_available} Pcs")
            
            conversion_info = "Pcs"
            if product.ice_product_type == '4kg':
                conversion_info = f"Bags (Pcs: {current_qty_in_pcs}, Conversion: /{product.pcs_per_bag or 8})"
            elif product.ice_product_type == 'cup':
                conversion_info = f"Baskets (Pcs: {current_qty_in_pcs}, Conversion: /{product.pcs_per_basket or 24})"
            
            _logger.info(f"Final display quantity for {product.display_name}: {current_qty_display} {conversion_info}")

            lines.append((0, 0, {
                'product_id': product.id,
                'current_qty': current_qty_display,
                'scrap_qty': 0.0,
            }))
            
        res['line_ids'] = lines
        return res

    def action_validate(self):
        self.ensure_one()
        picking_moves = []
        request = self.loading_request_id
        salesman_location = False
        if request.is_concrete:
            salesman_location = request.car_id.location_id
        else:
            salesman_location = request.salesman_id.accessible_location_id
        
        
        # CRITICAL FIX: Refresh current quantities before validation
        for line in self.line_ids:
            if line.scrap_qty > 0:
                # Get fresh current quantity
                current_qty_display, current_qty_in_pcs = self._get_current_quantity_in_display_units(
                    line.product_id, salesman_location
                )
                
                _logger.info(f"Processing scrap for {line.product_id.display_name}: "
                           f"scrap_qty={line.scrap_qty}, "
                           f"stored_current_qty={line.current_qty}, "
                           f"fresh_current_qty={current_qty_display}")
                
                # Use the fresh quantity for validation, not the stored one
                if line.scrap_qty > current_qty_display:
                    error_msg = _(
                        'Scrap quantity for %s cannot be greater than current quantity.\n'
                        'Requested: %s\n'
                        'Available: %s (stored) / %s (current)\n'
                        'Location: %s'
                    ) % (
                        line.product_id.display_name, 
                        line.scrap_qty, 
                        line.current_qty,
                        current_qty_display,
                        salesman_location.display_name
                    )
                    raise UserError(error_msg)
                
                # Update the line with fresh quantity for consistency
                line.current_qty = current_qty_display
        
        # Process scraps
        created_scraps = []
        for line in self.line_ids:
            if line.scrap_qty > 0:
                # Create scrap order
                product = line.product_id
                scrap_qty_in_pcs = line.scrap_qty
                if product.ice_product_type == '4kg':
                    scrap_qty_in_pcs = line.scrap_qty * (product.pcs_per_bag or 8)
                elif product.ice_product_type == 'cup':
                    scrap_qty_in_pcs = line.scrap_qty * (product.pcs_per_basket or 24)
                
                _logger.info(f"Creating scrap for {product.display_name}: {scrap_qty_in_pcs} Pcs")
                
                scrap = self.env['stock.scrap'].create({
                    'product_id': line.product_id.id,
                    'scrap_qty': scrap_qty_in_pcs,
                    'product_uom_id': product.uom_id.id,
                    'location_id': request.salesman_id.accessible_location_id.id,
                    'origin': request.name,
                    'loading_request_id': request.id,  # Add this if the field exists
                })
                
                created_scraps.append(scrap.id)
                scrap.action_validate()
                
                # Update second loading lines
                second_line = self.env['second.ice.loading.product.line'].search([
                    ('loading_request_id', '=', request.id),
                    ('product_id', '=', line.product_id.id)
                ], limit=1)
                if second_line:
                    second_line.scrap_quantity = scrap_qty_in_pcs
                    second_line.quantity = second_line.requested_quantity
        
        # Update loading request with created scraps
        if created_scraps:
            request.first_loading_scrap_ids = [(6, 0, created_scraps)]
        
        # Create internal transfer for remaining quantities for the second load
        dest_location = request.salesman_id.accessible_location_id.id
        if request.is_concrete:
            dest_location = request.car_id.location_id.id
        for second_line in request.second_product_line_ids:
            if second_line.quantity > 0:
                picking_moves.append((0, 0, {
                    'name': second_line.product_id.display_name,
                    'product_id': second_line.product_id.id,
                    'product_uom_qty': second_line.quantity_in_pcs,
                    'product_uom': second_line.product_id.uom_id.id,
                    'location_id': request.loading_place_id.loading_location_id.id,
                    'location_dest_id': dest_location,
                }))
        
        # Create internal transfer for remaining quantities
        if picking_moves:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id.lot_stock_id', '=', request.loading_place_id.loading_location_id.id)
            ], limit=1)
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id if picking_type else False,
                'location_id': request.loading_place_id.loading_location_id.id,
                'location_dest_id': dest_location,
                'move_ids_without_package': picking_moves,
                'origin': request.name + ' (Second Load)',
                'car_id': request.car_id.id,
                'loading_request_id': request.id,
                'loading_driver_id': request.salesman_id.id,
                'transfer_vehicle': request.car_id.id,
                'is_second_loading': True,
            })
            picking.action_confirm()
            picking.action_assign()
            request.second_internal_transfer_id = picking.id
        
        self.loading_request_id.write({
            'state': 'ready_for_second_loading'
        })
        
        _logger.info(f"Scrap wizard completed successfully for {request.name}")
        return {'type': 'ir.actions.act_window_close'}

class ScrapProductsLine(models.TransientModel):
    _name = 'ice.scrap.products.line'
    _description = 'Scrap Products Line'

    wizard_id = fields.Many2one('ice.scrap.products.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    current_qty = fields.Float(string='Current Quantity')
    scrap_qty = fields.Float(string='Scrap Quantity')

    # Remove the constraint that's causing issues and rely on the wizard validation
    # @api.constrains('scrap_qty', 'current_qty')
    # def _check_scrap_quantity(self):
    #     """
    #     This constraint runs on save and provides a clear error if the scrap
    #     quantity is invalid.
    #     """
    #     for line in self:
    #         if line.scrap_qty < 0:
    #             raise ValidationError(_("Scrap quantity cannot be negative."))
    #         if line.scrap_qty > line.current_qty:
    #             raise ValidationError(_(
    #                 "Scrap quantity for %s cannot be greater than the current quantity (%s)."
    #             ) % (line.product_id.display_name, line.current_qty))

    @api.onchange('scrap_qty')
    def _onchange_scrap_qty(self):
        """
        This onchange provides immediate feedback to the user in the interface
        if they enter a value that is too high, preventing confusion.
        """
        if self.scrap_qty < 0:
            self.scrap_qty = 0
            return {
                'warning': {
                    'title': _("Invalid Quantity"),
                    'message': _("Scrap quantity cannot be negative."),
                }
            }
        if self.scrap_qty > self.current_qty:
            # Don't auto-adjust here, just warn
            return {
                'warning': {
                    'title': _("Quantity Check"),
                    'message': _(
                        "Scrap quantity (%s) appears to be greater than the stored current quantity (%s). "
                        "The system will validate against actual stock during save."
                    ) % (self.scrap_qty, self.current_qty)
                }
            }