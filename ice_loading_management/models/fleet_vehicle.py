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
    ice_4kg_capacity = fields.Float(string='Capacity for 4kg Ice (PCs)', default=0.0)
    ice_25kg_capacity = fields.Float(string='Capacity for 25kg Ice (PCs)', default=0.0)
    ice_cup_capacity = fields.Float(string='Capacity for Ice Cups (PCs)', default=0.0)
    
    # Computed total capacity
    total_weight_capacity = fields.Float(
        string='Total Weight Capacity (kg)',
        
    )
    is_concrete = fields.Boolean(string='Is Concrete')
    location_id = fields.Many2one('stock.location', string='Location', domain="[('usage', '=', 'internal')]")

    # @api.model
    # def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
    #     """
    #     Extend the search to include the vehicle's model category name.
    #     """
    #     args = args or []
    #     domain = []
    #     if name:
    #         # Search on license plate, name, AND category name
    #         domain = ['|', '|', ('license_plate', operator, name), ('name', operator, name), ('model_id.category_id.name', operator, name)]
        
    #     return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
        

    # @api.depends('ice_4kg_capacity', 'ice_25kg_capacity', 'ice_cup_capacity')
    # def _compute_total_weight_capacity(self):
    #     for vehicle in self:
    #         vehicle.total_weight_capacity = (
    #             vehicle.ice_4kg_capacity + 
    #             vehicle.ice_25kg_capacity + 
    #             vehicle.ice_cup_capacity
    #         )