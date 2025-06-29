from odoo import models, fields, api

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'
        
    loading_status = fields.Selection([
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('not_available', 'Not Available'),
        ('ready_for_loading', 'Ready for Loading'),
        ('plugged', 'Plugged'),
    ], string='Loading Status', default='available')

    # Product capacity fields - corrected names
    ice_4kg_capacity = fields.Float(string='Capacity for 4kg Ice (KG)', default=0.0)
    ice_25kg_capacity = fields.Float(string='Capacity for 25kg Ice (KG)', default=0.0)
    ice_cup_capacity = fields.Float(string='Capacity for Ice Cups (KG)', default=0.0)
    
    # Computed total capacity
    total_weight_capacity = fields.Float(
        string='Total Weight Capacity (kg)',
        
    )

    # @api.depends('ice_4kg_capacity', 'ice_25kg_capacity', 'ice_cup_capacity')
    # def _compute_total_weight_capacity(self):
    #     for vehicle in self:
    #         vehicle.total_weight_capacity = (
    #             vehicle.ice_4kg_capacity + 
    #             vehicle.ice_25kg_capacity + 
    #             vehicle.ice_cup_capacity
    #         )