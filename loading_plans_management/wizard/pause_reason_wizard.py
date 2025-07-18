from odoo import models, fields, api, _

class PauseReasonWizard(models.TransientModel):
    _name = 'ice.pause.reason.wizard'
    _description = 'Pause Loading Reason Wizard'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    pause_reason = fields.Text(string='Reason for Pausing', required=True)

    def action_confirm_pause(self):
        self.ensure_one()
        self.loading_request_id.write({
            'state': 'paused',
            'pause_reason': self.pause_reason,
        })
        self.loading_request_id.message_post(
            body=_('Loading paused by %s.<br/>Reason: %s') % (self.env.user.name, self.pause_reason),
            subject=_('Loading Paused')
        )
        return {'type': 'ir.actions.act_window_close'}