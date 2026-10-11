"""Integration checks using an isolated SQLite database, fake Telegram and PayGate.

Run from the repo root: python -m unittest discover -s tests -p test_cosmetics_checkout.py -v
No real payment, Telegram request or production DB is used.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import urlencode
from unittest.mock import patch, Mock
from shop_test_helpers import ShopTests, m, CONTACT

SECRET = "cosmetic-test-secret-" + "a" * 40
TOKEN = "test-second-bot-token"


def init_data(tid=102, token=TOKEN):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": tid, "first_name": "Alice"})}
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k, v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class CosmeticsTests(ShopTests):
    def setUp(self):
        super().setUp()
        self.environment = patch.dict(os.environ, COSMETICS_CHECKOUT_ENABLED="1",
                                      NYXPEPZ_BRIDGE_SECRET=SECRET, NYXPEPZ_CATALOG_BOT_TOKEN=TOKEN)
        self.environment.start()
        self.wallet = patch("requests.get")
        response = Mock()
        response.json.return_value = {"polygon_address_in": "0x" + "2" * 40, "address_in": "fake-wallet"}
        self.wallet.start().return_value = response
        self.request_bridge("sync", products=[dict(id=1, name="Crème beauté", cents=1050, category="Anti-Age/Peau/Cheveux")])

    def tearDown(self):
        self.wallet.stop()
        self.environment.stop()
        super().tearDown()

    def request_bridge(self, action, **payload):
        raw = json.dumps(dict(action=action, **payload), separators=(",", ":")).encode()
        stamp, nonce = str(int(time.time())), uuid.uuid4().hex
        signature = hmac.new(SECRET.encode(), stamp.encode() + b"." + nonce.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return self.client.post("/api/cosmetics/bridge", data=raw, content_type="application/json",
                                headers={"X-Nyx-Time": stamp, "X-Nyx-Nonce": nonce, "X-Nyx-Signature": signature})

    def new_draft(self):
        response = self.request_bridge("draft", user={"id":102}, key=uuid.uuid4().hex,
                                       items=[dict(cosmetic_id=1, quantity=2)])
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["draft_id"]

    def customer(self, action, draft, tid=102, **payload):
        return self.client.post("/api/cosmetics/customer", json=dict(
            action=action, draft_id=draft, init_data=init_data(tid), **payload))

    def confirm_draft(self, draft):
        quote = self.customer("quote", draft, country="FR").get_json()["quote"]
        return self.customer("confirm", draft, accepted=True, contact=CONTACT, quote_hash=quote["quote_hash"])

    def test_shared_admin_payment_points_and_idempotency(self):
        draft = self.new_draft()
        response = self.confirm_draft(draft)
        self.assertEqual(response.status_code, 200, response.get_json())
        ref = response.get_json()["reference"]
        self.assertIn("checkout.paygate.to", response.get_json()["payment_url"])
        order = self.order(ref)
        self.assertEqual(order.total_cents, 2600)  # 2 x 10.50 + FR shipping 5
        self.assertEqual(order.lines[0]["kind"], "cosmetic")
        self.assertEqual(m.db.session.get(m.User, 2).loyalty_points, 800)
        again = self.customer("confirm", draft, accepted=True).get_json()
        self.assertEqual(again["reference"], ref)
        self.assertEqual(m.shop["Order"].query.count(), 1)
        self.assertEqual(self.receive(ref).status_code, 200)
        self.assertEqual(self.order(ref).status, "payment_review")
        self.assertEqual(m.db.session.get(m.User, 2).loyalty_points, 800)
        self.assertEqual(self.confirm(ref).status_code, 200)
        self.assertEqual(m.db.session.get(m.User, 2).loyalty_points, 821)
        self.assertEqual(self.confirm(ref).status_code, 200)
        self.assertEqual(m.db.session.get(m.User, 2).loyalty_points, 821)
        self.login(1)
        rows = self.client.get("/api/shop/admin/orders?group=preparing").get_json()["orders"]
        self.assertTrue(any(row["reference"] == ref for row in rows))

    def test_ownership_and_authentication(self):
        draft = self.new_draft()
        self.assertEqual(self.customer("load", draft, tid=103).status_code, 404)
        bad = self.client.post("/api/cosmetics/customer", json={"action":"load","draft_id":draft,"init_data":""})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.client.post("/api/cosmetics/bridge", json={"action":"sync","products":[]}).status_code, 401)

    def test_changed_price_requires_new_confirmation(self):
        draft = self.new_draft()
        quote = self.customer("quote", draft, country="FR").get_json()["quote"]
        self.request_bridge("sync", products=[dict(id=1, name="Crème beauté", cents=1200, category="Anti-Age/Peau/Cheveux")])
        result = self.customer("confirm", draft, accepted=True, contact=CONTACT, quote_hash=quote["quote_hash"])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(m.shop["Order"].query.count(), 0)

    def test_delivery_lease_ack_and_failed_paygate_retry(self):
        draft = self.new_draft()
        result = self.confirm_draft(draft)
        self.assertEqual(result.status_code, 200)
        first = self.request_bridge("deliveries").get_json()["deliveries"]
        self.assertEqual(len(first), 1)
        self.assertEqual(self.request_bridge("deliveries").get_json()["deliveries"], [])
        self.request_bridge("ack", id=first[0]["id"], lease=first[0]["lease"])
        self.assertEqual(self.request_bridge("deliveries").get_json()["deliveries"], [])
        retry = self.request_bridge("retry_payment", user={"id":102}, draft_id=draft)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(len(self.request_bridge("deliveries").get_json()["deliveries"]), 1)

    def test_invalid_cart_and_disabled_checkout(self):
        response = self.request_bridge("draft", user={"id":102}, key=uuid.uuid4().hex,
                                       items=[dict(product_id=1, quantity=1)])
        self.assertEqual(response.status_code, 400)
        with patch.dict(os.environ, COSMETICS_CHECKOUT_ENABLED="0"):
            response = self.request_bridge("draft", user={"id":102}, key=uuid.uuid4().hex,
                                           items=[dict(cosmetic_id=1, quantity=1)])
            self.assertEqual(response.status_code, 503)
            self.assertEqual(self.request_bridge("profile", user={"id":102}).status_code, 200)

    def test_referral_keeps_existing_account_and_does_not_duplicate(self):
        user = m.db.session.get(m.User, 2)
        user.referred_by_user_id = 3
        m.db.session.commit()
        response = self.confirm_draft(self.new_draft())
        ref = response.get_json()["reference"]
        self.receive(ref)
        self.assertEqual(self.confirm(ref).status_code, 200)
        self.assertEqual(self.confirm(ref).status_code, 200)
        self.assertEqual(m.ReferralOrderEvent.query.count(), 1)
        self.assertEqual(m.db.session.get(m.User, 3).referral_points, 2)
        self.assertEqual(m.referral_rewards["balance"](m.db.session.get(m.User,3)), 2.1)

