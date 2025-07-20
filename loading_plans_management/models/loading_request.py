from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class LoadingRequest(models.Model):
    _name = 'ice.loading.request'
    _description = 'Ice Loading Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority asc, dispatch_time asc, create_date asc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('car_checking', 'Car Checking'),
        ('ready_for_loading', 'Ready for Loading'),
        ('receive_key', 'Car Key Received'),  
        ('loading', 'Loading'),   
        ('ice_handled', 'Ice Loaded'),     
        ('plugged', 'Plugged / Ready for Dispatch'),
        ('paused', 'Paused'),
        ('sign_form', 'Form signed'),
        ('delivering', 'Session Started'),
        ('delivered', 'Delivered'),
        ('second_loading_request', 'Second Loading Request'),
        ('empty_scrap', 'Empty Scrap'),
        ('ready_for_second_loading', 'Ready for Second Loading'),
        ('started_second_loading', 'Started Second Loading'),
        ('second_loading_done', 'Second Loading Done'),
        ('second_loading_delivering', 'Second Loading Delivering'),
        ('session_closed', 'Session Closed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    car_checking_start_date = fields.Datetime(string='Car Checking Start Date', readonly=True, copy=False)
    car_checking_end_date = fields.Datetime(string='Car Checking End Date', readonly=True, copy=False)
    loading_start_date = fields.Datetime(string='Loading Start Date', readonly=True, copy=False)
    loading_end_date = fields.Datetime(string='Loading End Date', readonly=True, copy=False)
    plugged_date = fields.Datetime(string='Plugged Date', readonly=True, copy=False)
    paused_date = fields.Datetime(string='Paused Date', readonly=True, copy=False)
    form_signed_date = fields.Datetime(string='Form Signed Date', readonly=True, copy=False)
    delivered_date = fields.Datetime(string='Delivered Date', readonly=True, copy=False)
    second_loading_request_date = fields.Datetime(string='Second Loading Request Date', readonly=True, copy=False)
    second_loading_start_date = fields.Datetime(string='Second Loading Start Date', readonly=True, copy=False)
    second_loading_end_date = fields.Datetime(string='Second Loading End Date', readonly=True, copy=False)
    session_closed_date = fields.Datetime(string='Session Closed Date', readonly=True, copy=False)
    done_date = fields.Datetime(string='Done Date', readonly=True, copy=False)
    is_warehouse_check = fields.Boolean(string='Warehouse Check and Empty Car', default=False, help="Indicates if the warehouse check is required before confirming the return.")
    is_payment_processed = fields.Boolean(string='Payment Processed', default=False, help="Indicates if the payment has been processed for this return request.")
    is_car_received = fields.Boolean(string='Car Received From Fleet', default=False, help="Indicates if the car has been received back after the return.")
    has_second_loading = fields.Boolean(string='Has Second Loading', default=False, help="Indicates if this request has a second loading.")

    session_id = fields.Many2one('ice.driver.session', string='Driver Session', readonly=True, copy=False)
    car_id = fields.Many2one('fleet.vehicle', string='Car', required=True, 
                           domain="[('loading_status', '=', 'available')]")
    salesman_id = fields.Many2one('res.users', string='Salesman', required=True,domain="[('is_loading_plan_implemented', '=', True)]")
    special_packing = fields.Char(string='Special Packing')
    route_id = fields.Many2one('crm.team', string='Route (Sales Team)', readonly=True)
    team_leader_id = fields.Many2one('res.users', string='Team Leader', readonly=True)
    dispatch_time = fields.Datetime(string='Dispatch Time', required=True)
    loading_place_id = fields.Many2one('ice.loading.place', string='Loading Place', required=True)

    product_line_ids = fields.One2many('ice.loading.product.line', 'loading_request_id', string='Products')
    second_product_line_ids = fields.One2many('second.ice.loading.product.line', 'loading_request_id', string='Second Products')
    first_loading_scrap_ids = fields.One2many('stock.scrap', 'loading_request_id', string='First Loading Scraps', readonly=True)
    loading_scrap_orders_ids = fields.One2many('stock.scrap', 'loading_request_id', string='Loading Scraps', readonly=True)

    previous_car_id = fields.Many2one('fleet.vehicle', string='Previous Car', readonly=True)
    car_change_reason = fields.Text(string='Car Change Reason', readonly=True)
    car_changed_by_id = fields.Many2one('res.users', string='Car Changed By', readonly=True)
    car_change_date = fields.Datetime(string='Car Change Date', readonly=True)

    car_check_request_id = fields.Many2one('maintenance.form', string='Car Check Request')
    return_car_check_request_id = fields.Many2one('maintenance.form', string='Return Car Check Request')
    car_check_request_count = fields.Integer(compute='_compute_request_counts')
    internal_transfer_id = fields.Many2one('stock.picking', string='Internal Transfer')
    second_internal_transfer_id = fields.Many2one('stock.picking', string='Second Internal Transfer')
    picking_count = fields.Integer(compute='_compute_request_counts')
    cash_payment_id = fields.Many2one('account.payment', string='Cash Payment', readonly=True)
    salesman_cash_journal_id = fields.Many2one('account.journal', string="Salesman's Cash Journal", compute='_compute_salesman_cash_journal')
    salesman_balance = fields.Monetary(string="Salesman's Balance",compute='_compute_salesman_cash_journal')
    actual_cash_received = fields.Monetary(string="Actual Cash Received")
    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank','cash')), ('id', '!=', salesman_cash_journal_id)]",
        
    )
    currency_id = fields.Many2one('res.currency', related='salesman_cash_journal_id.currency_id')

    signed_loading_form = fields.Binary(string="Signed Loading Form from Salesman")
    signed_loading_form_filename = fields.Char(string="Loading Form Filename")
    loading_form_uploaded_by_id = fields.Many2one('res.users', string='Loading Form Uploaded By', readonly=True)
    loading_form_upload_date = fields.Datetime(string='Loading Form Upload Date', readonly=True)

    total_weight = fields.Float(compute='_compute_total_weight', string='Total Weight (kg)', store=True)

    quantity_change_ids = fields.One2many('ice.loading.quantity.change', 'loading_request_id', string='Quantity Changes')

    is_urgent = fields.Boolean(string="Urgent Request", default=False, help="Bypass 6-hour dispatch rule.")
    pause_reason = fields.Text(string="Pause Reason", readonly=True)
    is_concrete = fields.Boolean(related='car_id.is_concrete', string='Is Concrete', store=True, readonly=True)
    customer_line_ids = fields.One2many('ice.loading.customer.line', 'loading_request_id', string='Customer Lines')
    return_picking_id = fields.Many2one('stock.picking', string='Return Picking', readonly=True)
    quantity_changes = fields.One2many('ice.loading.quantity.change', 'loading_request_id', string='Quantity Changes')
    priority = fields.Integer(string='Priority', compute='_compute_priority', store=True, readonly=False, default=10, help="Priority for loading. Lower is higher.")

    first_loading_scrap_count = fields.Integer(compute='_compute_request_counts')
    loading_scrap_orders_count = fields.Integer(compute='_compute_request_counts')
    return_car_check_request_count = fields.Integer(compute='_compute_request_counts')
    second_internal_transfer_count = fields.Integer(compute='_compute_request_counts')
    return_picking_count = fields.Integer(compute='_compute_request_counts')
    quantity_changes_count = fields.Integer(compute='_compute_request_counts')

   
    
    @api.depends(
    'car_check_request_id',
    'first_loading_scrap_ids',
    'loading_scrap_orders_ids',
    'return_car_check_request_id',
    'second_internal_transfer_id',
    'return_picking_id',
    'quantity_change_ids'
    )
    def _compute_request_counts(self):
        for request in self:
            # Initialize all fields for this specific record
            request.first_loading_scrap_count = len(request.first_loading_scrap_ids) if request.first_loading_scrap_ids else 0
            request.loading_scrap_orders_count = len(request.loading_scrap_orders_ids) if request.loading_scrap_orders_ids else 0
            request.quantity_changes_count = len(request.quantity_change_ids) if request.quantity_change_ids else 0
            request.car_check_request_count = 1 if request.car_check_request_id else 0
            request.return_car_check_request_count = 1 if request.return_car_check_request_id else 0
            request.second_internal_transfer_count = 1 if request.second_internal_transfer_id else 0
            request.return_picking_count = 1 if request.return_picking_id else 0
            request.picking_count = self.env['stock.picking'].search_count(
                [('loading_request_id', '=', request.id), ('is_second_loading', '=', False)]
            )

    def action_view_first_loading_scrap_orders(self):
        self.ensure_one()
        return {
            'name': _('First Loading Scraps'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.first_loading_scrap_ids.ids)],
        }

    def action_view_loading_scrap_orders(self):
        self.ensure_one()
        return {
            'name': _('Loading Scrap Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.loading_scrap_orders_ids.ids)],
        }
    
    def action_view_return_car_check_request(self):
        self.ensure_one()
        return {
            'name': _('Return Car Check Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.form',
            'view_mode': 'form',
            'res_id': self.return_car_check_request_id.id,
        }

    def action_view_second_internal_transfer(self):
        self.ensure_one()
        return {
            'name': _('Second Internal Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.second_internal_transfer_id.id,
        }
    def action_view_return_picking(self):
        self.ensure_one()
        return {
            'name': _('Return Picking'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.return_picking_id.id,
        }

    

    @api.depends('loading_place_id.priority', 'dispatch_time', 'is_urgent', 'has_second_loading')
    def _compute_priority(self):
        for request in self:
            priority = request.loading_place_id.priority or 10
            
            # Urgent requests get the highest priority
            if request.is_urgent:
                priority = 1
            # Second loading requests are next
            elif request.has_second_loading:
                priority = 2
            
            request.priority = priority
    @api.constrains('state', 'loading_place_id')
    def _check_loading_capacity(self):
        """Constraint to ensure only 2 requests can be in 'loading' state per place."""
        for request in self:
            if request.state == 'loading':
                domain = [
                    ('loading_place_id', '=', request.loading_place_id.id),
                    ('state', 'in', ['loading','started_second_loading']),
                    ('id', '!=', request.id)
                ]
                loading_count = self.search_count(domain)
                if loading_count >= 2:
                    raise ValidationError(_("A loading place can only have a maximum of 2 cars loading at the same time."))
                
    @api.constrains('car_id', 'dispatch_time','state')
    def _check_car_open_request_per_day(self):
        for request in self:
            if request.car_id and request.dispatch_time:
                domain = [
                    ('car_id', '=', request.car_id.id),
                    ('dispatch_time', '>=', fields.Date.start_of(request.dispatch_time, 'day')),
                    ('dispatch_time', '<=', fields.Date.end_of(request.dispatch_time, 'day')),
                    ('state', 'not in', ['done', 'cancelled','draft']),
                    ('id', '!=', request.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("This car is already in an open request for today."))
    @api.constrains('dispatch_time', 'is_urgent')
    def _check_dispatch_time(self):
        """
        MODIFIED: Urgent requests must be at least 3 hours from now.
                  Regular requests must be at least 6 hours from now.
        """
        for request in self:
            if request.dispatch_time:
                now = datetime.now()
                if request.is_urgent:
                    if request.dispatch_time < now + timedelta(hours=3):
                        raise ValidationError(_("Urgent dispatch time must be at least 3 hours from now."))
                else:
                    if request.dispatch_time < now + timedelta(hours=6):
                        raise ValidationError(_("Dispatch time must be at least 6 hours from now. For a shorter time, mark the request as urgent."))
                    
    @api.constrains('car_id', 'dispatch_time', 'is_urgent')
    def _check_urgent_per_day(self):
        for request in self:
            if request.is_urgent:
                domain = [
                    ('car_id', '=', request.car_id.id),
                    ('is_urgent', '=', True),
                    ('dispatch_time', '>=', fields.Date.start_of(request.dispatch_time, 'day')),
                    ('dispatch_time', '<=', fields.Date.end_of(request.dispatch_time, 'day')),
                    ('id', '!=', request.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("A car can only have one urgent loading request per day."))
    
    @api.constrains('salesman_id', 'dispatch_time', 'has_second_loading')
    def _check_salesman_daily_loadings(self):
        for request in self:
            # Base domain for same salesman on same day (excluding current record)
            base_domain = [
                ('salesman_id', '=', request.salesman_id.id),
                ('dispatch_time', '>=', fields.Date.start_of(request.dispatch_time, 'day')),
                ('dispatch_time', '<=', fields.Date.end_of(request.dispatch_time, 'day')),
                ('id', '!=', request.id),
                ('state', 'not in', ['cancelled', 'draft']),
                ('is_concrete', '=', False),
            ]
            
            # Check existing requests with second loading
            existing_with_second_loading = self.search_count(base_domain + [('has_second_loading', '=', True)])
            
            # Check existing requests without second loading
            existing_without_second_loading = self.search_count(base_domain + [('has_second_loading', '=', False)])
            
            if request.has_second_loading:
                # If current request has second loading
                if existing_with_second_loading > 0:
                    raise ValidationError(_(
                        "A salesman can only have one loading request with second loading per day. "
                        "There is already a request with second loading for %s on %s."
                    ) % (request.salesman_id.name, request.dispatch_time.strftime('%Y-%m-%d')))
                
                if existing_without_second_loading > 0:
                    raise ValidationError(_(
                        "A salesman cannot have a request with second loading when there are already "
                        "requests without second loading on the same day. "
                        "There are %d existing request(s) without second loading for %s on %s."
                    ) % (existing_without_second_loading, request.salesman_id.name, request.dispatch_time.strftime('%Y-%m-%d')))
            
            else:
                # If current request does NOT have second loading
                if existing_with_second_loading > 0:
                    raise ValidationError(_(
                        "A salesman cannot have a request without second loading when there is already "
                        "a request with second loading on the same day. "
                        "There is already a request with second loading for %s on %s."
                    ) % (request.salesman_id.name, request.dispatch_time.strftime('%Y-%m-%d')))
                
                if existing_without_second_loading >= 2:
                    raise ValidationError(_(
                        "A salesman can only have a maximum of two loading requests without second loading per day. "
                        "There are already %d request(s) without second loading for %s on %s."
                    ) % (existing_without_second_loading, request.salesman_id.name, request.dispatch_time.strftime('%Y-%m-%d')))
                
    @api.constrains('salesman_id', 'state')
    def _check_salesman_open_sessions(self):
        for request in self:
            if request.state == 'delivering' and not request.is_concrete:
                # Get today's date range
                today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0)
                today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59)
                
                # Count existing open sessions for this salesman today (excluding current request's session)
                domain = [
                    ('driver_id', '=', request.salesman_id.id),
                    ('session_start', '>=', today_start),
                    ('session_start', '<=', today_end),
                    ('is_active', '=', True)
                ]
                
                # Exclude current request's session if it exists
                if request.session_id:
                    domain.append(('id', '!=', request.session_id.id))
                
                open_sessions_count = self.env['ice.driver.session'].search_count(domain)
                
                # Check if adding this session would exceed the limit
                # If this request doesn't have a session yet, it will create one, so we count it
                total_sessions_after = open_sessions_count + (1 if not request.session_id else 0)
                
                if total_sessions_after > 2:
                    raise ValidationError(_(
                        "A salesman can only have a maximum of two open sessions per day. "
                        "Salesman %s already has %d open session(s) today. "
                        "Cannot start delivery for this loading request."
                    ) % (request.salesman_id.name, open_sessions_count))
                
                # Additional check: if salesman already has 2 sessions and this request doesn't have a session
                if open_sessions_count >= 2 and not request.session_id:
                    raise ValidationError(_(
                        "Cannot start delivery. Salesman %s already has the maximum of 2 open sessions today. "
                        "Please close an existing session before starting a new delivery."
                    ) % request.salesman_id.name)
                
    

    @api.constrains('salesman_id', 'state')
    def _check_salesman_credit_limit(self):
        for request in self:
             if request.state == 'car_checking':
                journal = request.salesman_id.journal_id
                if journal.credit_limit > 0 and journal.balance > journal.credit_limit:
                     raise ValidationError(_("Salesman has exceeded the credit limit of %s. Current balance is %s.") % (journal.credit_limit, journal.balance))

    def _get_default_product_lines_values(self, concrete=False):
        """
        Refactored method: returns a list of values for product lines
        without creating them. This can be used by both onchange and create.
        :param concrete: Boolean indicating if the request is for concrete.
        :return: List of tuples with product line values.
        """
        product_tmpls = []
        if concrete:
            product_tmpls = [
                self.env.company.product_25kg_id,
            ]
        else:
            product_tmpls = [
                self.env.company.product_4kg_id,
                self.env.company.product_25kg_id,
                self.env.company.product_cup_id,
            ]
        lines_values = []
        for template in product_tmpls:
            if template and template.product_variant_id:
                lines_values.append((0, 0, {
                    'product_id': template.product_variant_id.id,
                    'quantity': 0.0,
                }))
        return lines_values
    
    # def action_open_session(self):
    #     self.ensure_one()
    #     if self.state != 'sign_form':
    #         raise UserError(_("You can only open a session when the request is in 'Sign Form' state."))

    #     # Create a new driver session
    #     session = self.env['ice.driver.session'].create({
    #         'driver_id': self.salesman_id.id,
    #         'car_id': self.car_id.id,
    #         'loading_request_id': self.id,
    #     })

    #     self.write({
    #         'state': 'delivering',
    #         'session_id': session.id
    #     })
    def action_open_second_loading_session(self):
        self.ensure_one()
        if self.state != 'second_loading_done':
            raise UserError(_("You can only open a second loading session when the request is in 'Second Loading Done' state."))

        self.write({
            'state': 'second_loading_delivering',
        })

        self.message_post(body=_("Driver session started by %s.") % self.env.user.name)

    @api.onchange('is_concrete')
    def _onchange_is_concrete(self):
        self.product_line_ids = [(5, 0, 0)]
        self.customer_line_ids = [(5, 0, 0)]
        if self.is_concrete:
            # Clear existing product lines
            self.product_line_ids = self._get_default_product_lines_values(concrete=True)

            # Logic to handle concrete-specific fields
            pass
        else:
            # Logic for non-concrete requests
            self.product_line_ids = self._get_default_product_lines_values(concrete=False)

    @api.onchange('product_line_ids')
    def _onchange_full_load(self):
        """When full load is checked, set quantity to max capacity for each product"""
        for line in self.product_line_ids:
            if line.is_full_load:
                if line.product_type == '4kg':
                    line.quantity = self.car_id.ice_4kg_capacity
                elif line.product_type == '25kg':
                    line.quantity = self.car_id.ice_25kg_capacity
                elif line.product_type == 'cup':
                    line.quantity = self.car_id.ice_cup_capacity
            elif line.quantity < 0:
                raise UserError(_("Quantity cannot be negative. Please enter a valid quantity."))
            else:
                line.quantity = 0.0

    def action_change_quantities_wizard(self):
        """Open quantity change wizard for sales supervisor"""
        self.ensure_one()
        
        # Check if user has sales supervisor permissions
        if not self.env.user.has_group('loading_plans_management.group_sales_supervisor'):
            raise UserError(_('Only Sales Supervisors can change quantities.'))
        
        # Check if state allows quantity changes
        if self.state not in ['draft', 'car_checking', 'ready_for_loading','receive_key']:
            raise UserError(_('Cannot change quantities after the request has been started loading.'))

        return {
            'name': _('Change Loading Quantities'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.loading.quantity.change.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }
    def action_loading_worker_wizard(self):
        """Open loading worker wizard to update quantities"""
        self.ensure_one()
        
        if not self.env.user.has_group('loading_plans_management.group_loading_worker'):
            raise UserError(_('Only Loading Workers can access this function.'))
        
        if self.state != 'loading':
            raise UserError(_('Loading quantities can only be updated when the request is in "Loading" state.'))

        return {
            'name': _('Update Loading Quantities'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.loading.worker.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('loading_plans_management.view_loading_worker_wizard_simple_form').id,
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }

    def action_second_loading_worker_wizard(self):
        """Open loading worker wizard to update quantities"""
        self.ensure_one()
        
        if not self.env.user.has_group('loading_plans_management.group_loading_worker'):
            raise UserError(_('Only Loading Workers can access this function.'))
        
        if self.state != 'started_second_loading':
            raise UserError(_('Loading quantities can only be updated when the request is in "Started Second Loading" state.'))

        return {
            'name': _('Update Loading Quantities'),
            'type': 'ir.actions.act_window',
            'res_model': 'second.ice.loading.worker.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('loading_plans_management.view_second_loading_worker_wizard_simple_form').id,
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }
    
    def action_pause_loading(self):
        self.ensure_one()
        # This action now opens the wizard. The wizard's action will do the pausing.
        return {
            'name': _('Reason for Pausing'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.pause.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loading_request_id': self.id}
        }
    
    def action_continue_loading(self):
        self.ensure_one()
        self.message_post(body=_('Loading continued by %s.') % self.env.user.name)
        return self.write({'state': 'plugged'})
    
    def write(self, vals):
        """Track loading priority changes and car changes"""
        for record in self:

            if 'car_id' in vals and vals['car_id'] != record.car_id.id:
                if record.state not in ['draft', 'car_checking']:

                    raise UserError(_(
                        'Cannot change car for loading request "%s" because it is in "%s" status. '
                        'Car changes are only allowed before the "Ready for Loading" stage.'
                    ) % (record.name, dict(record._fields['state'].selection)[record.state]))
            # Track loading priority changes
            
            # Track form uploads
            if 'signed_loading_form' in vals and vals['signed_loading_form']:
                vals.update({
                    'loading_form_uploaded_by_id': self.env.user.id,
                    'loading_form_upload_date': fields.Datetime.now(),
                })
            
          
            
            # Track car changes (when not done through wizard)
            if 'car_id' in vals and vals['car_id'] != record.car_id.id:
                old_car = record.car_id.license_plate or record.car_id.name or 'None'
                new_car = self.env['fleet.vehicle'].browse(vals['car_id'])
                new_car_name = new_car.license_plate or new_car.name or 'None'
                record.message_post(
                    body=_('Car changed from %s to %s') % (old_car, new_car_name),
                    subject=_('Car Changed')
                )
        
        return super().write(vals)
    
    def action_print_loading_form(self):
        """Print loading form for salesman signature"""
        self.ensure_one()

        # Check if user has fleet supervisor permissions
        if not (self.env.user.has_group('loading_plans_management.group_fleet_supervisor')):
            raise UserError(_('Only Fleet Supervisors can print loading forms.'))
        
        # Check if we're in the right state for printing
        valid_states = ['plugged']
        if self.state not in valid_states:
            # raise UserError(_('Loading form can only be printed when request is in "Plugged", "Freezer Loaded", or "Freezer Handled" state.'))
            raise UserError(_('Loading form can only be printed when request is in "Plugged" state.'))

        # Return report action
        return self.env.ref('loading_plans_management.action_report_loading_form').report_action(self)
    
    def action_upload_loading_form(self):
        """Upload signed loading form and update status"""
        self.ensure_one()
        
        # Check if user has fleet supervisor permissions
        if not (self.env.user.has_group('loading_plans_management.group_fleet_supervisor')):
            raise UserError(_('Only Fleet Supervisors can upload loading forms.'))
        
        # Check valid states for upload
        valid_states = ['plugged']
        if self.state not in valid_states:
            # raise UserError(_('Loading form can only be uploaded when request is in "Plugged", "Freezer Loaded", or "Freezer Handled" state.'))
            raise UserError(_('Loading form can only be uploaded when request is in "Plugged" state.'))
        
        if not self.signed_loading_form:
            raise UserError(_('Please upload the signed loading form first.'))
        
        # Update status to sign_form
        self.write({
            'state': 'sign_form',
            'form_signed_date': fields.Datetime.now(),
            })
        
        # Log the action
        self.message_post(
            body=_('Signed loading form uploaded by %s. Status changed to "Form Signed".') % self.env.user.name,
            subject=_('Loading Form Uploaded')
        )
        
        # Notify relevant people
        self._notify_form_upload('loading_form')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Loading Form Uploaded'),
                'message': _('Signed loading form uploaded successfully. Status changed to "Form Signed".'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _notify_form_upload(self, form_type):
        """Notify relevant people about form upload"""
        recipients = []
        
        # Notify salesman
        if self.salesman_id:
            recipients.append(self.salesman_id.partner_id.id)
        
        # Notify team leader
        if self.team_leader_id:
            recipients.append(self.team_leader_id.partner_id.id)
        
        # Notify sales supervisor
        try:
            sales_supervisor_group = self.env.ref('loading_plans_management.group_sales_supervisor')
            for user in sales_supervisor_group.users:
                recipients.append(user.partner_id.id)
        except:
            pass
        
        if recipients:
            form_messages = {
                # 'freezer_release': 'Freezer Release Form has been signed and uploaded',
                'loading_form': 'Loading Form has been signed and uploaded'
            }
            
            subject = _('%s for Loading Request %s') % (form_messages.get(form_type, 'Form'), self.name)
            message = _("""
            <p>The <strong>%s</strong> has been signed and uploaded for loading request <strong>%s</strong>:</p>
            <ul>
                <li><strong>Car:</strong> %s</li>
                <li><strong>Salesman:</strong> %s</li>
                <li><strong>Uploaded by:</strong> %s</li>
                <li><strong>Upload Date:</strong> %s</li>
                <li><strong>Status:</strong> %s</li>
            </ul>
            """) % (
                form_messages.get(form_type, 'Form'),
                self.name,
                self.car_id.license_plate or self.car_id.name,
                self.salesman_id.name,
                self.env.user.name,
                fields.Datetime.now().strftime('%Y-%m-%d %H:%M'),
                dict(self._fields['state'].selection)[self.state]
            )
            
            self.message_notify(
                partner_ids=list(set(recipients)),
                subject=subject,
                body=message,
            )

    def action_change_car(self):
        """Open car change wizard with status validation"""
        self.ensure_one()
        
        # Check if car change is allowed based on current state
        # if self.state in ['ready_for_loading', 'loaded', 'freezer_loaded', 'plugged', 'in_transit', 'delivered']:
        if self.state not in ['draft', 'car_checking', 'ready_for_loading']:
            raise UserError(_(
                'Cannot change car because the loading request is in "%s" status. '
                'Car changes are only allowed before the "Ready for Loading" stage.'
            ) % dict(self._fields['state'].selection)[self.state])
        
        return {
            'name': _('Change Car'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.car.change.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
                'default_current_car_id': self.car_id.id,
            }
        }
    
    @api.onchange('salesman_id')
    def _onchange_salesman_id(self):
        if self.salesman_id:
            team = self.env['crm.team'].search([('member_ids', 'in', [self.salesman_id.id])], limit=1)
            if team:
                self.write({
                    'route_id': team.id,
                    'team_leader_id': team.user_id.id,
                })

    def action_proceed_to_plugged(self):
        """Move to plugged state after all forms are handled"""
        self.ensure_one()
        
        # Check if user has fleet supervisor permissions
        if not (self.env.user.has_group('loading_plans_management.group_fleet_supervisor')):
            raise UserError(_('Only Fleet Supervisors can proceed to plugged state.'))
        
        # Check current state
        if self.state != 'ice_handled':
            raise UserError(_('Loading request must be in "Ice Handled" state to proceed to plugged.'))
        
        # Update status and car status
        self.write({
            'state': 'plugged',
            'plugged_date': fields.Datetime.now(),
            
            })
        self.car_id.write({'loading_status': 'plugged'})
        
        # Log the action
        self.message_post(
            body=_('Car plugged and ready for dispatch by %s.') % self.env.user.name,
            subject=_('Car Plugged - Ready for Dispatch')
        )
        
        # Notify salesman and team
        self._notify_car_ready_for_dispatch()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Car Plugged'),
                'message': _('Car is now plugged and ready for dispatch.'),
                'type': 'success',
                'sticky': False,
            }
        }
    @api.depends('product_line_ids.computed_weight')
    def _compute_total_weight(self):
        for record in self:
            record.total_weight = sum(record.product_line_ids.mapped('computed_weight'))
    
    # def _compute_request_counts(self):
    #     for request in self:
    #         request.car_check_request_count = 1 if request.car_check_request_id else 0
    #         request.picking_count = 1 if request.internal_transfer_id else 0
    
    
    def action_confirm_request(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("You can only confirm a request in 'Draft' state."))
        self._create_related_records()
        self._send_creation_notifications()

    @api.model
    def create(self, vals):
        # Set sequence, team leader, etc.
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ice.loading.request') or 'New'
        if 'salesman_id' in vals and vals['salesman_id']:
            team = self.env['crm.team']._get_default_team_id(user_id=vals['salesman_id'])
            if team:
                vals['route_id'] = team.id
                vals['team_leader_id'] = team.user_id.id

        # Add default product lines if not a concrete request
        if vals.get('is_concrete'):
            vals['product_line_ids'] = self._get_default_product_lines_values(concrete=True)
        else:
            vals['product_line_ids'] = self._get_default_product_lines_values(concrete=False)
        request = super().create(vals)
        return request
    
    def _send_creation_notifications(self):
        """Send notifications to all required departments"""
        groups_to_notify = [
            'customer_management.group_collections_department',
            'account.group_account_manager',
            'maintenance_app.maintenance_workshop_supervisor_group',
            'mrp.group_mrp_manager',
            'stock.group_stock_manager',
            'maintenance_app.maintenance_fleet_supervisor_group',
            'sales_team.group_sale_salesman_all_leads',
            'sales_team.group_sale_manager',
        ]
        
        for group_xml_id in groups_to_notify:
            try:
                group = self.env.ref(group_xml_id)
                users = group.users
                self.message_notify(
                    partner_ids=users.partner_id.ids,
                    subject=f'New Loading Request: {self.name}',
                    body=f'A new loading request has been created for car {self.car_id.license_plate} with salesman {self.salesman_id.name}.',
                )
            except:
                continue
    
    def _create_related_records(self):
        """Create car check request, freezer renting requests, and internal transfer"""
        # 1. Create car check request
        self._create_car_check_request()
        
        # # 3. Create internal transfer
        self._create_internal_transfer()

    def _create_car_check_request(self):
        """Create maintenance request for car check"""
        maintenance_request = self.env['maintenance.form'].create({
            'vehicle_id': self.car_id.id,  
            'is_daily_check': True,  
            'city': self.loading_place_id.name,
            'loading_request_id': self.id,
        })
        self.state = 'car_checking'
        self.car_checking_start_date = fields.Datetime.now()
        self.car_check_request_id = maintenance_request.id
        self.car_id.loading_status = 'in_use'
        self.message_post(
            body=_('Car check request created: %s') % maintenance_request.name,
            subject=_('Car Check Request Created')
        )
        

    def _create_internal_transfer(self):
        """Create internal transfer for loading request"""
        if not self.product_line_ids and not self.is_concrete:
            raise UserError(_("Please add products to the loading request before creating an internal transfer."))

        move_lines = []
        source_location_id = False
        _logger.info("Creating internal transfer for loading request %s", self.id)
        if self.is_concrete:
            if not self.car_id.location_id:
                raise UserError(_("The selected concrete car does not have a Source Location configured."))
            source_location_id = self.loading_place_id.loading_location_id.id            
            # Total quantity is summed from customer lines
            total_quantity = sum(self.customer_line_ids.mapped('quantity'))
            self.product_line_ids[1].quantity = total_quantity
            self.product_line_ids[1].quantity_in_pcs = total_quantity
            if total_quantity <= 0:
                raise UserError(_("Total quantity for concrete loading request must be greater than zero."))
        else:
            source_location_id = self.loading_place_id.loading_location_id.id
        for line in self.product_line_ids:
            if line.quantity > 0:
                # Use the computed quantity in pieces for the transfer
                move_lines.append((0, 0, {
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity_in_pcs,
                    # 'product_uom': self.env.ref('uom.product_uom_unit').id, # Always transfer in PCs
                    'location_id': source_location_id,
                    'location_dest_id': self.salesman_id.accessible_location_id.id,
                }))
        
        if not move_lines:
            raise UserError(_("Cannot create a transfer with zero quantity. Please add quantities to the lines."))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.lot_stock_id', '=', source_location_id)
        ], limit=1)
        _logger.info("Found picking type %s for source location %s", picking_type.name if picking_type else 'None', source_location_id)
        if not picking_type:
            raise UserError(_("No internal transfer operation type found for the source location."))
        _logger.info("Creating stock picking for loading request %s", self.id)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source_location_id,
            'location_dest_id': self.car_id.location_id.id if self.is_concrete else self.salesman_id.accessible_location_id.id,
            'move_ids_without_package': move_lines,
            'origin': self.name,
            'transfer_vehicle': self.car_id.id,
            'loading_driver_id': self.salesman_id.id,
            'car_id': self.car_id.id,
            'loading_request_id': self.id,
        })
        _logger.info("Stock picking created with ID %s", picking.id)
        
        self.internal_transfer_id = picking.id
        picking.action_confirm()
        picking.action_assign()

        self.message_post(
            body=_('Internal transfer created: %s') % picking.name,
            subject=_('Internal Transfer Created')
        )

    def action_start_delivery(self):
        self.ensure_one()
        if not self.signed_loading_form:
            raise UserError(_("You must upload the signed loading form from the salesman before start."))
        
        # Change car driver
        self.car_id.write({'driver_id': self.salesman_id.partner_id.id})
        

        # Create a new driver session
        session = self.env['ice.driver.session'].create({
            'driver_id': self.salesman_id.id,
            'car_id': self.car_id.id,
            'loading_request_id': self.id,
        })

        self.write({
            'state': 'delivering',
            'session_id': session.id
        })




    def action_view_maintenance_request(self):
        self.ensure_one()
        if not self.car_check_request_id:
            raise UserError(_("No maintenance request found for this loading request."))
        return self._get_action_view(self.car_check_request_id, 'maintenance_app.maintenance_form_action')

    def action_view_picking(self):
        self.ensure_one()
        if not self.internal_transfer_id:
            raise UserError(_("No internal transfer found for this loading request."))
        return self._get_action_view(self.internal_transfer_id, 'stock.action_picking_tree_all')
    
    def action_view_first_loading_scrap_orders(self):
        self.ensure_one()
        if not self.first_loading_scrap_ids:
            raise UserError(_("No internal transfer found for this loading request."))
        return self._get_action_view(self.internal_transfer_id, 'stock.action_picking_tree_all')
    
    def action_receive_car_keys(self):
        """NEW: Action to move the request to 'Loading' state."""
        self.ensure_one()
        if self.state != 'ready_for_loading':
            raise UserError(_("Car keys can only be received when the request is in 'Ready for Loading' state."))

        # The constraint '_check_loading_capacity' will be triggered automatically on write.
        self.write({
            'state': 'loading',
            'loading_start_date': fields.Datetime.now(),
            })
        self.message_post(body=_("Car keys received. The car is now in the loading area."))

    def _notify_car_ready_for_dispatch(self):
        recipients = []
        
        if self.salesman_id:
            recipients.append(self.salesman_id.partner_id.id)
        
        if self.team_leader_id:
            recipients.append(self.team_leader_id.partner_id.id)
        
        if recipients:
            subject = _('Car Ready for Dispatch - Loading Request %s') % self.name
            message = _("""
            <p>Your car is now <strong>plugged and ready for dispatch</strong>:</p>
            <ul>
                <li><strong>Loading Request:</strong> %s</li>
                <li><strong>Car:</strong> %s</li>
                <li><strong>Dispatch Time:</strong> %s</li>
                <li><strong>Loading Place:</strong> %s</li>
            </ul>
            <p>You can now pick up the car and start delivery.</p>
            """) % (
                self.name,
                self.car_id.license_plate or self.car_id.name,
                self.dispatch_time.strftime('%Y-%m-%d %H:%M') if self.dispatch_time else 'Not set',
                self.loading_place_id.name
            )
            
            self.message_notify(
                partner_ids=list(set(recipients)),
                subject=subject,
                body=message,
            )
    def _get_action_view(self, record, action_xmlid):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(action_xmlid)
        if record:
            action['res_id'] = record.id
            action['view_mode'] = 'form'
            action['views'] = [(False, 'form')]
        return action
    def action_view_quantity_changes(self):
        """Open quantity change history for this loading request"""
        self.ensure_one()
        return {
            'name': _('Quantity Change History'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.loading.quantity.change',
            'view_mode': 'tree,form',
            'domain': [('loading_request_id', '=', self.id)],
            'context': {'default_loading_request_id': self.id},
        }
    def action_close_session(self):
        self.ensure_one()
        if self.is_concrete:
            self.write({
                'state': 'session_closed',
                'session_closed_date': fields.Datetime.now(),
                })
        else:
            return {
                'name': _('Close Session'),
                'type': 'ir.actions.act_window',
                'res_model': 'ice.close.session.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_loading_request_id': self.id,
                }
        }
    def action_scrap_products(self):
        self.ensure_one()
        return {
            'name': _('Scrap Products'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.scrap.products.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }
    def action_start_second_loading(self):
        self.ensure_one()
        # Update state to started_second_loading
        self.write({'state': 'started_second_loading',
                    'second_loading_start_date': fields.Datetime.now()
                    })
        self.message_post(body=_("Second loading started for the car."))

    def action_second_loading_done(self):
        self.ensure_one()
        # Update state to session_closed
        self.write({'state': 'session_closed',
                    'second_loading_end_date': fields.Datetime.now()
                    })
        self.message_post(body=_("Second loading Loaded for the car."))

    @api.depends('salesman_id')
    def _compute_salesman_cash_journal(self):
        for rec in self:
            # You might need a more robust way to find the salesman's cash journal
            rec.salesman_cash_journal_id = rec.salesman_id.journal_id
            rec.salesman_balance = rec.salesman_id.journal_id.balance

    def action_handle_car(self):
        if not self.is_warehouse_check:
            raise UserError(_("Warehouse check is not completed."))
        self.ensure_one()
        self.write({
            'is_car_received': True,
        })
        if self.is_concrete:
            self.state = 'done'
            self.done_date = fields.Datetime.now()
        self._create_car_daily_maintenance_requests()
        
    def _create_car_daily_maintenance_requests(self):
        car = self.car_id
        return_car_check_request_id = self.env['maintenance.form'].create({
            'vehicle_id': car.id,
            'is_daily_check': True, # Or a new type for 'post-return check'
            'city': self.loading_place_id.name if self.loading_place_id else '',
            'loading_request_id': self.id,
        })
        self.return_car_check_request_id = return_car_check_request_id.id
        self.message_post(
            body=_('Post-return car check request created: %s') % return_car_check_request_id.name,
            subject=_('Post-Return Car Check Request Created')
        )

    def action_process_cash_return(self):
        self.ensure_one()
        if not self.salesman_cash_journal_id:
            raise UserError(_("Salesman's cash journal is not configured."))
        if self.actual_cash_received <= 0 and not self.is_concrete:
            raise UserError(_("Actual cash received must be a positive value."))

        payment = self.env['account.payment'].create({
            # 'partner_id': self.salesman_id.partner_id.id,
            'is_internal_transfer': True,
            'amount': self.actual_cash_received,
            'payment_type': 'outbound',
            # 'partner_type': 'customer',
            'journal_id': self.salesman_cash_journal_id.id,
            'destination_journal_id': self.destination_journal_id.id
        })
        payment.action_post()  
        self.write({
            'cash_payment_id': payment.id,
            'is_payment_processed': True,
        })
        if self.is_car_received and self.is_payment_processed and self.is_warehouse_check:
            self.state = 'done'
            self.done_date = fields.Datetime.now()


    def action_empty_warehouse(self):
        self.ensure_one()
        # This will open the wizard for warehouse staff
        return {
            'name': _('Process Warehouse Return'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.warehouse.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }
    
    def action_view_scrap_orders(self):
        """Show related scrap orders"""
        self.ensure_one()

        scrap_orders = self.loading_scrap_orders_ids

        if not scrap_orders:
            raise UserError(_("No scrap orders found for this record."))

        action = {
            'name': _('Scrap Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', scrap_orders.ids)],
        }
        
        if len(scrap_orders) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': scrap_orders.id,
            })
            
        return action
    
    def action_view_return_picking(self):
        """Show the related return picking"""
        self.ensure_one()
        
        if not self.return_picking_id:
            raise UserError(_("No return transfer exists for this record."))
            
        return {
            'name': _('Return Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.return_picking_id.id,
        }

    