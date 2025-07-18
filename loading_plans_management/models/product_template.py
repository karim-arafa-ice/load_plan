from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Product type for ice loading management
    ice_product_type = fields.Selection([
        ('4kg', '4kg Ice'),
        ('25kg', '25kg Ice'), 
        ('cup', 'Ice Cup')
    ], string='Ice Product Type', help="Type of ice product for loading capacity management")

    pcs_per_bag = fields.Integer(
        string='Pieces per Bag', 
        default=8, 
        help="How many individual pieces are in one bag (for 4kg ice)."
    )
    pcs_for_concrete = fields.Integer(
        string='Pieces For Concrete', 
        default=1, 
        help="How many individual pieces are in one bag (for concrete)."
    )
    pcs_per_basket = fields.Integer(
        string='Pieces per Basket', 
        default=12, 
        help="How many individual pieces are in one basket (for ice cups)."
    )