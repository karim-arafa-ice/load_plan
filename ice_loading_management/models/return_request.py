from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ReturnRequest(models.Model):
    _name = 'ice.return.request'
    _description = 'Salesman Return Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    salesman_id = fields.Many2one('res.users', string='Salesman', required=True, readonly=True)
    date = fields.Date(string='Return Date', required=True, default=fields.Date.context_today, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('warehouse_check', 'Warehouse Check'),
        ('car_check', 'Car Check'),
        ('payment', 'Cash Payment'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    loading_request_ids = fields.Many2many('ice.loading.request', string='Associated Loading Requests')
    return_line_ids = fields.One2many('ice.return.request.line', 'return_request_id', string='Return Lines')
    car_check_request_ids = fields.One2many('maintenance.form', 'return_request_id', string='Car Check Requests')
    cash_payment_id = fields.Many2one('account.payment', string='Cash Payment', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('ice.return.request') or _('New')
        return super().create(vals)

    def action_start_return(self):
        self.ensure_one()
        self._create_return_lines()
        self._create_car_check_requests()
        self.state = 'warehouse_check'

    def _create_return_lines(self):
        """Create return lines from the day's loading requests."""
        # Logic to aggregate loaded quantities for each product across all of the day's loading requests
        # For simplicity, we'll create a wizard for the user to input returns.
        pass

    def _create_car_check_requests(self):
        """Create car check requests for all unique cars from the day's loadings."""
        cars = self.loading_request_ids.mapped('car_id')
        for car in cars:
            self.env['maintenance.form'].create({
                'vehicle_id': car.id,
                'is_daily_check': True, # Or a new type for 'post-return check'
                'city': self.loading_request_ids[0].loading_place_id.name if self.loading_request_ids else '',
                'return_request_id': self.id,
            })
        self.state = 'car_check'

    def action_open_warehouse_return_wizard(self):
        # This will open the wizard for warehouse staff
        return {
            'name': _('Process Warehouse Return'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.warehouse.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_return_request_id': self.id,
            }
        }

    def action_process_payment(self):
        # Logic to create and post a payment from the salesman's journal
        self.state = 'payment'
        # Simplified: In a real scenario, this would open a payment wizard or an account.payment form
        # with pre-filled data (journal, partner, etc.)
        self.cash_payment_id = self.env['account.payment'].create({
            'partner_id': self.salesman_id.partner_id.id,
            'amount': self.salesman_id.partner_id.commercial_partner_id.credit, # Example amount
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'journal_id': self.env['account.journal'].search([('type', '=', 'cash')], limit=1).id,
        }).id
        self.action_done()

    def action_done(self):
        self.state = 'done'

class ReturnRequestLine(models.Model):
    _name = 'ice.return.request.line'
    _description = 'Salesman Return Request Line'

    return_request_id = fields.Many2one('ice.return.request', string='Return Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    loaded_quantity = fields.Float(string='Loaded Quantity', readonly=True)
    returned_quantity = fields.Float(string='Returned Quantity')
    scrap_quantity = fields.Float(string='Scrap Quantity')