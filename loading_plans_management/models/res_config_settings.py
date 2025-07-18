from odoo import models, fields, api


class IceSalesConfig(models.Model):
    _inherit = 'res.company'

    product_4kg_id = fields.Many2one(
        'product.template', 
        string='Default 4kg Ice Product',
        help="Select the default product for 4kg ice blocks"
    )
    product_25kg_id = fields.Many2one(
        'product.template', 
        string='Default 25kg Ice Product',
        help="Select the default product for 25kg ice blocks"
    )
    product_cup_id = fields.Many2one(
        'product.template', 
        string='Default Ice Cup Product',
        help="Select the default product for ice cups"
    )
    
    ice_location_id = fields.Many2one(
        'stock.location',
        string='Default Ice Location',
        domain="[('usage', '=', 'internal')]",
        help="Default location for ice operations"
    )
    scrap_location_id = fields.Many2one('stock.location', string='Scrap Location',
                                          domain=[('scrap_location', '=', True)],
                                          help="Location where scrapped items are placed")
    

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    # Default products configuration with proper default_model
    default_product_4kg_id = fields.Many2one(
        related='company_id.product_4kg_id', 
        readonly=False,
        default_model='res.company'
    )
    default_product_25kg_id = fields.Many2one(
        related='company_id.product_25kg_id', 
        readonly=False,
        default_model='res.company'
    )
    default_product_cup_id = fields.Many2one(
        related='company_id.product_cup_id', 
        readonly=False,
        default_model='res.company'
    )
    
    default_ice_location_id = fields.Many2one(
        related='company_id.ice_location_id', 
        readonly=False,
        default_model='res.company'
    )
    default_scrap_location_id = fields.Many2one(
        related='company_id.scrap_location_id', 
        readonly=False,
        default_model='res.company'
    )