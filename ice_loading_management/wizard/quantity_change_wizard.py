from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class LoadingQuantityChangeWizard(models.TransientModel):
    _name = 'ice.loading.quantity.change.wizard'
    _description = 'Ice Loading Quantity Change Wizard'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True)
    change_reason = fields.Text(string='Reason for Change', required=True)
    line_ids = fields.One2many('ice.loading.quantity.change.wizard.line', 'wizard_id', string='Product Lines')
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loading_request_id = self.env.context.get('default_loading_request_id')
        if loading_request_id:
            loading_request = self.env['ice.loading.request'].browse(loading_request_id)
            # Create wizard lines from existing product lines
            lines = []
            for line in loading_request.product_line_ids:
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_type': line.product_type,
                    'current_quantity': line.quantity,
                    'new_quantity': line.quantity,
                    'max_capacity': line.max_capacity_for_product,
                    'product_weight': line.product_id.weight,
                }))
            res['line_ids'] = lines
        return res
    
    def action_confirm(self):
        """Confirm quantity changes and update loading request"""
        self.ensure_one()
        
        # Check if user has sales supervisor permissions
        if not self.env.user.has_group('sales_team.group_sale_salesman_all_leads'):
            raise UserError(_('Only Sales Supervisors can change quantities.'))
        
        # Check state
        if self.loading_request_id.state in ['ice_handled', 'plugged', 'in_transit', 'delivered', 'done', 'cancelled']:
            raise UserError(_('Cannot change quantities after the request has been ice handled.'))
        
        # Validate and update quantities
        changes_made = False
        for wizard_line in self.line_ids:
            if wizard_line.new_quantity != wizard_line.current_quantity:
                changes_made = True
                # Find corresponding product line
                product_line = self.loading_request_id.product_line_ids.filtered(
                    lambda l: l.product_id.id == wizard_line.product_id.id
                )
                if product_line:
                    # Create change history record
                    self.env['ice.loading.quantity.change'].create({
                        'loading_request_id': self.loading_request_id.id,
                        'product_id': wizard_line.product_id.id,
                        'old_quantity': wizard_line.current_quantity,
                        'new_quantity': wizard_line.new_quantity,
                        'change_reason': self.change_reason,
                    })
                    
                    # Update the quantity
                    product_line.quantity = wizard_line.new_quantity
                    product_line.is_full_load = False  # Reset full load flag
        
        if changes_made:
            # Post message in chatter
            message = _("Quantities changed by %s<br/>Reason: %s") % (
                self.env.user.name,
                self.change_reason
            )
            self.loading_request_id.message_post(
                body=message,
                subject=_('Loading Quantities Changed')
            )
            
            # If internal transfer exists, update it
            if self.loading_request_id.internal_transfer_id and self.loading_request_id.internal_transfer_id.state == 'assigned':
                picking = self.loading_request_id.internal_transfer_id
                for move in picking.move_ids_without_package:
                    product_line = self.loading_request_id.product_line_ids.filtered(
                        lambda l: l.product_id.id == move.product_id.id
                    )
                    if product_line:
                        move.product_uom_qty = product_line.quantity
        
        return {'type': 'ir.actions.act_window_close'}


class LoadingQuantityChangeWizardLine(models.TransientModel):
    _name = 'ice.loading.quantity.change.wizard.line'
    _description = 'Loading Quantity Change Wizard Line'
    
    wizard_id = fields.Many2one('ice.loading.quantity.change.wizard', string='Wizard', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True)
    product_type = fields.Selection([
        ('4kg', '4kg Ice'),
        ('25kg', '25kg Ice'),
        ('cup', 'Ice Cup')
    ], string='Product Type', readonly=True)
    current_quantity = fields.Float(string='Current Quantity', readonly=True)
    new_quantity = fields.Float(string='New Quantity', required=True)
    max_capacity = fields.Float(string='Max Capacity (kg)', readonly=True)
    product_weight = fields.Float(string='Product Weight', readonly=True)
    computed_weight = fields.Float(compute='_compute_weight', string='Weight (kg)')
    
    @api.depends('new_quantity', 'product_weight')
    def _compute_weight(self):
        for line in self:
            line.computed_weight = line.new_quantity * line.product_weight
    
    @api.constrains('new_quantity')
    def _check_quantity(self):
        for line in self:
            if line.new_quantity < 0:
                raise ValidationError(_("Quantity cannot be negative."))
            
            # Check capacity
            if line.computed_weight > line.max_capacity:
                raise ValidationError(_(
                    'Weight (%.2f kg) for product %s exceeds car capacity (%.2f kg)'
                ) % (line.computed_weight, line.product_id.name, line.max_capacity))
    
    @api.onchange('new_quantity')
    def _onchange_new_quantity(self):
        """Provide warning if capacity exceeded"""
        if self.new_quantity and self.product_weight:
            computed_weight = self.new_quantity * self.product_weight
            if computed_weight > self.max_capacity:
                return {
                    'warning': {
                        'title': _('Capacity Warning'),
                        'message': _('Weight (%.2f kg) exceeds car capacity (%.2f kg) for %s') % (
                            computed_weight, self.max_capacity, self.product_id.name
                        )
                    }
                }