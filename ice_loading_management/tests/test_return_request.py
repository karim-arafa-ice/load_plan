# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from datetime import date

class TestReturnRequest(TransactionCase):
    """
    Test suite for the salesman return request process.
    """

    def setUp(self):
        """Set up the test environment for return requests."""
        super(TestReturnRequest, self).setUp()

        # --- Create Users ---
        self.salesman = self.env['res.users'].create({
            'name': 'Returning Salesman',
            'login': 'return_sales',
        })

        # --- Create a completed Loading Request for the day ---
        car = self.env['fleet.vehicle'].create({
            'model_id': self.env.ref('fleet.model_ford_truck').id,
            'license_plate': 'RETURN-1',
        })
        self.completed_loading_request = self.env['ice.loading.request'].create({
            'name': 'Completed Load for Return Test',
            'car_id': car.id,
            'salesman_id': self.salesman.id,
            'dispatch_time': date.today(),
            'loading_place_id': self.env['ice.loading.place'].create({
                'name': 'alahsa',
                'loading_location_id': self.env.ref('stock.stock_location_stock').id
            }).id,
            'state': 'delivered', # A state from which returns can be made
        })
        
        # --- Create a Driver Session to be closed ---
        self.driver_session = self.env['ice.driver.session'].create({
            'driver_id': self.salesman.id,
            'car_id': car.id,
            'loading_request_id': self.completed_loading_request.id,
        })

    def test_01_create_return_request_on_session_close(self):
        """Test that a return request is created when a driver session is closed."""
        # Close the session
        self.driver_session.close_session()
        
        # Find the created return request
        return_request = self.env['ice.return.request'].search([
            ('salesman_id', '=', self.salesman.id),
            ('date', '=', date.today()),
        ])
        
        self.assertTrue(return_request, "A return request should be created.")
        self.assertEqual(len(return_request), 1, "Only one consolidated return request should be created for the day.")
        self.assertIn(self.completed_loading_request, return_request.loading_request_ids, "Return request should link to the day's loading requests.")
        self.assertEqual(return_request.state, 'draft', "Initial state of return request should be 'draft'.")

    def test_02_return_workflow(self):
        """Test the state transitions of the return request workflow."""
        # Create the return request
        self.driver_session.close_session()
        return_request = self.env['ice.return.request'].search([('salesman_id', '=', self.salesman.id)])
        
        # Start the return process
        return_request.action_start_return()
        
        self.assertEqual(return_request.state, 'warehouse_check', "State should move to 'warehouse_check'.")
        self.assertTrue(return_request.car_check_request_ids, "Car check requests should be created.")

        # Simulate warehouse check via wizard
        warehouse_wizard = self.env['ice.warehouse.return.wizard'].with_context({
            'default_return_request_id': return_request.id
        }).create({})
        warehouse_wizard.action_process_return()

        self.assertEqual(return_request.state, 'car_check', "State should move to 'car_check' after warehouse processing.")

        # Simulate car check completion
        for car_check in return_request.car_check_request_ids:
            car_check.action_stop() # Simulate completion
        
        # This part of the workflow is manual in the code, so we can't test an automatic state change.
        # We will manually trigger the next step.
        return_request.state = 'payment'
        
        # Process payment
        return_request.action_process_payment()
        self.assertTrue(return_request.cash_payment_id, "A cash payment record should be created.")
        self.assertEqual(return_request.state, 'done', "State should move to 'done' after payment.")

