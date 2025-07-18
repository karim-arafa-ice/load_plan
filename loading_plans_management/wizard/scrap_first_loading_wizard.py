from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ScrapProductsWizard(models.TransientModel):
    _name = 'ice.scrap.products.wizard'
    _description = 'Scrap Products Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    line_ids = fields.One2many('ice.scrap.products.line', 'wizard_id', string='Products')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loading_request = self.env['ice.loading.request'].browse(self.env.context.get('default_loading_request_id'))
        lines = []
        # Get the 3 products from the request
        for line in loading_request.product_line_ids:
            # Get current qty in salesman's location
            quant = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', loading_request.salesman_id.accessible_location_id.id)
            ], limit=1)
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'current_qty': quant.quantity if quant else 0.0,
                'scrap_qty': 0.0,
            }))
        res['line_ids'] = lines
        return res

    def action_validate(self):
        self.ensure_one()
        picking_moves = []
        request = self.loading_request_id
        for line in self.line_ids:
            if line.scrap_qty > 0:
                if line.scrap_qty > line.current_qty:
                    raise UserError(_('Scrap quantity for %s cannot be greater than current quantity (%s).') % (line.product_id.display_name, line.current_qty))
                # Create scrap order
                scrap = self.env['stock.scrap'].create({
                    'product_id': line.product_id.id,
                    'scrap_qty': line.scrap_qty,
                    'location_id': self.loading_request_id.salesman_id.accessible_location_id.id,
                    'origin': self.loading_request_id.name,
                })
                second_line = self.env['second.ice.loading.product.line'].search([
                    ('loading_request_id', '=', request.id),
                    ('product_id', '=', line.product_id.id)
                ], limit=1)
                if second_line:
                    second_line.scrap_quantity = line.scrap_qty
                    second_line.quantity = second_line.requested_quantity - line.scrap_qty
                    # Prepare move for remaining quantity
                    if second_line.quantity > 0:
                        picking_moves.append((0, 0, {
                            'name': second_line.product_id.display_name,
                            'product_id': second_line.product_id.id,
                            'product_uom_qty': second_line.quantity,
                            'product_uom': second_line.product_id.uom_id.id,
                            'location_id': request.loading_place_id.loading_location_id.id,
                            'location_dest_id': request.salesman_id.accessible_location_id.id,
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
                'location_dest_id': request.salesman_id.accessible_location_id.id,
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
            'first_loading_scrap_ids': [(4, scrap.id)],
            'state': 'ready_for_second_loading'
        })
        return {'type': 'ir.actions.act_window_close'}

class ScrapProductsLine(models.TransientModel):
    _name = 'ice.scrap.products.line'
    _description = 'Scrap Products Line'

    wizard_id = fields.Many2one('ice.scrap.products.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    current_qty = fields.Float(string='Current Quantity', readonly=True)
    scrap_qty = fields.Float(string='Scrap Quantity')

    @api.onchange('current_qty')
    def _onchange_current_qty(self):
        for line in self:
            if line.scrap_qty > line.current_qty:
                line.scrap_qty = line.current_qty
                raise UserError(_('Scrap quantity cannot be greater than current quantity (%s).') % line.current_qty)