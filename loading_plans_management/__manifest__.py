
# Ice Loading Management Module for Odoo 17 Enterprise
# Module Structure and Key Files

{
    'name': 'Loading Plans Management',
    'summary': 'Complete ice manufacturing loading and delivery management system',
    'author': 'karim arafa',
    'depends': [
        'base',
        'fleet',
        'stock',
        'sale',
        'crm',
        'customer_management',
        'mail',
        'maintenance_app',
        'sale_management',
        'sales_team',
        'rest_api',
        'account',
        'restrict_implementation_of_loading_plan'
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Data
        'data/ir_sequence.xml',

        # Reports
        'reports/loading_form_report.xml',

        # Wizard
        'wizard/pause_reason_wizard.xml', 
        'wizard/car_change_wizard.xml', 
        'wizard/loading_worker_wizard.xml', 
        'wizard/quantity_change_wizard.xml', 
        'wizard/warehouse_return_wizard.xml',
        'wizard/delivery_wizard.xml',
        'wizard/close_session_wizard.xml',
        'wizard/scrap_first_loading_wizard.xml',
        'wizard/second_loading_worker_wizard.xml',

        # Views
        'views/fleet_vehicle.xml',
        'views/loading_place.xml',
        'views/account_journal.xml',
        'views/product_template.xml',
        'views/loading_request.xml',
        # 'views/dashboard_analytic.xml',
        'views/res_config_settings.xml',
        'views/sale_order.xml',
        'views/stock_picking.xml',
              
    ],
    # 'assets': {
    # 'web.assets_backend': [
    #     'loading_plans_management/static/src/css/ice_loading.css',
    #     'loading_plans_management/static/src/js/ice_loading_dashboard.js',
    #     'loading_plans_management/static/src/xml/dashboard_templates.xml',
    # ],
    # },

    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OEEL-1',
}