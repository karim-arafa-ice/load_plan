from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Product type for ice loading management
    ice_product_type = fields.Selection([
        ('4kg', '4kg Ice'),
        ('25kg', '25kg Ice'), 
        ('cup', 'Ice Cup')
    ], string='Ice Product Type', help="Type of ice product for loading capacity management")

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    # The ice_product_type field is automatically inherited from product.template
    # No need to redefine it here