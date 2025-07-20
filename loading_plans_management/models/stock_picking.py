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
            allowed_states = ['loading', 'ice_handled', 'session_closed']
            if self.loading_request_id.state not in allowed_states:
                raise UserError(_(
                    "You cannot validate the transfer. The loading request '%s' is in state '%s'. "
                    "Allowed states are: %s"
                ) % (self.loading_request_id.name, self.loading_request_id.state, ', '.join(allowed_states)))
        
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
            if self.loading_request_id.state == 'loading':
                # Update loading request state to 'ice_handled' after validation
                request = self.loading_request_id
                request.write({'state': 'ice_handled'})

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
        """Update delivery picking using direct SQL queries"""
        
        # Find the picking to update
        self.env.cr.execute("""
            SELECT sp.id, sp.name 
            FROM stock_picking sp
            INNER JOIN sale_order so ON sp.origin = so.name OR sp.sale_id = so.id
            WHERE so.id = %s 
            AND sp.state = 'assigned' 
            AND sp.picking_type_id IN (
                SELECT id FROM stock_picking_type WHERE code = 'outgoing'
            )
            LIMIT 1
        """, (customer_line.sale_order_id.id,))
        
        picking_result = self.env.cr.fetchone()
        if not picking_result:
            _logger.warning("No ready outgoing delivery found for sale order %s", customer_line.sale_order_id.name)
            return
            
        picking_id, picking_name = picking_result
        _logger.info("Updating picking %s (ID: %s) with SQL", picking_name, picking_id)
        
        # Find the correct picking type
        self.env.cr.execute("""
            SELECT id FROM stock_picking_type 
            WHERE code = 'outgoing' 
            AND warehouse_id = %s 
            LIMIT 1
        """, (request.car_id.location_id.warehouse_id.id,))
        
        picking_type_result = self.env.cr.fetchone()
        if not picking_type_result:
            _logger.error("No outgoing picking type found for warehouse %s", 
                         request.car_id.location_id.warehouse_id.name)
            return
            
        picking_type_id = picking_type_result[0]
        
        try:
            # Update stock_picking table directly
            self.env.cr.execute("""
                UPDATE stock_picking 
                SET 
                    loading_request_id = %s,
                    loading_driver_id = %s,
                    car_id = %s,
                    picking_type_id = %s,
                    location_id = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE id = %s
            """, (
                request.id,
                self.loading_driver_id.id,
                self.car_id.id,
                picking_type_id,
                request.car_id.location_id.id,
                self.env.user.id,
                picking_id
            ))
            
            # Update stock_move table for all moves in this picking
            self.env.cr.execute("""
                UPDATE stock_move 
                SET 
                    location_id = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE picking_id = %s
            """, (
                request.car_id.location_id.id,
                self.env.user.id,
                picking_id
            ))
            
            # Update stock_move_line table if there are any move lines
            self.env.cr.execute("""
                UPDATE stock_move_line 
                SET 
                    location_id = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE picking_id = %s
            """, (
                request.car_id.location_id.id,
                self.env.user.id,
                picking_id
            ))
            
            # Update the customer line with the delivery reference
            self.env.cr.execute("""
                UPDATE ice_loading_customer_line 
                SET 
                    delivery_id = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE id = %s
            """, (
                picking_id,
                self.env.user.id,
                customer_line.id
            ))
            
            # Commit the transaction
            self.env.cr.commit()
            
            _logger.info("Successfully updated picking %s and related moves via SQL", picking_name)
            
            # Invalidate cache for affected models to ensure ORM sees the changes
            self.env.invalidate_all()
            
        except Exception as e:
            # Rollback in case of error
            self.env.cr.rollback()
            _logger.error("Failed to update picking %s via SQL: %s", picking_name, str(e))
            raise UserError(_("Failed to update delivery picking %s: %s") % (picking_name, str(e)))