# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Gayathri V(odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.

###############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from collections import defaultdict



class AccountMove(models.Model):
    """Class for adding new button and a page in account move"""
    _inherit = 'account.move'

    po_number = fields.Char('PO Number')

    # def _get_report_base_filename(self):
    #     # This method is called by the report action.
    #     # We check if the report being printed is our specific VAT invoice.
    #     if self.env.context.get('report_name') == 'advanced_vat_invoice.vat_template':
    #         self.ensure_one()
    #         # If it is, we return our custom filename.
    #         return f"{self.name.replace('/', '-')}-{self.invoice_date}"
        
    #     # For all other reports on account.move, we use the default Odoo behavior.
    #     return super()._get_report_base_filename()
    
    def _get_report_base_filename(self):
        # --- START OF TEST CODE ---
        # This will cause a popup on the screen if this code runs.
        # raise UserError('SUCCESS: My custom filename method was called!')
        # --- END OF TEST CODE ---

        # Original logic (for now, it is unreachable)
         # We will use this later
        # if self.env.context.get('report_name') == 'advanced_vat_invoice.vat_template':
        #     self.ensure_one()
        return f"{self.invoice_date}"

        # return super()._get_report_base_filename()


    def get_product_summary(self):
        """
        Group invoice lines by product and calculate totals
        Returns a list of dictionaries with product details and totals
        """
        self.ensure_one()
        if self.move_type not in ('out_invoice', 'out_refund'):
            return []
            
        product_summary = defaultdict(lambda: {
            'name': '',
            'price_unit': 0.0,
            'quantity': 0.0,
            'price_subtotal': 0.0,
            'price_tax': 0.0,
            'price_total': 0.0,
        })
        
        for line in self.invoice_line_ids:
            if not line.product_id:
                continue
                
            product_id = line.product_id.id
            if product_summary[product_id]['name'] == '':
                product_summary[product_id]['name'] = line.product_id.product_name_in_report
            
            # We're calculating weighted average price for the price_unit
            current_qty = product_summary[product_id]['quantity']
            new_qty = current_qty + line.quantity
            
            if new_qty > 0:  # Avoid division by zero
                # Calculate weighted average price
                product_summary[product_id]['price_unit'] = (
                    (product_summary[product_id]['price_unit'] * current_qty) + 
                    (line.price_unit * line.quantity)
                ) / new_qty
            
            product_summary[product_id]['quantity'] += line.quantity
            product_summary[product_id]['price_subtotal'] += line.price_subtotal
            product_summary[product_id]['price_tax'] += (line.price_total - line.price_subtotal)
            product_summary[product_id]['price_total'] += line.price_total
            
        # Convert to list and round values
        result = []
        for product_data in product_summary.values():
            result.append({
                'name': product_data['name'],
                'price_unit': round(product_data['price_unit'], 2),
                'quantity': round(product_data['quantity'], 2),
                'price_subtotal': round(product_data['price_subtotal'], 2),
                'price_tax': round(product_data['price_tax'], 2),
                'price_total': round(product_data['price_total'], 2),
            })
            
        return result
        
    def get_total_summary(self):
        """
        Return the invoice totals
        """
        self.ensure_one()
        
        return {
            'name': 'TOTAL',
            'price_unit': 0.0,  # Not relevant for the total row
            'quantity': sum(line.quantity for line in self.invoice_line_ids),
            'price_subtotal': self.amount_untaxed,
            'price_tax': self.amount_tax,
            'price_total': self.amount_total,
        }
    
    def get_sorted_invoice_lines(self):
        """
        Return invoice lines sorted by effective_date (delivery date) from earliest to latest
        """
        self.ensure_one()
        
        # Create a list of lines with their effective dates
        lines_with_dates = []
        for line in self.invoice_line_ids:
            # Get the effective date from the related sale order
            effective_date = None
            if line.sale_line_ids and line.sale_line_ids[0].order_id:
                effective_date = line.sale_line_ids[0].order_id.effective_date
            
            lines_with_dates.append({
                'line': line,
                'effective_date': effective_date or fields.Date.from_string('2099-12-31')  # Default date for sorting if no date
            })
        
        # Sort the list by effective_date
        sorted_lines = sorted(lines_with_dates, key=lambda x: x['effective_date'])
        
        # Return only the line objects in sorted order
        return [item['line'] for item in sorted_lines]