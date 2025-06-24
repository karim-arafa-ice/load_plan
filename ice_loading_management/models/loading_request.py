from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree
import logging

_logger = logging.getLogger(__name__)

class LoadingRequest(models.Model):
    _name = 'ice.loading.request'
    _description = 'Ice Loading Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'loading_priority asc, dispatch_time desc'
    
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('car_checking', 'Car Checking'),
        ('ready_for_loading', 'Ready for Loading'),
        # ('loaded', 'Loaded'),
        # ('freezer_loaded', 'Freezer Loaded'),
        # ('freezer_handled', 'Freezer Handled'),      # NEW STATE - After freezer release form signed
        ('ice_handled', 'Ice Loaded'),              # NEW STATE - After loading form signed
        ('plugged', 'Plugged / Ready for Dispatch'),
        ('in_transit', 'In Transit'),
        ('delivering', 'Sesstion Started'),
        ('delivered', 'Delivered'),
        ('returned', 'Returned'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    # Main fields from requirements
    car_id = fields.Many2one('fleet.vehicle', string='Car', required=True, 
                           domain="[('loading_status', '=', 'available')]")
    salesman_id = fields.Many2one('res.users', string='Salesman', required=True)
    special_packing = fields.Char(string='Special Packing')
    route_id = fields.Many2one('crm.team', string='Route (Sales Team)', readonly=True)
    team_leader_id = fields.Many2one('res.users', string='Team Leader', readonly=True)
    dispatch_time = fields.Datetime(string='Dispatch Time', required=True)
    loading_place_id = fields.Many2one('ice.loading.place', string='Loading Place', required=True)
    # Loading priority - editable by sales manager
    loading_priority = fields.Integer(
        related='loading_place_id.loading_priority', 
        string='Loading Priority',
        store=True,
        readonly=False,  # Make it editable for sales managers
        tracking=True,
        help="Priority for this loading request (lower numbers = higher priority)"
    )
    
    # Track car changes
    previous_car_id = fields.Many2one('fleet.vehicle', string='Previous Car', readonly=True)
    car_change_reason = fields.Text(string='Car Change Reason', readonly=True)
    car_changed_by = fields.Many2one('res.users', string='Car Changed By', readonly=True)
    car_change_date = fields.Datetime(string='Car Change Date', readonly=True)
    
    # Industry type for concrete handling
    
    # Products tab
    product_line_ids = fields.One2many('ice.loading.product.line', 'loading_request_id', string='Products')
    
    # Freezers tab
    # freezer_line_ids = fields.One2many('ice.loading.freezer.line', 'loading_request_id', string='Freezers')
    
    # Related records (smart buttons)
    car_check_request_id = fields.Many2one('maintenance.form', string='Car Check Request')
    car_check_request_count = fields.Integer(compute='_compute_request_counts')
    internal_transfer_id = fields.Many2one('stock.picking', string='Internal Transfer')
    picking_count = fields.Integer(compute='_compute_request_counts')
    # freezer_renting_request_ids = fields.One2many('freezer.renting_request', 'loading_request_id', string='Freezer Renting Requests', readonly=True, copy=False)
    # freezer_renting_request_count = fields.Integer(compute='_compute_request_counts')

    signed_loading_form = fields.Binary(string="Signed Loading Form from Salesman")
    signed_loading_form_filename = fields.Char(string="Loading Form Filename")
    loading_form_uploaded_by = fields.Many2one('res.users', string='Loading Form Uploaded By', readonly=True)
    loading_form_upload_date = fields.Datetime(string='Loading Form Upload Date', readonly=True)
    
    # Freezer release form fields
    # freezer_release_form = fields.Binary(string="Signed Freezer Release Form")
    # freezer_release_form_filename = fields.Char(string="Release Form Filename")
    # freezer_release_form_uploaded_by = fields.Many2one('res.users', string='Release Form Uploaded By', readonly=True)
    # freezer_release_form_upload_date = fields.Datetime(string='Release Form Upload Date', readonly=True)
    
    is_concrete_handling = fields.Boolean(string='Concrete Handling', default=False, help="Check if this request involves concrete handling")
    total_weight = fields.Float(compute='_compute_total_weight', string='Total Weight (kg)', store=True)
    # Freezer status tracking
    # has_freezers = fields.Boolean(compute='_compute_has_freezers', string='Has Freezers', store=True)
    # all_freezers_ready = fields.Boolean(compute='_compute_freezer_status', string='All Freezers Ready')
    # freezer_supervisor_decision = fields.Selection([
    #     ('pending', 'Pending Decision'),
    #     ('ready', 'Freezers Ready for Loading'),
    #     ('not_ready', 'Freezers Not Ready - Proceed Without'),
    #     ('cancelled', 'Freezer Loading Cancelled'),
    # ], string='Freezer Supervisor Decision', default='pending', tracking=True,
    #    help="Freezer supervisor's decision on whether freezers are ready for loading")
    # freezer_supervisor_comments = fields.Text(string='Freezer Supervisor Comments',
    #                                         help="Comments from freezer supervisor about the decision")
    # freezer_decision_by = fields.Many2one('res.users', string='Decision Made By', readonly=True)
    # freezer_decision_date = fields.Datetime(string='Decision Date', readonly=True)
    quantity_changes = fields.One2many('ice.loading.quantity.change', 'loading_request_id', string='Quantity Changes')

    @api.onchange('product_line_ids')
    def _onchange_full_load(self):
        """When full load is checked, set quantity to max capacity for each product"""
        for line in self.product_line_ids:
            product_weight = line.product_id.weight or 1.0 
            if line.is_full_load:
                if line.product_type == '4kg':
                    line.quantity = (self.car_id.ice_4kg_capacity / product_weight) if product_weight > 0 else 0.0
                elif line.product_type == '25kg':
                    line.quantity = (self.car_id.ice_25kg_capacity / product_weight) if product_weight > 0 else 0.0
                elif line.product_type == 'cup':
                    line.quantity = (self.car_id.ice_cup_capacity / product_weight) if product_weight > 0 else 0.0
            elif line.quantity < 0:
                raise UserError(_("Quantity cannot be negative. Please enter a valid quantity."))
            elif line.quantity > 0:
                pass
            else:
                line.quantity = 0.0
    # EDIT 2: Add action for quantity change wizard
    def action_change_quantities_wizard(self):
        """Open quantity change wizard for sales supervisor"""
        self.ensure_one()
        
        # Check if user has sales supervisor permissions
        if not self.env.user.has_group('sales_team.group_sale_salesman_all_leads'):
            raise UserError(_('Only Sales Supervisors can change quantities.'))
        
        # Check if state allows quantity changes
        if self.state in ['ice_handled', 'plugged', 'in_transit', 'delivered', 'done', 'cancelled']:
            raise UserError(_('Cannot change quantities after the request has been ice handled.'))
        
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
        
        if not self.env.user.has_group('ice_loading_management.group_loading_worker'):
            raise UserError(_('Only Loading Workers can access this function.'))
        
        if self.state != 'ready_for_loading':
            raise UserError(_('Loading quantities can only be updated when the request is in "Ready for Loading" state.'))
        
        return {
            'name': _('Update Loading Quantities'),
            'type': 'ir.actions.act_window',
            'res_model': 'ice.loading.worker.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ice_loading_management.view_loading_worker_wizard_simple_form').id,
            'target': 'new',
            'context': {
                'default_loading_request_id': self.id,
            }
        }

    # @api.depends('freezer_line_ids')
    # def _compute_has_freezers(self):
    #     for record in self:
    #         record.has_freezers = bool(record.freezer_line_ids)
    
    # @api.depends('freezer_renting_request_ids.status', 'freezer_supervisor_decision')
    # def _compute_freezer_status(self):
    #     for record in self:
    #         if not record.freezer_renting_request_ids:
    #             record.all_freezers_ready = True  # No freezers means ready
    #         elif record.freezer_supervisor_decision == 'not_ready':
    #             record.all_freezers_ready = True  # Supervisor said proceed without freezers
    #         elif record.freezer_supervisor_decision == 'ready':
    #             record.all_freezers_ready = all(
    #                 req.status == 'ready_for_loading' 
    #                 for req in record.freezer_renting_request_ids
    #             )
    #         else:
    #             # Default behavior - check if all freezers are ready
    #             record.all_freezers_ready = all(
    #                 req.status == 'ready_for_loading' 
    #                 for req in record.freezer_renting_request_ids
    #             )
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Make loading_priority field readonly for non-sales managers"""
        result = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        if view_type == 'form':
            # Check if user is sales manager
            is_sales_manager = self.env.user.has_group('sales_team.group_sale_manager')
            
            if not is_sales_manager:
                # Make loading_priority readonly for non-sales managers
                doc = etree.XML(result['arch'])
                for field in doc.xpath("//field[@name='loading_priority']"):
                    field.set('readonly', '1')
                    field.set('help', 'Only Sales Managers can change loading priority')
                result['arch'] = etree.tostring(doc, encoding='unicode')
        
        return result

    def write(self, vals):
        """Track loading priority changes and car changes"""
        for record in self:

            if 'car_id' in vals and vals['car_id'] != record.car_id.id:
                # if record.state in ['ready_for_loading', 'loaded', 'freezer_loaded', 'plugged', 'in_transit', 'delivered']:
                if record.state in ['ready_for_loading', 'ice_handled', 'plugged', 'in_transit', 'delivered']:

                    raise UserError(_(
                        'Cannot change car for loading request "%s" because it is in "%s" status. '
                        'Car changes are only allowed before the "Ready for Loading" stage.'
                    ) % (record.name, dict(record._fields['state'].selection)[record.state]))
            # Track loading priority changes
            if 'loading_priority' in vals and vals['loading_priority'] != record.loading_priority:
                old_priority = record.loading_priority
                new_priority = vals['loading_priority']
                record.message_post(
                    body=_('Loading Priority changed from %s to %s by %s') % (
                        old_priority, new_priority, self.env.user.name
                    ),
                    subject=_('Loading Priority Changed')
                )
            # Track form uploads
            if 'signed_loading_form' in vals and vals['signed_loading_form']:
                vals.update({
                    'loading_form_uploaded_by': self.env.user.id,
                    'loading_form_upload_date': fields.Datetime.now(),
                })
            
            # if 'freezer_release_form' in vals and vals['freezer_release_form']:
            #     vals.update({
            #         'freezer_release_form_uploaded_by': self.env.user.id,
            #         'freezer_release_form_upload_date': fields.Datetime.now(),
            #     })
            
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
    # ========================================
    # FREEZER RELEASE FORM ACTIONS (TASK 4)
    # ========================================
    
    # def action_print_freezer_release_form(self):
    #     """Print freezer release form for salesman signature"""
    #     self.ensure_one()
        
    #     # Check if user has freezer supervisor permissions
    #     if not self.env.user.has_group('ice_loading_management.group_freezer_supervisor'):
    #         raise UserError(_('Only Freezer Supervisors can print release forms.'))
        
    #     if self.state != 'freezer_loaded':
    #         raise UserError(_('Loading request must be in "Freezer Loaded" state to print release form.'))
        
    #     if not self.has_freezers:
    #         raise UserError(_('This loading request has no freezers that require a release form.'))
        
    #     # Return report action
    #     return self.env.ref('ice_loading_management.action_report_freezer_release_form').report_action(self)
    
    # def action_upload_freezer_release_form(self):
    #     """Upload signed freezer release form and update status"""
    #     self.ensure_one()
        
    #     # Check if user has freezer supervisor permissions
    #     if not self.env.user.has_group('ice_loading_management.group_freezer_supervisor'):
    #         raise UserError(_('Only Freezer Supervisors can upload release forms.'))
        
    #     if self.state != 'freezer_loaded':
    #         raise UserError(_('Loading request must be in "Freezer Loaded" state to upload release form.'))
        
    #     if not self.freezer_release_form:
    #         raise UserError(_('Please upload the signed freezer release form first.'))
        
    #     # Update status to freezer_handled
    #     self.write({'state': 'freezer_handled'})
        
    #     # Log the action
    #     self.message_post(
    #         body=_('Signed freezer release form uploaded by %s. Status changed to "Freezer Handled".') % self.env.user.name,
    #         subject=_('Freezer Release Form Uploaded')
    #     )
        
    #     # Notify relevant people
    #     self._notify_form_upload('freezer_release')
        
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': _('Release Form Uploaded'),
    #             'message': _('Signed freezer release form uploaded successfully. Status changed to "Freezer Handled".'),
    #             'type': 'success',
    #             'sticky': False,
    #         }
    #     }
    # ========================================
    # LOADING FORM ACTIONS (TASK 5)
    # ========================================
    
    def action_print_loading_form(self):
        """Print loading form for salesman signature"""
        self.ensure_one()
        
        # Check if user has fleet supervisor or fleet manager permissions
        if not (self.env.user.has_group('ice_loading_management.group_fleet_supervisor') or
                self.env.user.has_group('fleet.fleet_group_manager')):
            raise UserError(_('Only Fleet Supervisors can print loading forms.'))
        
        # Check if we're in the right state for printing
        # valid_states = ['loaded', 'freezer_loaded', 'freezer_handled']
        valid_states = ['plugged']
        if self.state not in valid_states:
            # raise UserError(_('Loading form can only be printed when request is in "Plugged", "Freezer Loaded", or "Freezer Handled" state.'))
            raise UserError(_('Loading form can only be printed when request is in "Plugged" state.'))

        # Return report action
        return self.env.ref('ice_loading_management.action_report_loading_form').report_action(self)
    
    def action_upload_loading_form(self):
        """Upload signed loading form and update status"""
        self.ensure_one()
        
        # Check if user has fleet supervisor permissions
        if not (self.env.user.has_group('ice_loading_management.group_fleet_supervisor') or
                self.env.user.has_group('fleet.fleet_group_manager')):
            raise UserError(_('Only Fleet Supervisors can upload loading forms.'))
        
        # Check valid states for upload
        # valid_states = ['loaded', 'freezer_loaded', 'freezer_handled']
        valid_states = ['plugged']
        if self.state not in valid_states:
            # raise UserError(_('Loading form can only be uploaded when request is in "Plugged", "Freezer Loaded", or "Freezer Handled" state.'))
            raise UserError(_('Loading form can only be uploaded when request is in "Plugged" state.'))
        
        if not self.signed_loading_form:
            raise UserError(_('Please upload the signed loading form first.'))
        
        # Update status to in_transit
        self.write({'state': 'in_transit'})
        
        # Log the action
        self.message_post(
            body=_('Signed loading form uploaded by %s. Status changed to "In Transit".') % self.env.user.name,
            subject=_('Loading Form Uploaded')
        )
        
        # Notify relevant people
        self._notify_form_upload('loading_form')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Loading Form Uploaded'),
                'message': _('Signed loading form uploaded successfully. Status changed to "Ice Handled".'),
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
            sales_supervisor_group = self.env.ref('sales_team.group_sale_salesman_all_leads')
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
        if self.state in ['ready_for_loading', 'ice_handled', 'plugged', 'in_transit', 'delivered']:
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
    
    @api.depends('product_line_ids.computed_weight')
    def _compute_total_weight(self):
        for record in self:
            record.total_weight = sum(record.product_line_ids.mapped('computed_weight'))
    
    def _compute_request_counts(self):
        for request in self:
            request.car_check_request_count = 1 if request.car_check_request_id else 0
            request.picking_count = 1 if request.internal_transfer_id else 0
            # request.freezer_renting_request_count = len(request.freezer_renting_request_ids)
    
    
    def action_confirm_request(self):
        self._create_related_records()
        self._send_creation_notifications()
        

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ice.loading.request') or 'New'
        if 'salesman_id' in vals and vals['salesman_id']:

            team = self.env['crm.team'].search([('member_ids', 'in', [vals['salesman_id']])], limit=1)
            if team:
                vals['route_id'] = team.id
                vals['team_leader_id'] = team.user_id.id
                
        
        request = super().create(vals)
        request._create_default_product_lines()
        
        return request
    
    def _create_default_product_lines(self):
        """Create default product lines for the 3 configured ice products"""
        self.ensure_one()
        
        # Get configured default products from system parameters
        product_4kg_template_id = self.env.company.product_4kg_id
        product_25kg_template_id = self.env.company.product_25kg_id
        product_cup_template_id = self.env.company.product_cup_id
        
        lines_to_create = []
        
        # Create line for 4kg product
        if product_4kg_template_id:
            template = product_4kg_template_id
            if template.exists():
                # Get the first product variant (or create one if none exists)
                product = template.product_variant_ids[0] if template.product_variant_ids else template._create_variant_ids()[0]
                lines_to_create.append({
                    'product_id': product.id,
                    'quantity': 0.0,
                    'loading_request_id': self.id,
                })
        
        # Create line for 25kg product  
        if product_25kg_template_id:
            template = product_25kg_template_id
            if template.exists():
                product = template.product_variant_ids[0] if template.product_variant_ids else template._create_variant_ids()[0]
                lines_to_create.append({
                    'product_id': product.id,
                    'quantity': 0.0,
                    'loading_request_id': self.id,
                })
                
        # Create line for cup product
        if product_cup_template_id:
            template = product_cup_template_id
            if template.exists():
                product = template.product_variant_ids[0] if template.product_variant_ids else template._create_variant_ids()[0]
                lines_to_create.append({
                    'product_id': product.id,
                    'quantity': 0.0,
                    'loading_request_id': self.id,
                })
        
        if lines_to_create:
            self.env['ice.loading.product.line'].create(lines_to_create)
        else:
            raise UserError(_("Please configure the default ice products in Settings > Ice Loading Management."))
        
    def _send_creation_notifications(self):
        """Send notifications to all required departments"""
        groups_to_notify = [
            'customer_management.group_collections_department',
            'account.group_account_manager',
            'maintenance_app.maintenance_workshop_supervisor_group',
            'mrp.group_mrp_manager',
            'stock.group_stock_manager',
            'freezers_management.group_freezer_maintenance_admin',
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
        
        # # 2. Create freezer renting requests
        # self._create_freezer_renting_requests()
        
        # # 3. Create internal transfer
        self._create_internal_transfer()
    
    def _create_car_check_request(self):
        """Create maintenance request for car check"""
        _logger.info("Creating car check request for loading request %s", self.id)
        maintenance_request = self.env['maintenance.form'].create({
            'vehicle_id': self.car_id.id,  
            'is_daily_check': True,  
            'city': self.loading_place_id.name,
            'loading_request_id': self.id,
        })
        _logger.info("Car check request created with ID %s", maintenance_request.id)
        self.state = 'car_checking'
        self.car_check_request_id = maintenance_request.id
        _logger.info("Loading request %s state set to 'car_checking'", self.id)
        self.car_id.loading_status = 'in_use'

    def _create_internal_transfer(self):
        """Create internal transfer for loading request"""
        if not self.product_line_ids:
            raise UserError(_("Please add products to the loading request before creating an internal transfer."))
        
        move_lines = []
        for line in self.product_line_ids:
            if line.quantity > 0:
                move_lines.append((0, 0, {
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'quantity': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.loading_place_id.loading_location_id.id,
                    'location_dest_id': self.salesman_id.accessible_location_id.id,
                }))
        
        if not move_lines:
            raise UserError(_("No products with quantity greater than zero found. Cannot create internal transfer."))
        picking_type_warehouse = self.env['stock.warehouse'].search([('lot_stock_id', '=', self.loading_place_id.loading_location_id.id)], limit=1)
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', picking_type_warehouse.id),
            ('code', '=', 'internal'),
        ], limit=1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.loading_place_id.loading_location_id.id,
            'location_dest_id': self.salesman_id.accessible_location_id.id,
            'move_ids_without_package': move_lines,
            'origin': self.name,
            'transfer_vehicle': self.car_id.id,
            'loading_request_id': self.id,
        })
        
        self.internal_transfer_id = picking.id
        picking.action_confirm()
        picking.action_assign()
    
    # def _create_freezer_renting_requests(self):
    #     """Create freezer renting requests based on the freezer lines"""
    #     if not self.freezer_line_ids:
    #         pass
    #     default_location_id = self.env.company.freezer_location_id.id if self.env.company.freezer_location_id else False
        
    #     for line in self.freezer_line_ids:
            
    #         renting_request = self.env['freezer.renting_request'].create({
    #             'customer_id': line.partner_id.id,
    #             'loading_request_id': self.id,
    #             'category_id': line.category_id.id,
    #             'rental_start_date': self.dispatch_time,
    #             'location_id': int(default_location_id) if default_location_id else False,
    #             'user_id': self.env.user.id,
    #         })
    #         line.renting_request_id = renting_request.id
    #         self.message_post(
    #             body=_('Created freezer renting request %s for customer %s') % (
    #                 renting_request.name, line.partner_id.name
    #             ),
    #             subject=_('Freezer Request Created')
    #         )


    # def action_set_loaded_plugged(self):
    #     self.ensure_one()
    #     if self.internal_transfer_id.state != 'done':
    #         raise UserError(_("The internal transfer must be marked as 'Done' by the storekeeper first."))
    #     self.write({'state': 'plugged'})
    #     self.car_id.write({'loading_status': 'plugged'})

    def action_start_delivery(self):
        self.ensure_one()
        if not self.signed_loading_form:
            raise UserError(_("You must upload the signed loading form from the salesman before start."))
        
        self.write({'state': 'in_transit'})
        # Change car driver
        self.car_id.write({'driver_id': self.salesman_id.partner_id.id})

    def action_view_maintenance_request(self):
        return self._get_action_view(self.car_check_request_id, 'maintenance_app.maintenance_form_action')

    def action_view_picking(self):
        return self._get_action_view(self.internal_transfer_id, 'stock.action_picking_tree_all')

    # def action_view_freezer_renting_requests(self):
    #     # Assuming you have an action for freezer.renting_request
    #     action = self.env['ir.actions.act_window']._for_xml_id('freezers_management.action_freezer_renting_request_list')
    #     action['domain'] = [('id', 'in', self.freezer_renting_request_ids.ids)]
    #     return action
    
    def action_proceed_to_plugged(self):
        """Move to plugged state after all forms are handled"""
        self.ensure_one()
        
        # Check if user has fleet supervisor permissions
        if not (self.env.user.has_group('ice_loading_management.group_fleet_supervisor') or
                self.env.user.has_group('fleet.fleet_group_manager')):
            raise UserError(_('Only Fleet Supervisors can proceed to plugged state.'))
        
        # Check current state
        if self.state != 'ice_handled':
            raise UserError(_('Loading request must be in "Ice Handled" state to proceed to plugged.'))
        
        # Update status and car status
        self.write({'state': 'plugged'})
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
    def _notify_car_ready_for_dispatch(self):
        """Notify about car ready for dispatch"""
        recipients = []
        
        # Notify salesman
        if self.salesman_id:
            recipients.append(self.salesman_id.partner_id.id)
        
        # Notify team leader
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


    # ========================================
    # EXISTING METHODS (keeping for completeness)
    # ========================================
    
    # def action_set_freezer_loaded(self):
    #     """Mark all freezers as loaded and update state"""
    #     self.ensure_one()
        
    #     if self.state != 'loaded':
    #         raise UserError(_('Loading request must be in "Loaded" state to mark freezers as loaded.'))
        
    #     if not self.has_freezers:
    #         raise UserError(_('This loading request has no freezers to load.'))
        
    #     # Check freezer supervisor decision
    #     if self.freezer_supervisor_decision == 'not_ready':
    #         # Supervisor said freezers not ready - proceed without loading freezers
    #         self.write({'state': 'ice_handled'})  # Skip freezer steps
            
    #         self.message_post(
    #             body=_('Freezer supervisor indicated freezers are not ready. Skipping freezer handling and proceeding to ice handling by %s.<br/>Comments: %s') % (
    #                 self.env.user.name,
    #                 self.freezer_supervisor_comments or 'No comments'
    #             ),
    #             subject=_('Skipped Freezer Handling')
    #         )
    #         return
        
    #     if not self.all_freezers_ready:
    #         raise UserError(_('Not all freezers are ready for loading. Please check freezer renting requests or ask freezer supervisor to make a decision.'))
        
    #     # Update freezer renting requests to loaded status (only if freezers are actually ready)
    #     if self.freezer_supervisor_decision == 'ready':
    #         for freezer_request in self.freezer_renting_request_ids:
    #             if freezer_request.status == 'ready_for_loading':
    #                 freezer_request.action_set_loaded()
        
    #     # Update loading request state
    #     self.write({'state': 'freezer_loaded'})
        
    #     # Log the action
    #     self.message_post(
    #         body=_('All freezers marked as loaded by %s') % self.env.user.name,
    #         subject=_('Freezers Loaded')
        # )

    # def action_skip_freezer_loading(self):
    #     """Skip freezer loading if no freezers or go directly to ice_handled"""
    #     self.ensure_one()
        
    #     if self.state != 'loaded':
    #         raise UserError(_('Loading request must be in "Loaded" state.'))
        
    #     if self.has_freezers and self.freezer_supervisor_decision not in ['not_ready', 'cancelled']:
    #         raise UserError(_('Cannot skip freezer loading when freezers are present. Use "Set Freezer Loaded" instead or ask freezer supervisor to make a decision.'))
        
    #     # Go directly to ice_handled state (skip freezer handling completely)
    #     self.write({'state': 'ice_handled'})
        
    #     reason = "No freezers present"
    #     if self.freezer_supervisor_decision == 'not_ready':
    #         reason = "Freezer supervisor indicated freezers not ready"
    #     elif self.freezer_supervisor_decision == 'cancelled':
    #         reason = "Freezer loading cancelled by supervisor"
        
    #     self.message_post(
    #         body=_('Skipped freezer handling (%s) and moved to ice handled state by %s') % (reason, self.env.user.name),
    #         subject=_('Freezer Handling Skipped')
    #     )
    # def action_freezer_supervisor_ready(self):
    #     """Freezer supervisor confirms freezers are ready for loading"""
    #     self.ensure_one()
        
    #     # Check if user has freezer supervisor permissions
    #     if not self.env.user.has_group('ice_loading_management.group_freezer_supervisor'):
    #         raise UserError(_('Only Freezer Supervisors can make this decision.'))
        
    #     if not self.has_freezers:
    #         raise UserError(_('This loading request has no freezers.'))
        
    #     self.write({
    #         'freezer_supervisor_decision': 'ready',
    #         'freezer_decision_by': self.env.user.id,
    #         'freezer_decision_date': fields.Datetime.now(),
    #     })
        
    #     self.message_post(
    #         body=_('Freezer supervisor %s confirmed freezers are ready for loading.<br/>Comments: %s') % (
    #             self.env.user.name,
    #             self.freezer_supervisor_comments or 'No comments'
    #         ),
    #         subject=_('Freezers Confirmed Ready')
    #     )
        
    #     # Notify relevant people
    #     self._notify_freezer_decision('ready')
    # def action_freezer_supervisor_not_ready(self):
    #     """Freezer supervisor indicates freezers are not ready - proceed without loading"""
    #     self.ensure_one()
        
    #     # Check if user has freezer supervisor permissions
    #     if not self.env.user.has_group('ice_loading_management.group_freezer_supervisor'):
    #         raise UserError(_('Only Freezer Supervisors can make this decision.'))
        
    #     if not self.has_freezers:
    #         raise UserError(_('This loading request has no freezers.'))
        
    #     self.write({
    #         'freezer_supervisor_decision': 'not_ready',
    #         'freezer_decision_by': self.env.user.id,
    #         'freezer_decision_date': fields.Datetime.now(),
    #     })
        
    #     self.message_post(
    #         body=_('Freezer supervisor %s indicated freezers are NOT ready. Loading can proceed without freezers.<br/>Comments: %s') % (
    #             self.env.user.name,
    #             self.freezer_supervisor_comments or 'No comments'
    #         ),
    #         subject=_('Freezers Not Ready - Proceed Without')
    #     )
        
    #     # Notify relevant people
    #     self._notify_freezer_decision('not_ready')
    # def action_freezer_supervisor_cancel(self):
    #     """Freezer supervisor cancels freezer loading entirely"""
    #     self.ensure_one()
        
    #     # Check if user has freezer supervisor permissions
    #     if not self.env.user.has_group('ice_loading_management.group_freezer_supervisor'):
    #         raise UserError(_('Only Freezer Supervisors can make this decision.'))
        
    #     if not self.has_freezers:
    #         raise UserError(_('This loading request has no freezers.'))
        
    #     self.write({
    #         'freezer_supervisor_decision': 'cancelled',
    #         'freezer_decision_by': self.env.user.id,
    #         'freezer_decision_date': fields.Datetime.now(),
    #     })
        
    #     self.message_post(
    #         body=_('Freezer supervisor %s cancelled freezer loading for this request.<br/>Comments: %s') % (
    #             self.env.user.name,
    #             self.freezer_supervisor_comments or 'No comments'
    #         ),
    #         subject=_('Freezer Loading Cancelled')
    #     )
        
    #     # Cancel related freezer renting requests
    #     for freezer_request in self.freezer_renting_request_ids:
    #         if freezer_request.status not in ['delivered', 'completed']:
    #             freezer_request.action_cancel()
        
    #     # Notify relevant people
    #     self._notify_freezer_decision('cancelled')
    # def _notify_freezer_decision(self, decision):
    #     """Notify relevant people about freezer supervisor decision"""
    #     recipients = []
        
    #     # Notify salesman
    #     if self.salesman_id:
    #         recipients.append(self.salesman_id.partner_id.id)
        
    #     # Notify team leader
    #     if self.team_leader_id:
    #         recipients.append(self.team_leader_id.partner_id.id)
        
    #     # Notify sales supervisor
    #     try:
    #         sales_supervisor_group = self.env.ref('sales_team.group_sale_salesman_all_leads')
    #         for user in sales_supervisor_group.users:
    #             recipients.append(user.partner_id.id)
    #     except:
    #         pass
        
    #     # Notify storekeeper/warehouse
    #     try:
    #         storekeeper_group = self.env.ref('stock.group_stock_manager')
    #         for user in storekeeper_group.users:
    #             recipients.append(user.partner_id.id)
    #     except:
    #         pass
        
    #     if recipients:
    #         decision_messages = {
    #             'ready': 'Freezers are ready for loading',
    #             'not_ready': 'Freezers are NOT ready - proceed without freezer loading',
    #             'cancelled': 'Freezer loading has been cancelled'
    #         }
            
    #         subject = _('Freezer Decision for Loading Request %s') % self.name
    #         message = _("""
    #         <p>Freezer supervisor <strong>%s</strong> has made a decision for loading request <strong>%s</strong>:</p>
    #         <p><strong>Decision:</strong> %s</p>
    #         <p><strong>Comments:</strong> %s</p>
    #         <p><strong>Dispatch Time:</strong> %s</p>
    #         """) % (
    #             self.env.user.name,
    #             self.name,
    #             decision_messages.get(decision, decision),
    #             self.freezer_supervisor_comments or 'No comments',
    #             self.dispatch_time.strftime('%Y-%m-%d %H:%M') if self.dispatch_time else 'Not set'
    #         )
            
    #         self.message_notify(
    #             partner_ids=list(set(recipients)),
    #             subject=subject,
    #             body=message,
    #         )

