import os
import tempfile
import unittest

from app import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DB_PATH": self.path, "TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.path)

    # helpers
    def post(self, url, body):
        return self.client.post(url, json=body)

    def make_basics(self):
        r = self.post("/api/restaurants", {"name": "Test Diner"}).get_json()
        c = self.post("/api/customers", {"name": "Asha", "email": "asha@example.com"}).get_json()
        m1 = self.post("/api/menu-items", {"restaurant_id": r["id"], "name": "Pizza", "price": 100}).get_json()
        m2 = self.post("/api/menu-items", {"restaurant_id": r["id"], "name": "Soda", "price": 25.5}).get_json()
        return r, c, m1, m2


class TestPlatform(ApiTestCase):
    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_metrics_exposed(self):
        self.client.get("/health")
        body = self.client.get("/metrics").get_data(as_text=True)
        self.assertIn("restaurant_http_requests_total", body)
        self.assertIn("restaurant_app_info", body)

    def test_home_page(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_unknown_api_route_is_json_404(self):
        r = self.client.get("/api/nothing")
        self.assertEqual(r.status_code, 404)


class TestCrud(ApiTestCase):
    def test_restaurant_crud(self):
        r = self.post("/api/restaurants", {"name": "  Cafe One ", "address": "Pune"})
        self.assertEqual(r.status_code, 201)
        rid = r.get_json()["id"]
        self.assertEqual(r.get_json()["name"], "Cafe One")
        self.assertEqual(self.client.get("/api/restaurants/%d" % rid).status_code, 200)
        u = self.client.put("/api/restaurants/%d" % rid, json={"phone": "123"})
        self.assertEqual(u.get_json()["phone"], "123")
        self.assertEqual(len(self.client.get("/api/restaurants").get_json()), 1)
        self.assertEqual(self.client.delete("/api/restaurants/%d" % rid).status_code, 204)
        self.assertEqual(self.client.get("/api/restaurants/%d" % rid).status_code, 404)

    def test_validation_errors(self):
        self.assertEqual(self.post("/api/restaurants", {}).status_code, 400)
        self.assertEqual(self.post("/api/restaurants", {"name": "   "}).status_code, 400)
        self.assertEqual(self.client.post("/api/restaurants", data="notjson").status_code, 400)
        r, *_ = self.make_basics()
        bad = self.post("/api/menu-items", {"restaurant_id": r["id"], "name": "X", "price": -5})
        self.assertEqual(bad.status_code, 400)
        orphan = self.post("/api/menu-items", {"restaurant_id": 999, "name": "X", "price": 5})
        self.assertEqual(orphan.status_code, 400)

    def test_duplicate_email(self):
        self.post("/api/customers", {"name": "A", "email": "a@x.com"})
        r = self.post("/api/customers", {"name": "B", "email": "a@x.com"})
        self.assertEqual(r.status_code, 409)

    def test_menu_item_availability_and_filter(self):
        r, _, m1, _ = self.make_basics()
        u = self.client.patch("/api/menu-items/%d" % m1["id"], json={"available": False})
        self.assertFalse(u.get_json()["available"])
        items = self.client.get("/api/menu-items?restaurant_id=%d" % r["id"]).get_json()
        self.assertEqual(len(items), 2)

    def test_update_missing_returns_404(self):
        self.assertEqual(self.client.put("/api/customers/42", json={"name": "Z"}).status_code, 404)


class TestOrders(ApiTestCase):
    def test_order_total_and_items(self):
        r, c, m1, m2 = self.make_basics()
        res = self.post("/api/orders", {
            "customer_id": c["id"], "restaurant_id": r["id"],
            "items": [{"menu_item_id": m1["id"], "quantity": 2}, {"menu_item_id": m2["id"], "quantity": 1}],
        })
        self.assertEqual(res.status_code, 201)
        order = res.get_json()
        self.assertEqual(order["total"], 225.5)
        self.assertEqual(order["status"], "PLACED")
        self.assertEqual(len(order["items"]), 2)
        self.assertEqual(self.client.get("/api/stats").get_json()["orders"], 1)

    def test_order_rejects_unavailable_and_foreign_items(self):
        r, c, m1, _ = self.make_basics()
        self.client.patch("/api/menu-items/%d" % m1["id"], json={"available": False})
        res = self.post("/api/orders", {"customer_id": c["id"], "restaurant_id": r["id"],
                                         "items": [{"menu_item_id": m1["id"], "quantity": 1}]})
        self.assertEqual(res.status_code, 400)
        res = self.post("/api/orders", {"customer_id": c["id"], "restaurant_id": r["id"], "items": []})
        self.assertEqual(res.status_code, 400)
        res = self.post("/api/orders", {"customer_id": 999, "restaurant_id": r["id"],
                                         "items": [{"menu_item_id": m1["id"]}]})
        self.assertEqual(res.status_code, 400)

    def test_status_update_and_delete_guard(self):
        r, c, m1, _ = self.make_basics()
        order = self.post("/api/orders", {"customer_id": c["id"], "restaurant_id": r["id"],
                                           "items": [{"menu_item_id": m1["id"], "quantity": 1}]}).get_json()
        ok = self.client.patch("/api/orders/%d/status" % order["id"], json={"status": "SERVED"})
        self.assertEqual(ok.get_json()["status"], "SERVED")
        bad = self.client.patch("/api/orders/%d/status" % order["id"], json={"status": "FLYING"})
        self.assertEqual(bad.status_code, 400)
        # restaurant and customer are referenced by an order -> 409
        self.assertEqual(self.client.delete("/api/restaurants/%d" % r["id"]).status_code, 409)
        self.assertEqual(self.client.delete("/api/customers/%d" % c["id"]).status_code, 409)
        self.assertEqual(self.client.delete("/api/orders/%d" % order["id"]).status_code, 204)
        self.assertEqual(self.client.delete("/api/customers/%d" % c["id"]).status_code, 204)


if __name__ == "__main__":
    unittest.main()
