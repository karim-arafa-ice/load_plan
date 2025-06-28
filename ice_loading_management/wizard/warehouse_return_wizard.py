from odoo import models, fields, api, _

class WarehouseReturnWizard(models.TransientModel):
    _name = 'ice.warehouse.return.wizard'
    _description = 'Warehouse Return Wizard'

    return_request_id = fields.Many2one('ice.return.request', string='Return Request', required=True)
    line_ids = fields.One2many('ice.warehouse.return.wizard.line', 'wizard_id', string='Return Lines')

    @api.model
    def default_get(self, fields_list):
        """
        Aggregates product lines from all loading requests associated with the
        parent return request to populate the wizard.
        """
        res = super().default_get(fields_list)
        if self.env.context.get('default_return_request_id'):
            return_request = self.env['ice.return.request'].browse(self.env.context.get('default_return_request_id'))
            
            product_map = {}  # To aggregate quantities: {product_id: loaded_quantity}

            for loading_req in return_request.loading_request_ids:
                for line in loading_req.product_line_ids:
                    # Use a dictionary to sum up quantities per product
                    product_map.setdefault(line.product_id, 0.0)
                    product_map[line.product_id] += line.quantity

            lines = []
            for product, loaded_qty in product_map.items():
                lines.append((0, 0, {
                    'product_id': product.id,
                    'loaded_quantity': loaded_qty,
                    # current_quantity would ideally come from a real-time inventory report
                    # of the salesman's van location. Defaulting to loaded_qty for now.
                    'current_quantity': loaded_qty,
                    'returned_quantity': 0,
                    'scrap_quantity': 0,
                }))
            
            res['line_ids'] = lines
        return res

    def action_process_return(self):
        """
        This action will create the necessary stock moves for returned and scrapped goods.
        """
        self.ensure_one()
        # Logic to create an internal transfer for returned goods and a scrap order for scrapped goods
        # would be implemented here, using the data from self.line_ids.
        
        # After processing, move the return request to the next stage
        self.return_request_id.state = 'car_check'
        self.return_request_id.message_post(body=_("Warehouse return processed by %s.") % self.env.user.name)
        return {'type': 'ir.actions.act_window_close'}


class WarehouseReturnWizardLine(models.TransientModel):
    _name = 'ice.warehouse.return.wizard.line'
    _description = 'Warehouse Return Wizard Line'

    wizard_id = fields.Many2one('ice.warehouse.return.wizard', string='Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True)
    loaded_quantity = fields.Float(string='Total Loaded Qty', readonly=True)
    current_quantity = fields.Float(string='Current Qty', help="Quantity currently in the van")
    returned_quantity = fields.Float(string='Returned Qty')
    scrap_quantity = fields.Float(string='Scrap Qty')