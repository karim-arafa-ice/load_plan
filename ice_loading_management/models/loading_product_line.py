from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class LoadingProductLine(models.Model):
    _name = 'ice.loading.product.line'
    _description = 'Loading Request Product Line'
    
    loading_request_id = fields.Many2one('ice.loading.request', string='Loading Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', default=0.0)
    computed_weight = fields.Float(compute='_compute_weight', string='Weight (kg)', store=True)
    
    # Product type taken from the product itself
    product_type = fields.Selection(
        related='product_id.ice_product_type',
        string='Product Type', 
        readonly=True,
        store=True
    )
    
    # Full load option
    is_full_load = fields.Boolean(string='Full Load', default=False)
    max_capacity_for_product = fields.Float(
        compute='_compute_max_capacity_for_product',
        string='Max Capacity (kg)'
    )
    
    @api.depends('quantity', 'product_id.weight')
    def _compute_weight(self):
        for line in self:
            line.computed_weight = line.quantity * line.product_id.weight if line.product_id.weight else 0.0
    
    @api.depends('loading_request_id.car_id', 'product_type')
    def _compute_max_capacity_for_product(self):
        for line in self:
            
            if line.loading_request_id.car_id and line.product_type:
                product = self.env['product.template'].search([('ice_product_type', '=', line.product_type)], limit=1)
                car = line.loading_request_id.car_id
                if line.product_type == '4kg':
                    line.max_capacity_for_product = car.ice_4kg_capacity * product.weight if product.weight else car.ice_4kg_capacity
                elif line.product_type == '25kg':
                    line.max_capacity_for_product = car.ice_25kg_capacity * product.weight if product.weight else car.ice_25kg_capacity
                elif line.product_type == 'cup':
                    line.max_capacity_for_product = car.ice_cup_capacity * product.weight if product.weight else car.ice_cup_capacity
                else:
                    line.max_capacity_for_product = 0.0
            else:
                line.max_capacity_for_product = 0.0
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, validate it has ice product type"""
        if self.product_id and not self.product_id.ice_product_type:
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _('The selected product does not have an ice product type configured. Please configure the ice product type in the product form.')
                }
            }
    
    @api.onchange('is_full_load')
    def _onchange_full_load(self):
        print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        _logger.info("Full load dependency triggered for loading product line %s", self.id)
        """When full load is checked, set quantity to maximum capacity"""
        if self.is_full_load and self.product_id and self.loading_request_id.car_id:
            car = self.loading_request_id.car_id
            # product_weight = self.product_id.weight or 1.0  # Avoid division by zero
            
            if self.product_type == '4kg':
                max_capacity = car.ice_4kg_capacity
            elif self.product_type == '25kg':
                max_capacity = car.ice_25kg_capacity
            elif self.product_type == 'cup':
                max_capacity = car.ice_cup_capacity
            else:
                max_capacity = 0.0
            
            # Calculate maximum quantity based on weight capacity
            # max_quantity = max_capacity / product_weight if product_weight > 0 else 0.0
            self.quantity = max_capacity
    
 # EDIT 4: Enhanced capacity validation with specific messages
    @api.constrains('computed_weight', 'quantity', 'product_id', 'is_full_load')
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
            if line.product_type == '4kg' and line.computed_weight > car.ice_4kg_capacity * product.weight if product.weight else car.ice_4kg_capacity:
                raise ValidationError(_(
                    '4kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, car.ice_4kg_capacity, car.license_plate or car.name))

            elif line.product_type == '25kg' and line.computed_weight > car.ice_25kg_capacity * product.weight if product.weight else car.ice_25kg_capacity:
                raise ValidationError(_(
                    '25kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, car.ice_25kg_capacity, car.license_plate or car.name))

            elif line.product_type == 'cup' and line.computed_weight > car.ice_cup_capacity * product.weight if product.weight else car.ice_cup_capacity:
                raise ValidationError(_(
                    'Ice Cup weight (%.2f kg) exceeds car capacity (%.2f kg) for car %s'
                ) % (line.computed_weight, car.ice_cup_capacity, car.license_plate or car.name))
            
            # Check total weight doesn't exceed car total capacity
            total_weight = sum(line.loading_request_id.product_line_ids.mapped('computed_weight'))
            if total_weight > car.total_weight_capacity:
                raise ValidationError(_(
                    'Total weight (%.2f kg) exceeds car total capacity (%.2f kg) for car %s'
                ) % (total_weight, car.total_weight_capacity, car.license_plate or car.name))
                
    # EDIT 5: Add onchange for quantity to check capacity in real-time
    @api.onchange('quantity')
    def _onchange_quantity(self):
        """Check capacity when quantity changes"""
        if self.quantity and self.product_id and self.loading_request_id.car_id:
            car = self.loading_request_id.car_id
            product = self.env['product.template'].search([('ice_product_type', '=', self.product_type)], limit=1)
            # product_weight = self.product_id.weight or 0.0
            computed_weight = self.quantity * product.weight if product.weight else 0.0
            

            # Check individual capacity
            warning_message = None
            if self.product_type == '4kg' and computed_weight > car.ice_4kg_capacity * product.weight if product.weight else car.ice_4kg_capacity:
                warning_message = _('4kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_4kg_capacity * product.weight)
            elif self.product_type == '25kg' and computed_weight > car.ice_25kg_capacity * product.weight if product.weight else car.ice_25kg_capacity:
                warning_message = _('25kg Ice weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_25kg_capacity * product.weight)
            elif self.product_type == 'cup' and computed_weight > car.ice_cup_capacity * product.weight if product.weight else car.ice_cup_capacity:
                warning_message = _('Ice Cup weight (%.2f kg) exceeds car capacity (%.2f kg)') % (
                    computed_weight, car.ice_cup_capacity * product.weight if product.weight else car.ice_cup_capacity)

            # Check total capacity
            total_weight = sum(self.loading_request_id.product_line_ids.mapped('computed_weight')) - self.computed_weight + computed_weight
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