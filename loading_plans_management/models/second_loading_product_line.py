from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class LoadingProductLine(models.Model):
    _name = 'second.ice.loading.product.line'
    _description = 'Loading Request Product Line'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Needed Quantity to load', default=0.0, readonly=True)
    scrap_quantity = fields.Float(string='Scrap Quantity', default=0.0, readonly=True)
    requested_quantity = fields.Float(string='Requested Quantity', readonly=True)
    current_quantity = fields.Float(string='Current Quantity after scrap', readonly=True)
    quantity_in_pcs = fields.Float(compute='_compute_quantity_in_pcs', string='Quantity in Pieces', store=True)
    computed_weight = fields.Float(compute='_compute_weight', string='Weight (kg)', store=True)
    
    # Product type taken from the product itself
    product_type = fields.Selection(
        related='product_id.ice_product_type',
        string='Product Type', 
        readonly=True,
        store=True
    )
    
    # Full load option
    max_capacity_for_product = fields.Float(
        compute='_compute_max_capacity_for_product',
        string='Max Capacity (kg)'
    )

    @api.depends('quantity', 'product_id.pcs_per_bag', 'product_id.pcs_per_basket', 'product_id.ice_product_type','product_id.weight','product_id.pcs_for_concrete')
    def _compute_quantity_in_pcs(self):
        """NEW: Compute the total quantity in the base unit (Pieces)."""
        for line in self:
            if not line.product_id:
                line.quantity_in_pcs = 0.0
                continue

            if line.product_id.ice_product_type == '4kg':
                line.quantity_in_pcs = line.quantity * (line.product_id.pcs_per_bag or 8)
            elif line.product_id.ice_product_type == 'cup':
                line.quantity_in_pcs = line.quantity * (line.product_id.pcs_per_basket or 24)
            else: # Default to Pieces
                line.quantity_in_pcs = line.quantity
    
    @api.depends('quantity', 'product_id.weight','quantity_in_pcs')
    def _compute_weight(self):
        for line in self:
            line.computed_weight = line.quantity_in_pcs * line.product_id.weight if line.product_id.weight else 0.0
    
    @api.depends('loading_request_id.car_id', 'product_type','product_id.weight','product_id.pcs_per_bag','product_id.pcs_per_basket','product_id.pcs_for_concrete')
    def _compute_max_capacity_for_product(self):
        for line in self:
            
            if line.loading_request_id.car_id and line.product_type:
                product = self.env['product.template'].search([('ice_product_type', '=', line.product_type)], limit=1)
                car = line.loading_request_id.car_id
                if line.product_type == '4kg':
                    line.max_capacity_for_product = car.ice_4kg_capacity * product.weight * product.pcs_per_bag if product.weight else car.ice_4kg_capacity
                elif line.product_type == '25kg':
                    line.max_capacity_for_product = car.ice_25kg_capacity * product.weight * product.pcs_for_concrete if product.weight else car.ice_25kg_capacity
                elif line.product_type == 'cup':
                    line.max_capacity_for_product = car.ice_cup_capacity * product.weight * product.pcs_per_basket if product.weight else car.ice_cup_capacity
                else:
                    line.max_capacity_for_product = 0.0
            else:
                line.max_capacity_for_product = 0.0
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, validate it has ice product type"""
        if self.product_id:
            if not self.product_id.ice_product_type:
                return {
                    'warning': {
                        'title': _('Warning'),
                        'message': _('The selected product does not have an ice product type configured. Please configure the ice product type in the product form.')
                    }
            }             
    
    
    
 # EDIT 4: Enhanced capacity validation with specific messages
    @api.constrains('computed_weight', 'quantity', 'product_id')
    def _check_weight_capacity(self):
        for line in self:
            if not line.loading_request_id.car_id:
                continue
            
            # Check if product has ice product type configured
            product = self.env['product.template'].search([('ice_product_type', '=', line.product_type)], limit=1)
            if line.product_id and not product.ice_product_type:
                raise ValidationError(_(
                    'Product "%s" does not have an ice product type configured. Please set the ice product type in the product form.'
                ) % line.product_id.name)
                
            car = line.loading_request_id.car_id
            
            # Check individual product capacity based on product type
            if line.product_type == '4kg' and line.computed_weight > car.ice_4kg_capacity * product.pcs_per_bag * product.weight if product.weight else car.ice_4kg_capacity:
                ice_4kg_capacity = car.ice_4kg_capacity * product.pcs_per_bag * product.weight if product.weight else car.ice_4kg_capacity
                raise ValidationError(_(
                    '4kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, ice_4kg_capacity, car.license_plate or car.name))

            elif line.product_type == '25kg' and line.computed_weight > car.ice_25kg_capacity * product.pcs_for_concrete * product.weight if product.weight else car.ice_25kg_capacity:
                ice_25kg_capacity = car.ice_25kg_capacity * product.pcs_for_concrete * product.weight if product.weight else car.ice_25kg_capacity
                raise ValidationError(_(
                    '25kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, ice_25kg_capacity, car.license_plate or car.name))

            elif line.product_type == 'cup' and line.computed_weight > car.ice_cup_capacity * product.pcs_per_basket * product.weight if product.weight else car.ice_cup_capacity:
                ice_cup_capacity = car.ice_cup_capacity * product.pcs_per_basket * product.weight if product.weight else car.ice_cup_capacity
                raise ValidationError(_(
                    'Ice Cup weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, ice_cup_capacity, car.license_plate or car.name))
            
            # Check total weight doesn't exceed car total capacity
            total_weight = sum(line.loading_request_id.second_product_line_ids.mapped('computed_weight'))
            if total_weight > car.total_weight_capacity:
                raise ValidationError(_(
                    'Total weight (%.2f kg) exceeds car total capacity (%.2f kg) for car %s'
                ) % (total_weight, car.total_weight_capacity, car.license_plate or car.name))
                
    # EDIT 5: Add onchange for quantity to check capacity in real-time
    @api.onchange('quantity', 'product_id', 'loading_request_id.car_id')
    def _onchange_quantity(self):
        """Check capacity when quantity changes"""
        if self.quantity and self.product_id and self.loading_request_id.car_id:
            car = self.loading_request_id.car_id
            product = self.env['product.template'].search([('ice_product_type', '=', self.product_type)], limit=1)
            # product_weight = self.product_id.weight or 0.0
            computed_weight = self.quantity_in_pcs * product.weight if product.weight else 0.0
            
            # Check individual capacity
            warning_message = None
            if self.product_type == '4kg' and computed_weight > car.ice_4kg_capacity * product.pcs_per_bag * product.weight if product.weight else car.ice_4kg_capacity:
                warning_message = _('4kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_4kg_capacity * product.pcs_per_bag * product.weight if product.weight else car.ice_4kg_capacity)
            elif self.product_type == '25kg' and computed_weight > car.ice_25kg_capacity * product.pcs_for_concrete * product.weight if product.weight else car.ice_25kg_capacity:
                warning_message = _('25kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_25kg_capacity * product.pcs_for_concrete * product.weight if product.weight else car.ice_25kg_capacity)
            elif self.product_type == 'cup' and computed_weight > car.ice_cup_capacity * product.pcs_per_basket * product.weight if product.weight else car.ice_cup_capacity:
                warning_message = _('Ice Cup weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_cup_capacity * product.pcs_per_basket * product.weight if product.weight else car.ice_cup_capacity)

            # Check total capacity
            total_weight = sum(self.loading_request_id.second_product_line_ids.mapped('computed_weight')) - self.computed_weight + computed_weight
            if total_weight > car.total_weight_capacity:
                warning_message = _('Total weight (%.2f kg) exceeds car total capacity (%.2f kg)') % (
                    total_weight, car.total_weight_capacity)
            
            if warning_message:
                return {
                    'warning': {
                        'title': _('Capacity Warning'),
                        'message': warning_message
                    }
                }