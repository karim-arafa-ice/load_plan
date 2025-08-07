from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    _rec_names_search = ['name', 'partner_id.name', 'partner_id.ref']

    session_id = fields.Many2one('ice.driver.session', string='Driver Session', readonly=True, copy=False)
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False)
    car_id = fields.Many2one('fleet.vehicle', string='Car', readonly=True, copy=False)
    is_concrete = fields.Boolean(string="Concrete Order")

    open_order = fields.Boolean(
        string='Open Order',
        help='True if any order line has remaining quantity to be delivered'
    )

    
   