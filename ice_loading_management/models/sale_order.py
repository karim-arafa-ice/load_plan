from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_create_delivery(self, quantity_to_deliver):
        self.ensure_one()
        
        picking_type_id = self.warehouse_id.out_type_id.id
        picking_vals = {
            'partner_id': self.partner_shipping_id.id,
            'picking_type_id': picking_type_id,
            'location_id': self.warehouse_id.lot_stock_id.id,
            'location_dest_id': self.partner_shipping_id.property_stock_customer.id,
            'origin': self.name,
            'sale_id': self.id,
        }
        picking = self.env['stock.picking'].create(picking_vals)

        remaining_qty_to_assign = quantity_to_deliver
        for line in self.order_line.filtered(lambda l: l.product_id.type == 'product' and l.product_uom_qty - l.qty_delivered > 0):
            if remaining_qty_to_assign <= 0:
                break
            
            qty_on_line = line.product_uom_qty - line.qty_delivered
            qty_to_move = min(remaining_qty_to_assign, qty_on_line)
            
            self.env['stock.move'].create({
                'name': line.name,
                'product_id': line.product_id.id,
                'product_uom_qty': qty_to_move,
                'product_uom': line.product_uom.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'sale_line_id': line.id,
            })
            remaining_qty_to_assign -= qty_to_move
            
        picking.action_confirm()
        picking.action_assign()
        
        return picking