from odoo import models, fields, api, _

class SetFullLoadWizard(models.TransientModel):
    _name = 'ice.set.full.load.wizard'
    _description = 'Set Full Load for All Products'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    apply_to_4kg = fields.Boolean(string='Apply Full Load to 4kg Ice', default=True)
    apply_to_25kg = fields.Boolean(string='Apply Full Load to 25kg Ice', default=True)
    apply_to_cup = fields.Boolean(string='Apply Full Load to Ice Cups', default=True)
    
    def action_apply_full_load(self):
        """Apply full load to selected product types"""
        self.ensure_one()
        
        for line in self.loading_request_id.product_line_ids:
            if ((line.product_type == '4kg' and self.apply_to_4kg) or
                (line.product_type == '25kg' and self.apply_to_25kg) or
                (line.product_type == 'cup' and self.apply_to_cup)):
                
                line.is_full_load = True
                line._onchange_full_load()  # Trigger the onchange to set quantity
        
        return {'type': 'ir.actions.act_window_close'}