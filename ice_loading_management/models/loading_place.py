from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class LoadingPlace(models.Model):
    _name = 'ice.loading.place'
    _description = 'Ice Loading Place'
    _order = 'loading_priority'
    
    # name = fields.Char(string='Loading Place Name', required=True)
    name = fields.Selection(
        [("alahsa", "Alahsa"),
         ("dammam", "Dammam"),
         ("nairyah", "Nairyah"),
         ("riyadh", "Riyadh")],
         required=True,
         string='Loading Place City',
         help="Select the city where the loading place is located."
    )
    loading_priority = fields.Integer(string='Loading Priority', default=1, 
                                    help="Lower numbers = Higher priority")
    loading_location_id = fields.Many2one('stock.location', string='Loading Location', 
                                        required=True, domain="[('usage', '=', 'internal')]")
    
    @api.constrains('loading_priority')
    def _check_loading_priority(self):
        for record in self:
            if record.loading_priority < 1:
                raise ValidationError(_('Loading priority must be greater than 0'))