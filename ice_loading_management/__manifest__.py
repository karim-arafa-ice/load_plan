
# Ice Loading Management Module for Odoo 17 Enterprise
# Module Structure and Key Files

{
    'name': 'Ice Loading Management',
    'summary': 'Complete ice manufacturing loading and delivery management system',
    'author': 'karim arafa',
    'depends': [
        'base',
        'fleet',
        'stock',
        'sale',
        'crm',
        'account_asset',
        'customer_management',
        'mrp',
        'mail',
        'maintenance_app',
        'freezers_management',
        'sale_management',
        'sales_team',
        'rest_api',
        'account',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        'data/ir_sequence.xml',
        'data/cron.xml',
        
        'wizard/set_full_load_wizard.xml',
        'wizard/car_change_wizard.xml',
        'wizard/form_ipload_wizard.xml',
        'wizard/loading_worker_wizard.xml',
        'wizard/quantity_change_wizard.xml',
        'wizard/pause_reason_wizard.xml', # New
        'wizard/warehouse_return_wizard.xml', # New
        'wizard/delivery_wizard.xml',  # New

        # Views
        'views/fleet_vehicle.xml',
        'views/res_config_settings.xml',
        'views/dashboard_analytic.xml',
        'views/return_request_views.xml',

        # Reports
        # 'reports/freezer_release_form_report.xml',
        'reports/loading_form_report.xml',




        
      
    ],
    'assets': {
    'web.assets_backend': [
        'ice_loading_management/static/src/css/ice_loading.css',
        'ice_loading_management/static/src/js/ice_loading_dashboard.js',
        'ice_loading_management/static/src/xml/dashboard_templates.xml',
    ],
},
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OEEL-1',
}