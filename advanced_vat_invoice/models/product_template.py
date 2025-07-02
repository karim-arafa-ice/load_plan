from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_name_in_report = fields.Char(
        string='Product Name in Report',
        help="This field is used to display the product name in reports. "
             "If not set, the default product name will be used."
    )