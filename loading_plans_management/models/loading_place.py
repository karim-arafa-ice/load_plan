from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class LoadingPlace(models.Model):
    _name = 'ice.loading.place'
    _description = 'Ice Loading Place'
    
    name = fields.Selection(
        [("alahsa", "Alahsa"),
         ("dammam", "Dammam"),
         ("nairyah", "Nairyah"),
         ("riyadh", "Riyadh")],
         required=True,
         string='Loading Place City',
         help="Select the city where the loading place is located."
    )
    loading_location_id = fields.Many2one('stock.location', string='Loading Location', 
                                        required=True, domain="[('usage', '=', 'internal')]")
    
    priority = fields.Integer(string='Priority', default=10, help="Lower number means higher priority.")

    
   