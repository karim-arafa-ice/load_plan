# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FormUploadWizard(models.TransientModel):
    _name = 'ice.form.upload.wizard'
    _description = 'Form Upload Wizard'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    form_type = fields.Selection([
        ('loading_form', 'Loading Form'),
    ], string='Form Type', required=True)
    # form_type = fields.Selection([
    #     ('freezer_release', 'Freezer Release Form'),
    #     ('loading_form', 'Loading Form'),
    # ], string='Form Type', required=True)
    
    uploaded_file = fields.Binary(string='Signed Form', required=True)
    uploaded_filename = fields.Char(string='Filename')
    comments = fields.Text(string='Comments')
    
    # Display current status
    current_state = fields.Selection(related='loading_request_id.state', string='Current Status', readonly=True)
    salesman_name = fields.Char(related='loading_request_id.salesman_id.name', string='Salesman', readonly=True)
    car_name = fields.Char(related='loading_request_id.car_id.license_plate', string='Car', readonly=True)
    
    def action_upload_form(self):
        """Upload the form and update the loading request"""
        self.ensure_one()
        
        if not self.uploaded_file:
            raise UserError(_('Please select a file to upload.'))
        
        loading_request = self.loading_request_id
        
        # if self.form_type == 'freezer_release':
        #     loading_request.write({
        #         'freezer_release_form': self.uploaded_file,
        #         'freezer_release_form_filename': self.uploaded_filename,
        #         'state': 'freezer_handled'
        #     })
        #     success_message = _('Freezer release form uploaded successfully!')
            
        if self.form_type == 'loading_form':
            loading_request.write({
                'signed_loading_form': self.uploaded_file,
                'signed_loading_form_filename': self.uploaded_filename,
                'state': 'ice_handled'
            })
            success_message = _('Loading form uploaded successfully!')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Form Uploaded'),
                'message': success_message,
                'type': 'success',
                'sticky': False,
            }
        }