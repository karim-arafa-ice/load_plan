
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
        'sales_team',
        'rest_api',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Views
        'views/fleet_vehicle.xml',
        

        # Reports
        # 'reports/freezer_release_form_report.xml',
        'reports/loading_form_report.xml',
        'views/res_config_settings.xml',

        
        'views/dashboard_analytic.xml',

        'wizard/set_full_load_wizard.xml',
        'wizard/car_change_wizard.xml',
        'wizard/form_ipload_wizard.xml',
        'wizard/loading_worker_wizard.xml',
        'wizard/quantity_change_wizard.xml',


        'data/ir_sequence.xml',
      
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