class LoadingQuantityChange(models.Model):
    _name = 'ice.loading.quantity.change'
    _description = 'Loading Request Quantity Change History'
    _order = 'change_date desc'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    old_quantity = fields.Float(string='Old Quantity', required=True)
    new_quantity = fields.Float(string='New Quantity', required=True)
    change_reason = fields.Text(string='Reason for Change', required=True)
    changed_by = fields.Many2one('res.users', string='Changed By', required=True, default=lambda self: self.env.user)
    change_date = fields.Datetime(string='Change Date', required=True, default=fields.Datetime.now)
    


class DriverSession(models.Model):
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
        self.session_end = fields.Datetime.now()
        self.is_active = False
        self.state = 'closed'
        # Create return car request
        self._create_return_request()
    
    def _create_return_request(self):
        pass
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')
    
    def button_validate(self):
        # Storekeeper validation check
        if self.loading_request_id and self.loading_request_id.state not in ['ready_for_loading']:
            raise UserError(_("You cannot validate the transfer. The car for request '%s' is not yet ready for loading.", self.loading_request_id.name))
        
        res = super(StockPicking, self).button_validate()
        
        if self.loading_request_id:
            self.loading_request_id.write({'state': 'ice_handled'})
        
        return res
    
class FreezerRentingRequest(models.Model):
    _inherit= 'freezer.renting_request'

    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')

    # def action_ready_for_loading(self):
    #     """Mark freezer as ready for loading (from ready_for_delivery)"""
    #     self.ensure_one()
    #     if self.status != 'ready_for_delivery':
    #         raise UserError(_('Freezer must be in "Ready for Delivery" state to mark as ready for loading.'))
        
    #     self.write({'status': 'ready_for_loading'})
    #     self.message_post(
    #         body=_('Freezer marked as ready for loading by %s') % self.env.user.name,
    #         subject=_('Ready for Loading')
    #     )
        
    #     # Notify loading request if linked
    #     if self.loading_request_id:
    #         self.loading_request_id.message_post(
    #             body=_('Freezer %s (%s) is now ready for loading') % (
    #                 self.asset_id.name if self.asset_id else 'TBD',
    #                 self.name
    #             ),
    #             subject=_('Freezer Ready for Loading')
    #         )
    # def action_set_loaded(self):
    #     """Mark freezer as loaded onto vehicle"""
    #     self.ensure_one()
    #     if self.status != 'ready_for_loading':
    #         raise UserError(_('Freezer must be in "Ready for Loading" state to mark as loaded.'))
        
    #     self.write({'status': 'loaded'})
    #     self.message_post(
    #         body=_('Freezer loaded onto vehicle by %s') % self.env.user.name,
    #         subject=_('Freezer Loaded')
    #     )
        
    #     # Update asset location to be with the car/driver
    #     if self.asset_id and self.loading_request_id and self.loading_request_id.salesman_id:
    #         if self.loading_request_id.salesman_id.accessible_location_id:
    #             self.asset_id.location_id = self.loading_request_id.salesman_id.accessible_location_id
    #             self.asset_id.responsible_user_id = self.loading_request_id.salesman_id.id

