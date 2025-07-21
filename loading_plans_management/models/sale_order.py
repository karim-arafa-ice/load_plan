from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    _rec_names_search = ['name', 'partner_id.name', 'partner_id.ref']

    session_id = fields.Many2one('ice.driver.session', string='Driver Session', readonly=True, copy=False)
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False)
    car_id = fields.Many2one('fleet.vehicle', string='Car', readonly=True, copy=False)
    is_concrete = fields.Boolean(string="Concrete Order")

    
    # ... (rest of the fields)

    def write(self,vals):
        if "is_concrete" in vals:
            warehouse = self.env['stock.warehouse'].search([('lot_stock_id','=',self.env.company.ice_location_id.id)])
            vals['warehouse_id'] = warehouse.id
        res = super(SaleOrder, self).write(vals)
        return res


    @api.model
    def create(self, vals):
        if 'is_concrete' in vals:
            if vals['is_concrete'] == True:
                warehouse = self.env['stock.warehouse'].search([('lot_stock_id','=',self.env.company.ice_location_id.id)])
                vals['warehouse_id'] = warehouse.id
                if 'user_id' in vals:
                    team_leader = self.env['res.users'].search([('id', '=', vals['user_id'])], limit=1)
                    if team_leader:
                        active_loading_request = self.env['ice.loading.request'].search([
                            ('team_leader_id', '=', team_leader.id),
                            ('state', '=', 'delivering')
                        ], order='create_date desc', limit=1)
                        if active_loading_request:
                            vals.update({
                                'session_id': active_loading_request.session_id.id,
                                'loading_request_id': active_loading_request.id,
                                'car_id': active_loading_request.car_id.id,
                            })
            else:
                if 'user_id' in vals:
                    salesman = self.env['res.users'].search([('id', '=', vals['user_id'])], limit=1)
                    if salesman:
                        active_loading_request = self.env['ice.loading.request'].search([
                            ('salesman_id', '=', salesman.id),
                            ('state', '=', 'delivering')
                        ], order='create_date desc', limit=1)
                        if active_loading_request:
                            vals.update({
                                'session_id': active_loading_request.session_id.id,
                                'loading_request_id': active_loading_request.id,
                                'car_id': active_loading_request.car_id.id,
                            })
        
        elif 'user_id' in vals and 'is_concrete' not in vals:
            
            salesman = self.env['res.users'].search([('id', '=', vals['user_id'])], limit=1)
            if salesman:
                active_loading_request = self.env['ice.loading.request'].search([
                    ('salesman_id', '=', salesman.id),
                    ('state', '=', 'delivering')
                ], order='create_date desc', limit=1)
                if active_loading_request:
                    vals.update({
                        'session_id': active_loading_request.session_id.id,
                        'loading_request_id': active_loading_request.id,
                        'car_id': active_loading_request.car_id.id,
                    })
        return super(SaleOrder, self).create(vals)

    open_order = fields.Boolean(
        string='Open Order',
        compute='_compute_open_order',
        store=True,
        help='True if any order line has remaining quantity to be delivered'
    )
    
    @api.depends('order_line.qty_delivered', 'order_line.product_uom_qty')
    def _compute_open_order(self):
        for order in self:
            open_order = False
            for line in order.order_line:
                if line.qty_delivered != line.product_uom_qty:
                    open_order = True
                    break
            order.open_order = open_order

    
   