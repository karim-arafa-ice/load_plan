# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Gayathri V (odoo@cybrosys.com)
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
{
    'name': 'e-Invoicing For Saudi | Saudi VAT Invoice | Saudi Electronic Invoice | Saudi Zatca',
    'version': '17.0.1.1.0',
    'category': 'Accounting',
    'summary': "Module for e-Invoicing For Saudi | Saudi VAT Invoice | Saudi "
               "Electronic Invoice | Saudi Zatca",
    'description': "e-Invoicing For Saudi,Saudi VAT Invoice,Saudi Electronic "
                   "Invoice,Saudi Zatca,Zatca,Saudi,e-Invoicing",
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': ['account','account_payment','l10n_gcc_invoice',
        'l10n_sa','l10n_sa_edi','custom_partner_po_required'],
    'data': [
        # 'views/res_config_settings_views.xml',
        'views/res_partner.xml',
        'views/account_move_views.xml',
        'report/account_move_reports.xml',
        'report/arabic_english_invoice.xml',
        'report/vat_invoice_report_templates.xml',
        # 'report/vat_invoice_report_templates2.xml'
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
