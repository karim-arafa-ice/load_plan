from odoo import models, fields, api

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'
    _rec_names_search = ['name', 'driver_id.name','category_id.name']
        
    loading_status = fields.Selection([
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('not_available', 'Not Available'),
        ('ready_for_loading', 'Ready for Loading'),
        ('plugged', 'Plugged'),
    ], string='Loading Status', default='available')

    # Product capacity fields - corrected names
    ice_4kg_capacity = fields.Float(string='Capacity for 4kg Ice (Bags)', default=0.0)
    ice_25kg_capacity = fields.Float(string='Capacity for 25kg Ice (PCs)', default=0.0)
    ice_cup_capacity = fields.Float(string='Capacity for Ice Cups (Baskets)', default=0.0)
    
    # Computed total capacity
    total_weight_capacity = fields.Float(
        string='Total Weight Capacity (kg)',
    )
    is_concrete = fields.Boolean(string='Is Concrete')
    location_id = fields.Many2one('stock.location', string='Location', domain="[('usage', '=', 'internal')]")