class MaintenanceForm(models.Model):
    _inherit = "maintenance.form"
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', readonly=True, copy=False, ondelete='set null')

    def action_stop(self):
        """Override to set loading request state to 'car_checking' when stopping the maintenance form."""
        res = super(MaintenanceForm, self).action_stop()
        if self.loading_request_id:
            self.loading_request_id.write({'state': 'ready_for_loading'})
            self.loading_request_id.car_id.loading_status = 'ready_for_loading'
        return res

    

# class LoadingFreezerLine(models.Model):
#     _name = 'ice.loading.freezer.line'
#     _description = 'Loading Request Freezer Line'
    
#     loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
#     category_id = fields.Many2one('product.category', string='Freezer Category',
#                                   domain="[('is_freezer_category', '=', True)]",
#                                   required=True,
#                                   tracking=True)
#     freezer_id = fields.Many2one('account.asset', string='Freezer',
#                                domain="[('rental_availability', '=', 'available'), ('state', '=', 'open')]")
#     partner_id = fields.Many2one('res.partner', string='Customer', required=True,
#                                domain="[('customer_rank', '>', 0)]")
#     renting_request_id = fields.Many2one('freezer.renting_request', string='Freezer Renting Request',
#                                          readonly=True, copy=False, ondelete='set null')


# access_ice_loading_freezer_line_user,ice.loading.freezer.line.user,model_ice_loading_freezer_line,base.group_user,1,1,1,1
