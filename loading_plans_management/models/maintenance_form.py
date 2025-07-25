from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class MaintenanceForm(models.Model):
    _inherit = "maintenance.form"
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')


    def action_stop(self):
        """Override to set loading request state to 'car_checking' when stopping the maintenance form."""
        res = super(MaintenanceForm, self).action_stop()
        if self.loading_request_id:
            if self.loading_request_id.state == 'car_checking':
                self.loading_request_id.write({'state': 'ready_for_loading'})
                self.loading_request_id.car_id.loading_status = 'ready_for_loading'
                self.loading_request_id.car_checking_end_date = fields.Datetime.now()
                self.loading_request_id.message_post(body=_("Maintenance form completed. Loading request is now ready for loading."))
            else:
                self.vehicle_id.loading_status = 'available'

        else:
            self.vehicle_id.loading_status = 'available'
        return res
    
    def action_precheck(self):
        """
        Set the state to precheck.
        """
        res = super(MaintenanceForm, self).action_precheck()
        if self.loading_request_id:
            self.vehicle_id.loading_status = 'not_available'
        return res
    
    def action_received(self):

        res = super(MaintenanceForm, self).action_received()
        if self.loading_request_id:
            
            if self.loading_request_id.state == 'car_checking':
                self.loading_request_id.write({'state': 'ready_for_loading'})
                self.loading_request_id.car_id.loading_status = 'ready_for_loading'
                self.loading_request_id.car_checking_end_date = fields.Datetime.now()
            else:
                self.vehicle_id.loading_status = 'available'

        return res
