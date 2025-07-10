# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from datetime import datetime, timedelta

class TestConcreteHandling(TransactionCase):
    """
    Test suite for the concrete handling functionality in loading requests.
    """

    def setUp(self):
        """Set up the test environment for concrete handling."""
        super(TestConcreteHandling, self).setUp()

        # --- Create Users ---
        self.salesman = self.env['res.users'].create({
            'name': 'Concrete Salesman',
            'login': 'concrete_sales',
        })
        
        # --- Create Customer with an open Sale Order ---
        self.product_concrete = self.env['product.product'].create({
            'name': 'Ready-Mix Concrete',
            'type': 'service', # Concrete is often a service in Odoo
        })
        self.customer = self.env['res.partner'].create({
            'name': 'Concrete Customer Inc.',
            'customer_rank': 1,
        })
        self.sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_concrete.id,
                    'product_uom_qty': 50,
                })
            ]
        })
        self.sale_order.action_confirm()

        # --- Create a Concrete Car ---
        self.concrete_car = self.env['fleet.vehicle'].create({
            'model_id': self.env.ref('fleet.model_mercedes_truck').id,
            'license_plate': 'CONCRETE-1',
            'is_concrete': True,
            'total_weight_capacity': 10000, # 10 tons
            'loading_status': 'available',
            'location_id': self.env.ref('stock.stock_location_stock').id,
        })
        
        # --- Create Loading Place ---
        self.loading_place = self.env['ice.loading.place'].create({
            'name': 'riyadh',
            'loading_priority': 2,
            'loading_location_id': self.env.ref('stock.stock_location_stock').id,
        })
        
        # --- Create a Concrete Loading Request ---
        self.concrete_request = self.env['ice.loading.request'].with_user(self.salesman).create({
            'car_id': self.concrete_car.id,
            'salesman_id': self.salesman.id,
            'dispatch_time': datetime.now() + timedelta(days=1),
            'loading_place_id': self.loading_place.id,
            'is_concrete': True,
        })

    def test_01_create_concrete_request(self):
        """Test the creation of a concrete loading request."""
        self.assertTrue(self.concrete_request, "Concrete loading request should be created.")
        self.assertTrue(self.concrete_request.is_concrete, "Request should be marked as concrete.")
        self.assertFalse(self.concrete_request.product_line_ids, "Product lines should be empty for concrete requests.")

    def test_02_add_customer_line(self):
        """Test adding a customer line to a concrete request."""
        customer_line = self.env['ice.loading.customer.line'].create({
            'loading_request_id': self.concrete_request.id,
            'customer_id': self.customer.id,
            'quantity': 30,
        })
        
        self.assertTrue(customer_line, "Customer line should be created.")
        self.assertEqual(customer_line.sale_order_id, self.sale_order, "It should link to the customer's open sale order.")
        self.assertEqual(customer_line.remaining_qty, 50, "Remaining quantity should be fetched correctly.")

    def test_03_concrete_delivery_creation(self):
        """Test the creation of delivery orders from a concrete request."""
        # Add a customer line
        self.env['ice.loading.customer.line'].create({
            'loading_request_id': self.concrete_request.id,
            'customer_id': self.customer.id,
            'quantity': 25,
        })
        
        # Confirm the loading request
        self.concrete_request.action_confirm_request()
        
        # Validate the main transfer (simulating storekeeper action)
        self.concrete_request.internal_transfer_id.button_validate()
        
        # Check that a delivery picking was created for the customer line
        customer_line = self.concrete_request.customer_line_ids[0]
        self.assertTrue(customer_line.delivery_id, "A delivery picking should be created for the customer line.")
        self.assertEqual(customer_line.delivery_id.state, 'assigned', "Delivery should be in 'Ready' state.")
        self.assertEqual(customer_line.delivery_id.move_ids_without_package.product_uom_qty, 25, "Delivery quantity should be correct.")

    def test_04_delivery_wizard(self):
        """Test the delivery wizard for updating actual delivered quantities."""
        # Set up the request and create deliveries
        self.env['ice.loading.customer.line'].create({
            'loading_request_id': self.concrete_request.id,
            'customer_id': self.customer.id,
            'quantity': 40,
        })
        self.concrete_request.action_confirm_request()
        self.concrete_request.internal_transfer_id.button_validate()
        self.concrete_request.state = 'in_transit' # Move to a state where delivery happens

        # Open and use the delivery wizard
        delivery_wizard = self.env['delivery.wizard'].with_context({
            'active_id': self.concrete_request.id,
            'active_model': 'ice.loading.request',
        }).create({})
        
        self.assertEqual(len(delivery_wizard.line_ids), 1, "Wizard should have one line for the delivery.")
        
        # Simulate delivering a different quantity
        delivery_wizard.line_ids[0].delivered_quantity = 38
        delivery_wizard.action_validate()
        
        customer_line = self.concrete_request.customer_line_ids[0]
        self.assertTrue(customer_line.is_delivered, "Customer line should be marked as delivered.")
        self.assertEqual(customer_line.delivery_id.state, 'done', "The delivery picking should be 'Done'.")
        self.assertEqual(self.concrete_request.state, 'delivered', "The loading request should move to 'Delivered'.")

