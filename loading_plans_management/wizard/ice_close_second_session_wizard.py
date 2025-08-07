from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CloseSessionWizard(models.TransientModel):
    _name = 'ice.close.second.session.wizard'
    _description = 'Close Session Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    is_concrete = fields.Boolean(string="Is Concrete",related='loading_request_id.is_concrete',store=True)
    customer_line_ids = fields.One2many(
        'ice.close.second.session.customer.line', 'wizard_id', string='Second Loading Customers'
    )
    current_product_line_ids = fields.One2many('ice.close.second.session.current.product.line','wizard_id',string="Current Products Quantity")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_loading_request_id') and 'current_product_line_ids' in fields_list:
            loading_request = self.env['ice.loading.request'].browse(self.env.context.get('default_loading_request_id'))
            
            search_location = loading_request.car_id.location_id
            
            product_map = {}
            lines = []
            
            # Aggregate quantities from first loading
            for line in loading_request.second_product_line_ids:
                if line.product_id.id not in product_map:
                    product_map[line.product_id.id] = {'loaded': 0.0, 'product': line.product_id}
                product_map[line.product_id.id]['loaded'] += line.quantity
            # Create wizard lines
            for product_id, data in product_map.items():
                product = data['product']
                
                # Get current quantity in Pcs from stock.quant
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', product_id),
                    ('location_id', '=', search_location.id)
                ], limit=1)
                current_qty_pcs = stock_quant.quantity if stock_quant else 0.0
                
                # Convert current quantity to user-facing unit (Bags/Baskets) for display
                current_qty_display = current_qty_pcs
                if product.ice_product_type == '4kg' and product.pcs_per_bag > 0:
                    current_qty_display = current_qty_pcs / product.pcs_per_bag
                elif product.ice_product_type == 'cup' and product.pcs_per_basket > 0:
                    current_qty_display = current_qty_pcs / product.pcs_per_basket

                line_vals = {
                    'product_id': product_id,
                    'loaded_quantity': data['loaded'],
                    'current_quantity': current_qty_display,
                    'return_quantity': 0.0,
                    'scrap_quantity': 0.0,
                }
                lines.append((0, 0, line_vals))
            
            res['current_product_line_ids'] = lines
        
        return res
    def action_validate(self):
        self.ensure_one()
        request = self.loading_request_id
        request.write({'state': 'session_closed',
                    'second_loading_end_date': fields.Datetime.now()
                    })
        if self.loading_request_id.is_concrete:
            product_25kg = self.env.company.product_25kg_id.product_variant_id
            warehouse = request.env['stock.warehouse'].search([
                        ('lot_stock_id', '=', self.loading_request_id.car_id.location_id.id)
                    ], limit=1)
            for line in self.customer_line_ids:
                if line.quantity < 0:
                    raise UserError(_("Please enter a valid quantity for the Customer: %s") % line.customer_id.name)
                if line.quantity > 0:
                    price = False
                    pricelist = line.customer_id.property_product_pricelist
                    if pricelist:
                        pricelist_item = pricelist.item_ids.filtered(
                            lambda r: r.product_id == product_25kg or r.product_tmpl_id == product_25kg.product_tmpl_id)
                        if pricelist_item:
                            price = pricelist._get_product_price(product_25kg, line.quantity, line.customer_id)

                    if not price:
                        price = product_25kg.lst_price
                    
                    concrete_order_vals = {
                    'partner_id': line.customer_id.id,
                    'order_line': [(0, 0, {
                        'product_id': product_25kg.id,
                        'product_uom_qty': line.quantity,
                        'name': product_25kg.display_name,  # Name of the product in the order line
                        'price_unit': price
                    })],
                    'is_concrete': True,
                    'loading_request_id': self.loading_request_id.id,
                    'car_id': self.loading_request_id.car_id.id,
                    'user_id': self.loading_request_id.team_leader_id.id,  # Set the salesperson as the request maker
                    'pricelist_id': pricelist.id if pricelist else None,
                    'warehouse_id': warehouse.id if warehouse else None,
                }

                concrete_order = request.env['sale.order'].create(concrete_order_vals)
                for picking in concrete_order.picking_ids:
                    if picking.state not in ('done', 'cancel'):
                        picking.write({'location_id': self.loading_request_id.car_id.location_id.id})
                        picking.write({'user_id': user.id})
                        for move_line in picking.move_line_ids:
                            move_line.write({'location_id': self.loading_request_id.car_id.location_id.id})
                    if picking.state not in ('done', 'cancel'):
                        picking.action_confirm()
                        picking.action_assign()
                        for move_line in picking.move_line_ids:
                            move_line.qty_done = move_line.quantity_product_uom
                        picking.button_validate()
                self.env['second.ice.loading.customer.line'].create({
                    'loading_request_id': request.id,
                    'customer_id': line.customer_id.id,
                    'quantity': line.quantity,
                    'sale_order_id': concrete_order.id,
                    # 'delivery_id': concrete_order.picking_ids[0].id
                })
        
            
        
        
        return {'type': 'ir.actions.act_window_close'}

class CloseSessionCustomerLine(models.TransientModel):
    _name = 'ice.close.second.session.customer.line'
    _description = 'Close Session Customer Line'

    wizard_id = fields.Many2one('ice.close.second.session.wizard', string='Wizard')
    customer_id = fields.Many2one('res.partner', string='Product', required=True)
    quantity = fields.Float(string='Second Loading Quantity', required=True, default=0.0)

class CloseSessionCurrentProductLine(models.TransientModel):
    _name = 'ice.close.second.session.current.product.line'
    wizard_id = fields.Many2one('ice.close.second.session.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    loaded_quantity = fields.Float(string='First Loading Quantity', default=0.0)
    current_quantity = fields.Float(string='Current Quantity', required=True, default=0.0)
    return_quantity = fields.Float(string='Returned Quantity', required=True, default=0.0)
    scrap_quantity = fields.Float(string='Scrap Quantity', required=True, default=0.0)
