# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError,UserError
from datetime import datetime, timedelta

class TestSecurity(TransactionCase):
    """
    Test suite for security rules and access rights.
    """

    def setUp(self):
        """Set up users with different roles."""
        super(TestSecurity, self).setUp()

        # --- Create Users ---
        self.salesman1 = self.env['res.users'].create({
            'name': 'Salesman One',
            'login': 'sales1',
            'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id])]
        })
        self.salesman2 = self.env['res.users'].create({
            'name': 'Salesman Two',
            'login': 'sales2',
            'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id])]
        })
        self.sales_supervisor = self.env['res.users'].create({
            'name': 'Sales Supervisor',
            'login': 'supr',
            # group_sale_salesman_all_leads is the supervisor group
            'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman_all_leads').id])]
        })
        self.fleet_supervisor = self.env['res.users'].create({
            'name': 'Fleet Supervisor Secure',
            'login': 'fleet_secure',
            'groups_id': [(6, 0, [self.env.ref('ice_loading_management.group_fleet_supervisor').id])]
        })

        # --- Create a loading request for salesman1 ---
        car = self.env['fleet.vehicle'].create({
            'model_id': self.env.ref('fleet.model_ford_truck').id,
            'license_plate': 'SECURE-1',
        })
        self.lr_salesman1 = self.env['ice.loading.request'].create({
            'car_id': car.id,
            'salesman_id': self.salesman1.id,
            'dispatch_time': datetime.now() + timedelta(days=2),
            'loading_place_id': self.env['ice.loading.place'].create({
                'name': 'dammam', 
                'loading_location_id': self.env.ref('stock.stock_location_stock').id
            }).id,
        })

    def test_01_salesman_record_rule(self):
        """Test that a salesman can only see their own loading requests."""
        # Search for requests as salesman1
        requests_s1 = self.env['ice.loading.request'].with_user(self.salesman1).search([])
        self.assertIn(self.lr_salesman1, requests_s1, "Salesman 1 should see their own request.")
        
        # Search for requests as salesman2
        requests_s2 = self.env['ice.loading.request'].with_user(self.salesman2).search([])
        self.assertNotIn(self.lr_salesman1, requests_s2, "Salesman 2 should not see Salesman 1's request.")

    def test_02_quantity_change_permission(self):
        """Test that only a sales supervisor can change quantities."""
        # A regular salesman should not be able to open the wizard
        with self.assertRaises(AccessError, msg="Salesman should not be able to change quantities."):
            self.lr_salesman1.with_user(self.salesman1).action_change_quantities_wizard()
            
        # A sales supervisor should be able to open the wizard
        try:
            self.lr_salesman1.with_user(self.sales_supervisor).action_change_quantities_wizard()
        except AccessError:
            self.fail("Sales Supervisor should have access to the quantity change wizard.")

    def test_03_car_change_permission(self):
        """Test that only a fleet supervisor can change the car."""
        # A salesman should not be able to change the car
        with self.assertRaises(AccessError, msg="Salesman should not be able to change the car."):
            self.lr_salesman1.with_user(self.salesman1).action_change_car()
            
        # A fleet supervisor should be able to open the car change wizard
        try:
            self.lr_salesman1.with_user(self.fleet_supervisor).action_change_car()
        except AccessError:
            self.fail("Fleet Supervisor should have access to the car change wizard.")

    def test_04_state_constraints_for_wizards(self):
        """Test that wizards/actions are blocked in certain states."""
        # Move request to a state where car change is not allowed
        self.lr_salesman1.state = 'plugged'
        
        with self.assertRaises(UserError, msg="Car change should be blocked in 'plugged' state."):
            self.lr_salesman1.with_user(self.fleet_supervisor).action_change_car()
            
        with self.assertRaises(UserError, msg="Quantity change should be blocked in 'plugged' state."):
            self.lr_salesman1.with_user(self.sales_supervisor).action_change_quantities_wizard()

