from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CloseSessionWizard(models.TransientModel):
    _name = 'ice.close.session.wizard'
    _description = 'Close Session Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    need_second_load = fields.Selection([
        ('no', 'No'),
        ('yes', 'Yes')
    ], string='Need Second Load?', required=True, default='no')

    product_line_ids = fields.One2many(
        'ice.close.session.product.line', 'wizard_id', string='Second Loading Products'
    )

    @api.onchange('need_second_load')
    def _onchange_need_second_load(self):
        if self.need_second_load == 'yes':
            # Populate lines with the 3 products from the request
            self.product_line_ids = self.loading_request_id._get_default_product_lines_values(concrete=False)
        else:
            self.product_line_ids = [(5, 0, 0)]

    def action_validate(self):
        self.ensure_one()
        request = self.loading_request_id
        if self.need_second_load == 'yes':
            for line in self.product_line_ids:
                if line.quantity <= 0:
                    raise UserError(_("Please enter a valid quantity for the product: %s") % line.product_id.name)
                # Create second loading product lines
                self.env['second.ice.loading.product.line'].create({
                    'loading_request_id': request.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'scrap_quantity': 0.0,  # Assuming no scrap for now
                    'requested_quantity': line.quantity,  # Assuming requested quantity is same as entered
                    'current_quantity': line.quantity,  # Assuming current quantity is same as entered
                })
            # Create second internal transfer (similar to _create_internal_transfer)
            # move_lines = []
            # source_location_id = request.loading_place_id.loading_location_id.id
            # for line in self.product_line_ids:
            #     if line.quantity > 0:
            #         move_lines.append((0, 0, {
            #             'name': line.product_id.name,
            #             'product_id': line.product_id.id,
            #             'product_uom_qty': line.quantity,
            #             'location_id': source_location_id,
            #             'location_dest_id': request.salesman_id.accessible_location_id.id,
            #         }))
            # if not move_lines:
            #     raise UserError(_("Please enter quantities for the second loading."))

            # picking_type = self.env['stock.picking.type'].search([
            #     ('code', '=', 'internal'),
            #     ('warehouse_id.lot_stock_id', '=', source_location_id)
            # ], limit=1)
            # if not picking_type:
            #     raise UserError(_("No internal transfer operation type found for the source location."))

            # picking = self.env['stock.picking'].create({
            #     'picking_type_id': picking_type.id,
            #     'location_id': source_location_id,
            #     'location_dest_id': request.salesman_id.accessible_location_id.id,
            #     'move_ids_without_package': move_lines,
            #     'origin': request.name + ' (Second Load)',
            #     'transfer_vehicle': request.car_id.id,
            #     'loading_driver_id': request.salesman_id.id,
            #     'car_id': request.car_id.id,
            #     'loading_request_id': request.id,
            # })
            # picking.action_confirm()
            # picking.action_assign()
            # request.second_internal_transfer_id = picking.id
            request.write({'state': 'empty_scrap', 'has_second_loading': True})
        else:
            request.write({'state': 'session_closed'})
        return {'type': 'ir.actions.act_window_close'}

class CloseSessionProductLine(models.TransientModel):
    _name = 'ice.close.session.product.line'
    _description = 'Close Session Product Line'

    wizard_id = fields.Many2one('ice.close.session.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Second Loading Quantity', required=True, default=0.0)