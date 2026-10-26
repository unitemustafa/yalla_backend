from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import Order


class CourierActivePagingTests(APITestCase):
    setUp = fixtures.OrderAPITests.setUp

    def test_active_totals_cover_unloaded_pages_and_exclude_other_couriers(self):
        Order.objects.bulk_create([
            Order(user=self.customer, market=self.market,
                  delivery_address=self.address,
                  assigned_representative=self.representative,
                  status=Order.Status.ASSIGNED if index < 65 else Order.Status.PICKED_UP,
                  total_price=100, delivery_price=15)
            for index in range(70)
        ])
        Order.objects.create(user=self.customer, market=self.market,
                             delivery_address=self.address,
                             assigned_representative=self.admin,
                             status=Order.Status.ASSIGNED, total_price=999)
        self.client.force_authenticate(self.representative)
        response = self.client.get('/api/v1/courier/orders/',
                                   {'scope': 'active', 'page': 1, 'page_size': 30})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 30)
        self.assertEqual(response.data['count'], 70)
        self.assertEqual(response.data['summary'], {
            'count': 70, 'pickup_required_count': 65,
            'total_value': '7000.00', 'total_delivery_fees': '1050.00',
        })
        self.assertIsNotNone(response.data['next'])
        history = self.client.get('/api/v1/courier/orders/', {'scope': 'history'})
        self.assertNotIn('pickup_required_count', history.data['summary'])
