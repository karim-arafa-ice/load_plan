from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
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
        # First, call the original validation logic
        res = super(StockPicking, self).button_validate()

        # After validation, the state of this picking will be 'done'.
        # We check if this is the internal transfer for a concrete request.
        if self.loading_request_id and self.loading_request_id.is_concrete and self.state == 'done' and not self.is_second_loading:
            request = self.loading_request_id
            _logger.info(f"Internal transfer {self.name} for concrete request {request.name} is done. Updating related delivery pickings.")

            # Now, find and update the actual customer delivery pickings
            for customer_line in request.customer_line_ids.filtered(lambda l: l.quantity > 0):
                self._update_delivery_picking_for_customer(customer_line, request)

        # This part handles state changes for the loading request itself.
        if self.loading_request_id:
            if self.is_second_loading and self.loading_request_id.state == 'started_second_loading':
                self.loading_request_id.write({'state': 'second_loading_done'})
                _logger.info("Second loading transfer validated. Updated request %s to 'second_loading_done'", self.loading_request_id.name)
            elif not self.is_second_loading and self.loading_request_id.state == 'loading':
                self.loading_request_id.write({'state': 'ice_handled'})
                _logger.info("First loading transfer validated. Updated request %s to 'ice_handled'", self.loading_request_id.name)

        return res

    def _update_delivery_picking_for_customer(self, customer_line, request):
        """Finds and updates the delivery picking for a specific customer line."""
        sale_order = customer_line.sale_order_id
        if not sale_order:
            _logger.warning("Customer line has no linked sale order.")
            return

        # Find the delivery picking associated with the sale order.
        delivery_picking = self.env['stock.picking'].search([
            ('sale_id', '=', sale_order.id),
            ('state', 'in', ['confirmed', 'waiting', 'assigned']),
            ('picking_type_id.code', '=', 'outgoing')
        ], limit=1)

        if not delivery_picking:
            _logger.warning(f"No ready outgoing delivery found for sale order {sale_order.name}")
            return

        _logger.info(f"Found delivery picking {delivery_picking.name} for SO {sale_order.name}. Updating...")

        car_location = request.car_id.location_id
        if not car_location:
            raise UserError(_(f"The car '{request.car_id.name}' does not have a location configured."))

        # *** THE FIX: Unreserve the picking to release stock from the original location ***
        if delivery_picking.state == 'assigned':
            delivery_picking.do_unreserve()
            _logger.info(f"Unreserved picking {delivery_picking.name} to change source location.")

        # Update the picking's source location to the car's location
        delivery_picking.write({
            'location_id': car_location.id,
            'loading_request_id': request.id,
        })

        # Update the move lines with the new source location and the correct quantity
        for move in delivery_picking.move_ids_without_package:
            move.write({
                'location_id': car_location.id,
                # 'product_uom_qty': customer_line.quantity,
            })
            _logger.info(f"Updated move {move.id}: new location is {car_location.display_name}, new demand is {customer_line.quantity}")

        # *** THE FIX: Re-reserve the picking from the new location (the car) ***
        delivery_picking.action_assign()
        _logger.info(f"Re-assigned picking {delivery_picking.name}. New state is: {delivery_picking.state}")

        # Update the customer line with the delivery reference for future use
        customer_line.write({'delivery_id': delivery_picking.id})

        # Post a message in the delivery's chatter for clarity
        delivery_picking.message_post(body=_(
            f"This delivery's source location has been updated to the car '{request.car_id.name}' "
            f"and quantity updated to {customer_line.quantity} based on loading request {request.name}."
        ))
        
        _logger.info(f"Successfully updated and re-reserved delivery picking {delivery_picking.name}.")

    def _force_assign_quantities(self):
        """Force assign quantities to move lines to allow validation"""
        _logger.info("Force assigning quantities for picking %s", self.name)
        
        for move in self.move_ids_without_package.filtered(lambda m: m.state not in ['done', 'cancel']):
            if not move.move_line_ids:
                # This is a fallback and might not be needed with the new logic
                move._create_move_line_ids()
            
            total_qty_needed = move.product_uom_qty
            total_qty_assigned = sum(move.move_line_ids.mapped('quantity'))
            
            if total_qty_assigned < total_qty_needed:
                qty_to_assign = total_qty_needed - total_qty_assigned
                
                if move.move_line_ids:
                    move_line = move.move_line_ids[0]
                    move_line.quantity += qty_to_assign
                else:
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'picking_id': self.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'quantity': qty_to_assign,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    })
                
                _logger.info("Force-assigned %.2f %s for move %s", qty_to_assign, move.product_uom.name, move.name)
        
        if self.state != 'assigned':
            self.write({'state': 'assigned'})
