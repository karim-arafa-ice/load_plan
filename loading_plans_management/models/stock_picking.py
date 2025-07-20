from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')
    loading_driver_id = fields.Many2one('res.users', string="Driver", readonly=True)
    car_id = fields.Many2one('fleet.vehicle', string="Car", readonly=True)
    is_second_loading = fields.Boolean(string="Is Second Loading", readonly=True)

    def button_validate(self):
        # Storekeeper validation check
        if self.loading_request_id:
            # Different allowed states based on whether this is a second loading transfer
            if self.is_second_loading:
                allowed_states = ['started_second_loading', 'second_loading_done']
                error_context = "second loading transfer"
            else:
                allowed_states = ['loading', 'ice_handled', 'session_closed']
                error_context = "first loading transfer"
                
            if self.loading_request_id.state not in allowed_states:
                raise UserError(_(
                    "You cannot validate the %s. The loading request '%s' is in state '%s'. "
                    "Allowed states for %s are: %s"
                ) % (
                    error_context,
                    self.loading_request_id.name, 
                    self.loading_request_id.state, 
                    error_context,
                    ', '.join(allowed_states)
                ))
        
        # Check and handle stock reservation before validation
        if self.state in ['confirmed', 'waiting', 'partially_available']:
            _logger.info("Picking %s is not fully assigned. Attempting to assign stock.", self.name)
            try:
                # Try to assign stock first
                self.action_assign()
                
                if self.state != 'assigned':
                    _logger.warning("Could not fully assign stock for picking %s. Forcing validation.", self.name)
                    # Force validation by setting quantities on move lines
                    self._force_assign_quantities()
                    
            except Exception as e:
                _logger.warning("Failed to assign stock for picking %s: %s. Forcing validation.", self.name, str(e))
                self._force_assign_quantities()
        
        res = super(StockPicking, self).button_validate()
        
        if self.loading_request_id:
            # Handle state transitions based on transfer type
            if self.is_second_loading and self.loading_request_id.state == 'started_second_loading':
                # Update loading request state to 'second_loading_done' after second loading validation
                request = self.loading_request_id
                request.write({'state': 'second_loading_done'})
                _logger.info("Second loading transfer validated. Updated request %s to 'second_loading_done'", request.name)
                
            elif not self.is_second_loading and self.loading_request_id.state == 'loading':
                # Update loading request state to 'ice_handled' after first loading validation
                request = self.loading_request_id
                request.write({'state': 'ice_handled'})
                _logger.info("First loading transfer validated. Updated request %s to 'ice_handled'", request.name)

            if request.is_concrete:
                # Create deliveries for each customer line
                for customer_line in request.customer_line_ids.filtered(lambda l: l.quantity > 0):
                    if customer_line.sale_order_id:
                        self._update_delivery_picking_sql(customer_line, request)
        
        return res

    def _force_assign_quantities(self):
        """Force assign quantities to move lines to allow validation"""
        _logger.info("Force assigning quantities for picking %s", self.name)
        
        for move in self.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
            if not move.move_line_ids:
                # Create move lines if they don't exist
                move._create_move_line_ids()
            
            # Ensure move lines have the required quantities
            total_qty_needed = move.product_uom_qty
            total_qty_assigned = sum(move.move_line_ids.mapped('quantity_product_uom'))
            
            if total_qty_assigned < total_qty_needed:
                qty_to_assign = total_qty_needed - total_qty_assigned
                
                # Find or create a move line to assign the missing quantity
                if move.move_line_ids:
                    # Use existing move line
                    move_line = move.move_line_ids[0]
                    move_line.quantity_product_uom += qty_to_assign
                else:
                    # Create new move line
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'picking_id': self.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'quantity_product_uom': qty_to_assign,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    })
                
                _logger.info("Assigned %.2f %s for move %s", qty_to_assign, move.product_uom.name, move.name)
        
        # Update picking state
        if self.state != 'assigned':
            self.write({'state': 'assigned'})

    
    def _update_delivery_picking_sql(self, customer_line, request):
        """Update delivery picking to use existing stock in car location"""
        
        # Find the delivery picking
        delivery_picking = self.env['stock.picking'].search([
            ('origin', '=', customer_line.sale_order_id.name),
            ('state', '=', 'assigned'),
            ('picking_type_id.code', '=', 'outgoing')
        ], limit=1)
        
        if not delivery_picking:
            # Also try to find by sale_id
            delivery_picking = self.env['stock.picking'].search([
                ('sale_id', '=', customer_line.sale_order_id.id),
                ('state', '=', 'assigned'),
                ('picking_type_id.code', '=', 'outgoing')
            ], limit=1)
        
        if not delivery_picking:
            _logger.warning("No ready outgoing delivery found for sale order %s", customer_line.sale_order_id.name)
            return
        
        _logger.info("Updating picking %s to use existing car stock", delivery_picking.name)
        
        try:
            car_location = request.car_id.location_id
            
            # Step 1: Completely unreserve the picking to free all stock reservations
            delivery_picking.do_unreserve()
            _logger.info("Unreserved all stock for picking %s", delivery_picking.name)
            
            # Step 2: Update picking location and details
            delivery_picking.write({
                'loading_request_id': request.id,
                'loading_driver_id': self.loading_driver_id.id,
                'car_id': self.car_id.id,
                'location_id': car_location.id,
            })
            
            # Step 3: Update all moves to use car location and correct quantities
            for move in delivery_picking.move_ids_without_package:
                # Update move with car location and customer quantity
                move.write({
                    'location_id': car_location.id,
                    'product_uom_qty': customer_line.quantity,  # Use customer_line.quantity
                })
                
                _logger.info("Updated move %s: quantity=%.2f, location=%s", 
                            move.name, customer_line.quantity, car_location.name)
            
            # Step 4: Try automatic stock assignment first
            delivery_picking.action_assign()
            
            # Step 5: Check if assignment was successful
            if delivery_picking.state != 'assigned':
                _logger.info("Auto-assignment incomplete for %s. Checking stock and forcing assignment.", delivery_picking.name)
                
                # Force assignment by creating proper move lines with quant reservation
                for move in delivery_picking.move_ids_without_package:
                    product = move.product_id
                    quantity_needed = customer_line.quantity
                    
                    # Find available stock quants in car location
                    available_quants = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', car_location.id),
                        ('quantity', '>', 'reserved_quantity')  # Only quants with available stock
                    ], order='in_date')
                    
                    if not available_quants:
                        raise UserError(_(
                            "No available stock found for %s in car location %s"
                        ) % (product.name, car_location.name))
                    
                    # Calculate total available
                    total_available = sum(quant.quantity - quant.reserved_quantity for quant in available_quants)
                    _logger.info("Available stock for %s in %s: %.2f (needed: %.2f)", 
                            product.name, car_location.name, total_available, quantity_needed)
                    
                    if total_available < quantity_needed:
                        raise UserError(_(
                            "Not enough stock available for %s in car location %s. "
                            "Available: %.2f, Required: %.2f"
                        ) % (product.name, car_location.name, total_available, quantity_needed))
                    
                    # Clear existing move lines
                    move.move_line_ids.unlink()
                    
                    # Reserve stock and create move lines
                    remaining_qty = quantity_needed
                    for quant in available_quants:
                        if remaining_qty <= 0:
                            break
                        
                        available_in_quant = quant.quantity - quant.reserved_quantity
                        if available_in_quant <= 0:
                            continue
                        
                        qty_to_reserve = min(remaining_qty, available_in_quant)
                        
                        # Create move line and reserve from this quant
                        move_line = self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': delivery_picking.id,
                            'product_id': product.id,
                            'product_uom_id': move.product_uom.id,
                            'location_id': car_location.id,
                            'location_dest_id': move.location_dest_id.id,
                            'quantity': qty_to_reserve,
                            'quantity_product_uom': qty_to_reserve,
                            'lot_id': quant.lot_id.id if quant.lot_id else False,
                            'package_id': quant.package_id.id if quant.package_id else False,
                            'owner_id': quant.owner_id.id if quant.owner_id else False,
                        })
                        
                        # Update quant to reserve the quantity
                        quant.write({
                            'reserved_quantity': quant.reserved_quantity + qty_to_reserve
                        })
                        
                        remaining_qty -= qty_to_reserve
                        
                        _logger.info("Reserved %.2f units from quant %s for move line %s", 
                                qty_to_reserve, quant.id, move_line.id)
                    
                    if remaining_qty > 0:
                        raise UserError(_(
                            "Could not reserve enough stock for %s. Missing: %.2f"
                        ) % (product.name, remaining_qty))
                
                # Update picking state to assigned
                delivery_picking.write({'state': 'assigned'})
                _logger.info("Force-assigned stock for picking %s", delivery_picking.name)
            
            # Step 6: Update customer line with delivery reference
            customer_line.write({'delivery_id': delivery_picking.id})
            
            # Step 7: Verify final state
            if delivery_picking.state == 'assigned':
                _logger.info("Successfully updated picking %s - ready for delivery", delivery_picking.name)
            else:
                _logger.warning("Picking %s state is %s - may need manual review", 
                            delivery_picking.name, delivery_picking.state)
            
        except Exception as e:
            _logger.error("Failed to update picking %s: %s", delivery_picking.name, str(e))
            raise UserError(_("Failed to update delivery picking %s: %s") % (delivery_picking.name, str(e)))
    # def _update_delivery_picking_sql(self, customer_line, request):
    #     """Update delivery picking using direct SQL queries"""
        
    #     # Find the picking to update
    #     self.env.cr.execute("""
    #         SELECT sp.id, sp.name 
    #         FROM stock_picking sp
    #         INNER JOIN sale_order so ON sp.origin = so.name OR sp.sale_id = so.id
    #         WHERE so.id = %s 
    #         AND sp.state = 'assigned' 
    #         AND sp.picking_type_id IN (
    #             SELECT id FROM stock_picking_type WHERE code = 'outgoing'
    #         )
    #         LIMIT 1
    #     """, (customer_line.sale_order_id.id,))
        
    #     picking_result = self.env.cr.fetchone()
    #     if not picking_result:
    #         _logger.warning("No ready outgoing delivery found for sale order %s", customer_line.sale_order_id.name)
    #         return
            
    #     picking_id, picking_name = picking_result
    #     _logger.info("Updating picking %s (ID: %s) with SQL", picking_name, picking_id)
        
    #     # Find the correct picking type
    #     self.env.cr.execute("""
    #         SELECT id FROM stock_picking_type 
    #         WHERE code = 'outgoing' 
    #         AND warehouse_id = %s 
    #         LIMIT 1
    #     """, (request.car_id.location_id.warehouse_id.id,))
        
    #     picking_type_result = self.env.cr.fetchone()
    #     if not picking_type_result:
    #         _logger.error("No outgoing picking type found for warehouse %s", 
    #                      request.car_id.location_id.warehouse_id.name)
    #         return
            
    #     picking_type_id = picking_type_result[0]
        
    #     try:
    #         # Update stock_picking table directly
    #         self.env.cr.execute("""
    #             UPDATE stock_picking 
    #             SET 
    #                 loading_request_id = %s,
    #                 loading_driver_id = %s,
    #                 car_id = %s,
    #                 picking_type_id = %s,
    #                 location_id = %s,
    #                 write_date = NOW(),
    #                 write_uid = %s
    #             WHERE id = %s
    #         """, (
    #             request.id,
    #             self.loading_driver_id.id,
    #             self.car_id.id,
    #             picking_type_id,
    #             request.car_id.location_id.id,
    #             self.env.user.id,
    #             picking_id
    #         ))
            
    #         # Update stock_move table for all moves in this picking
    #         self.env.cr.execute("""
    #             UPDATE stock_move 
    #             SET 
    #                 location_id = %s,
    #                 write_date = NOW(),
    #                 write_uid = %s
    #             WHERE picking_id = %s
    #         """, (
    #             request.car_id.location_id.id,
    #             self.env.user.id,
    #             picking_id
    #         ))
            
    #         # Update stock_move_line table if there are any move lines
    #         self.env.cr.execute("""
    #             UPDATE stock_move_line 
    #             SET 
    #                 location_id = %s,
    #                 write_date = NOW(),
    #                 write_uid = %s
    #             WHERE picking_id = %s
    #         """, (
    #             request.car_id.location_id.id,
    #             self.env.user.id,
    #             picking_id
    #         ))
            
    #         # Update the customer line with the delivery reference
    #         self.env.cr.execute("""
    #             UPDATE ice_loading_customer_line 
    #             SET 
    #                 delivery_id = %s,
    #                 write_date = NOW(),
    #                 write_uid = %s
    #             WHERE id = %s
    #         """, (
    #             picking_id,
    #             self.env.user.id,
    #             customer_line.id
    #         ))
            
    #         # Commit the transaction
    #         self.env.cr.commit()
            
    #         _logger.info("Successfully updated picking %s and related moves via SQL", picking_name)
            
    #         # Invalidate cache for affected models to ensure ORM sees the changes
    #         self.env.invalidate_all()
            
    #     except Exception as e:
    #         # Rollback in case of error
    #         self.env.cr.rollback()
    #         _logger.error("Failed to update picking %s via SQL: %s", picking_name, str(e))
    #         raise UserError(_("Failed to update delivery picking %s: %s") % (picking_name, str(e)))