from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = 'res.partner'
    name_arabic = fields.Char(string="Partner Arabic Name")
    street_arabic = fields.Char("Street in Arabic")
    street2_arabic = fields.Char("Street2 in Arabic")
    city_arabic = fields.Char("City in Arabic")
    state_arabic = fields.Char(string="State Arabic Name")
    zip_arabic = fields.Char("ZIP in Arabic")
    country_arabic = fields.Char(string="Country Name Arabic")
    project_name = fields.Char('Project Name')


    display_address_arabic = fields.Char(
        string="Arabic Display Address", 
        compute="_compute_display_address_arabic", 
        store=True
    )

    @api.depends('street_arabic', 'street2_arabic', 'city_arabic', 'state_arabic', 'zip_arabic', 'country_arabic')
    def _compute_display_address_arabic(self):
        for rec in self:
            address_parts = [
                rec.street_arabic,
                rec.street2_arabic,
                rec.city_arabic,
                rec.state_arabic,
                rec.zip_arabic,
                rec.country_arabic,
            ]
            # Filter out None or empty strings, then join with comma
            rec.display_address_arabic = ', '.join(filter(None, address_parts))

