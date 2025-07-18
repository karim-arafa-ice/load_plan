from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class IceDriverSession(models.Model):
    _name = 'ice.driver.session'
    _description = 'Driver Session Management'

    driver_id = fields.Many2one('res.users', string='Driver', required=True)
    car_id = fields.Many2one('fleet.vehicle', string='Car', required=True)
    session_start = fields.Datetime(string='Session Start', default=fields.Datetime.now)
    session_end = fields.Datetime(string='Session End')
    is_active = fields.Boolean(string='Active Session', default=True)
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')
    driver_comment = fields.Text(string='Driver Comment')

    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], string='Status', default='open')

    def close_session(self):
        """
        Closes the session. The creation of the return request is now
        handled manually from the Return Request screen.
        """
        for session in self:
            session.write({
                'session_end': fields.Datetime.now(),
                'is_active': False,
                'state': 'closed',
            })