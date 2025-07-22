from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CarChangeWizard(models.TransientModel):
    _name = 'ice.car.change.wizard'
    _description = 'Car Change Wizard'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    current_car_id = fields.Many2one('fleet.vehicle', string='Current Car', readonly=True)
    new_car_id = fields.Many2one('fleet.vehicle', string='New Car', required=True,
                                domain="[('loading_status', '=', 'available'), ('id', '!=', current_car_id)]")
    reason = fields.Text(string='Reason for Change', required=True)

    # Status validation
    current_state = fields.Selection(related='loading_request_id.state', string='Current Status', readonly=True)
    status_warning = fields.Text(compute='_compute_status_warning', string='Status Warning')
    
    # Show current car details
    current_car_name = fields.Char(related='current_car_id.category_id.name', string='Current Car Name')
    current_car_capacity = fields.Float(related='current_car_id.total_weight_capacity', string='Current Car Capacity (kg)')
    
    # Show new car details
    new_car_name = fields.Char(related='new_car_id.category_id.name', string='New Car Name')
    new_car_capacity = fields.Float(related='new_car_id.total_weight_capacity', string='New Car Capacity (kg)')
    
    # Capacity comparison
    capacity_difference = fields.Float(compute='_compute_capacity_difference', 
                                     string='Capacity Difference (kg)')
    capacity_warning = fields.Text(compute='_compute_capacity_warning', 
                                 string='Capacity Warning')
    
    # Notification options
    notify_salesman = fields.Boolean(string='Notify Salesman', default=True)
    notify_sales_supervisor = fields.Boolean(string='Notify Sales Supervisor', default=True)
    notify_team_leader = fields.Boolean(string='Notify Team Leader', default=True)
    additional_message = fields.Text(string='Additional Message')

    
    
    @api.depends('current_car_capacity', 'new_car_capacity')
    def _compute_capacity_difference(self):
        for wizard in self:
            wizard.capacity_difference = wizard.new_car_capacity - wizard.current_car_capacity
    
    @api.depends('capacity_difference', 'loading_request_id.total_weight')
    def _compute_capacity_warning(self):
        for wizard in self:
            warning = ""
            if wizard.new_car_capacity < wizard.loading_request_id.total_weight:
                warning = _("⚠️ WARNING: New car capacity (%.2f kg) is less than current load weight (%.2f kg)!") % (
                    wizard.new_car_capacity, wizard.loading_request_id.total_weight
                )
            elif wizard.capacity_difference < 0:
                warning = _("⚠️ NOTE: New car has %.2f kg less capacity than current car.") % abs(wizard.capacity_difference)
            elif wizard.capacity_difference > 0:
                warning = _("✅ New car has %.2f kg more capacity than current car.") % wizard.capacity_difference
            
            wizard.capacity_warning = warning
    
    @api.onchange('new_car_id')
    def _onchange_new_car_id(self):
        """Validate new car capacity against current load"""
        if self.new_car_id and self.loading_request_id:
            # Check if new car can handle the current load
            total_weight = self.loading_request_id.total_weight
            if total_weight > self.new_car_id.total_weight_capacity:
                return {
                    'warning': {
                        'title': _('Capacity Warning'),
                        'message': _('The new car capacity (%.2f kg) is insufficient for the current load (%.2f kg). You may need to reduce the quantities.') % (
                            self.new_car_id.total_weight_capacity, total_weight
                        )
                    }
                }
    
    def action_change_car(self):
        """Execute car change with notifications"""
        self.ensure_one()
        # Check status restrictions

        
        if not self.new_car_id:
            raise UserError(_('Please select a new car.'))
        
        if self.new_car_id == self.current_car_id:
            raise UserError(_('New car must be different from current car.'))
        
        # Check if user has permission (fleet supervisor)
        if not self.env.user.has_group('maintenance_app.maintenance_fleet_supervisor_group'):
            raise UserError(_('Only Fleet Supervisors can change cars.'))
        
        # Validate new car capacity
        if self.loading_request_id.total_weight > self.new_car_id.total_weight_capacity:
            raise UserError(_(
                'Cannot change car: New car capacity (%.2f kg) is insufficient for current load (%.2f kg). Please reduce quantities first.'
            ) % (self.new_car_capacity, self.loading_request_id.total_weight))
        
        # Store previous car info
        previous_car = self.current_car_id
        
        # Update loading request
        self.loading_request_id.write({
            'previous_car_id': previous_car.id,
            'car_id': self.new_car_id.id,
            'car_change_reason': self.reason,
            'car_changed_by_id': self.env.user.id,
            'car_change_date': fields.Datetime.now(),
            'state': 'ready_for_loading',  # Update state to indicate car change
        })
        
        # Update car statuses
        if previous_car.loading_status == 'in_use':
            previous_car.loading_status = 'not_available'
        self.new_car_id.loading_status = 'in_use'
        
        
        # Send notifications
        self._send_car_change_notifications()
        
        # Log the change
        self.loading_request_id.message_post(
            body=_('Car changed from %s to %s by %s.<br/>Reason: %s') % (
                previous_car.license_plate or previous_car.name,
                self.new_car_id.license_plate or self.new_car_id.name,
                self.env.user.name,
                self.reason
            ),
            subject=_('Car Changed by Fleet Supervisor')
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def _send_car_change_notifications(self):
        """Send notifications to relevant people"""
        request = self.loading_request_id
        subject = _('Car Changed for Loading Request %s') % request.name
        
        # Base message
        message = _("""
        <p>The car for loading request <strong>%s</strong> has been changed:</p>
        <ul>
            <li><strong>Previous Car:</strong> %s</li>
            <li><strong>New Car:</strong> %s</li>
            <li><strong>Reason:</strong> %s</li>
            <li><strong>Changed by:</strong> %s</li>
            <li><strong>Dispatch Time:</strong> %s</li>
        </ul>
        """) % (
            request.name,
            self.current_car_id.license_plate or self.current_car_id.name,
            self.new_car_id.license_plate or self.new_car_id.name,
            self.reason,
            self.env.user.name,
            request.dispatch_time.strftime('%Y-%m-%d %H:%M') if request.dispatch_time else 'Not set'
        )
        
        if self.additional_message:
            message += _('<p><strong>Additional Message:</strong> %s</p>') % self.additional_message
        
        # Collect recipients
        recipients = []
        
        # Notify salesman
        if self.notify_salesman and request.salesman_id:
            recipients.append(request.salesman_id.partner_id.id)
        
        # Notify team leader
        if self.notify_team_leader and request.team_leader_id:
            recipients.append(request.team_leader_id.partner_id.id)
        
        # Notify sales supervisor
        if self.notify_sales_supervisor:
            try:
                sales_supervisor_group = self.env.ref('sales_team.group_sale_salesman_all_leads')
                for user in sales_supervisor_group.users:
                    recipients.append(user.partner_id.id)
            except:
                pass
        
        # Send notification
        if recipients:
            request.message_notify(
                partner_ids=list(set(recipients)),  # Remove duplicates
                subject=subject,
                body=message,
            )