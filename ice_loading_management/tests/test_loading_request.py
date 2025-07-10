# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

class TestLoadingRequest(TransactionCase):
    """
    Test suite for the standard (non-concrete) ice loading request workflow.
    """

    def setUp(self):
        """
        Set up the test environment with necessary data.
        This method is called before each test function.
        """
        super(TestLoadingRequest, self).setUp()

        # --- Create User Groups ---
        self.group_sales_manager = self.env.ref('sales_team.group_sale_manager')
        self.group_fleet_supervisor = self.env.ref('ice_loading_management.group_fleet_supervisor')
        self.group_loading_worker = self.env.ref('ice_loading_management.group_loading_worker')
        self.group_salesman = self.env.ref('sales_team.group_sale_salesman')

        # --- Create Users ---
        self.sales_manager = self.env['res.users'].create({
            'name': 'Sales Manager',
            'login': 'manager',
            'groups_id': [(6, 0, [self.group_sales_manager.id])]
        })
        self.fleet_supervisor = self.env['res.users'].create({
            'name': 'Fleet Supervisor',
            'login': 'fleet',
            'groups_id': [(6, 0, [self.group_fleet_supervisor.id])]
        })
        self.loading_worker = self.env['res.users'].create({
            'name': 'Loading Worker',
            'login': 'worker',
            'groups_id': [(6, 0, [self.group_loading_worker.id])]
        })
        self.salesman = self.env['res.users'].create({
            'name': 'Salesman Bob',
            'login': 'salesman',
            'groups_id': [(6, 0, [self.group_salesman.id])]
        })
        
        # --- Create Products ---
        self.product_4kg = self.env['product.product'].create({
            'name': '4kg Ice Block',
            'type': 'product',
            'weight': 4.0,
            'ice_product_type': '4kg',
        })
        self.product_25kg = self.env['product.product'].create({
            'name': '25kg Ice Block',
            'type': 'product',
            'weight': 25.0,
            'ice_product_type': '25kg',
        })

        # --- Create Fleet Vehicle ---
        self.car = self.env['fleet.vehicle'].create({
            'model_id': self.env.ref('fleet.model_astra').id,
            'license_plate': 'TEST-123',
            'driver_id': self.salesman.partner_id.id,
            'ice_4kg_capacity': 100.0,
            'ice_25kg_capacity': 500.0,
            'total_weight_capacity': 600.0,
            'loading_status': 'available',
        })

        # --- Create Loading Place ---
        self.loading_place = self.env['ice.loading.place'].create({
            'name': 'dammam',
            'loading_priority': 1,
            'loading_location_id': self.env.ref('stock.stock_location_stock').id,
        })
        
        # --- Create Loading Request ---
        self.loading_request = self.env['ice.loading.request'].with_user(self.salesman).create({
            'car_id': self.car.id,
            'salesman_id': self.salesman.id,
            'dispatch_time': datetime.now() + timedelta(days=1),
            'loading_place_id': self.loading_place.id,
            'product_line_ids': [
                (0, 0, {'product_id': self.product_4kg.id, 'quantity': 10}), # 40kg
                (0, 0, {'product_id': self.product_25kg.id, 'quantity': 5}), # 125kg
            ]
        })

    def test_01_create_loading_request(self):
        """Test the creation of a loading request and its default values."""
        self.assertTrue(self.loading_request, "Loading request should be created.")
        self.assertEqual(self.loading_request.state, 'draft', "Initial state should be 'draft'.")
        self.assertEqual(self.loading_request.total_weight, 165.0, "Total weight should be calculated correctly.")
        self.assertIsNotNone(self.loading_request.name, "Request should have a reference name.")
        
    def test_02_workflow_confirmation(self):
        """Test the confirmation of a loading request and creation of related records."""
        self.loading_request.with_user(self.sales_manager).action_confirm_request()
        
        self.assertEqual(self.loading_request.state, 'car_checking', "State should move to 'car_checking'.")
        
        # Check for related records
        self.assertTrue(self.loading_request.car_check_request_id, "Car check request should be created.")
        self.assertTrue(self.loading_request.internal_transfer_id, "Internal transfer should be created.")
        
        # Check car status
        self.assertEqual(self.car.loading_status, 'in_use', "Car status should be 'in_use'.")

    def test_03_workflow_full_cycle(self):
        """Test the full workflow from draft to done."""
        # Confirm (Sales Manager)
        self.loading_request.with_user(self.sales_manager).action_confirm_request()
        self.assertEqual(self.loading_request.state, 'car_checking')

        # Car Check (Fleet Supervisor)
        self.loading_request.car_check_request_id.with_user(self.fleet_supervisor).action_stop()
        self.assertEqual(self.loading_request.state, 'ready_for_loading')
        self.assertEqual(self.car.loading_status, 'ready_for_loading')

        # Loading (Loading Worker)
        # We need to simulate the wizard action
        worker_wizard = self.env['ice.loading.worker.wizard'].with_context({
            'default_loading_request_id': self.loading_request.id
        }).create({})
        worker_wizard.with_user(self.loading_worker)._complete_loading()
        self.assertEqual(self.loading_request.state, 'ice_handled')
        self.assertEqual(self.loading_request.internal_transfer_id.state, 'done')

        # Plug Car (Fleet Supervisor)
        self.loading_request.with_user(self.fleet_supervisor).action_proceed_to_plugged()
        self.assertEqual(self.loading_request.state, 'plugged')
        self.assertEqual(self.car.loading_status, 'plugged')
        
        # Start Delivery (Salesman) - Requires signed form
        self.loading_request.signed_loading_form = "test_signature_data" # Mock data
        self.loading_request.with_user(self.salesman).action_start_delivery()
        self.assertEqual(self.loading_request.state, 'in_transit')
        
        # This is a simplified test. A full test would involve delivery wizards and return requests.

    def test_04_capacity_constraint(self):
        """Test the weight capacity constraint."""
        with self.assertRaises(ValidationError, msg="Should not allow weight to exceed capacity."):
            self.env['ice.loading.product.line'].create({
                'loading_request_id': self.loading_request.id,
                'product_id': self.product_25kg.id,
                'quantity': 20, # 500kg, which exceeds total capacity
            })

    def test_05_car_change_wizard(self):
        """Test the car change wizard."""
        new_car = self.env['fleet.vehicle'].create({
            'model_id': self.env.ref('fleet.model_astra').id,
            'license_plate': 'NEW-CAR-1',
            'total_weight_capacity': 700.0,
            'loading_status': 'available',
        })
        
        # Open the wizard
        change_wizard = self.env['ice.car.change.wizard'].with_user(self.fleet_supervisor).create({
            'loading_request_id': self.loading_request.id,
            'current_car_id': self.car.id,
            'new_car_id': new_car.id,
            'reason': 'Original car broke down.',
        })
        
        # Execute the change
        change_wizard.action_change_car()
        
        self.assertEqual(self.loading_request.car_id, new_car, "Car should be changed.")
        self.assertEqual(self.loading_request.previous_car_id, self.car, "Previous car should be recorded.")
        self.assertEqual(self.car.loading_status, 'available', "Old car should be available.")
        self.assertEqual(new_car.loading_status, 'in_use', "New car should be in use.")

    def test_06_quantity_change_wizard(self):
        """Test the quantity change wizard by a sales supervisor."""
        self.loading_request.with_user(self.sales_manager).action_confirm_request()
        
        # Open the wizard
        qty_wizard = self.env['ice.loading.quantity.change.wizard'].with_user(self.sales_manager).create({
            'loading_request_id': self.loading_request.id,
            'change_reason': 'Customer updated their order.',
        })
        
        # Change a quantity
        wizard_line = qty_wizard.line_ids.filtered(lambda l: l.product_id == self.product_4kg)
        wizard_line.new_quantity = 15
        
        # Confirm changes
        qty_wizard.action_confirm()
        
        request_line = self.loading_request.product_line_ids.filtered(lambda l: l.product_id == self.product_4kg)
        self.assertEqual(request_line.quantity, 15, "Quantity should be updated.")
        
        # Check history
        change_history = self.env['ice.loading.quantity.change'].search([
            ('loading_request_id', '=', self.loading_request.id)
        ])
        self.assertEqual(len(change_history), 1, "A change history record should be created.")
        self.assertEqual(change_history.new_quantity, 15)

