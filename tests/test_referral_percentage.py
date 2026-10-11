"""Temporary SQLite DB and simulated PayGate. No live payments or points."""
import uuid
from test_cosmetics_checkout import CosmeticsTests,m
from referral_rewards import points_from_units


class ReferralPercentageTests(CosmeticsTests):
    def setUp(self):
        super().setUp()
        m.db.session.get(m.User,2).referred_by_user_id=3
        m.db.session.commit()

    def balance(self):
        return m.referral_rewards["balance"](m.db.session.get(m.User,3))

    def paid_cosmetic(self):
        response=self.confirm_draft(self.new_draft())
        self.assertEqual(response.status_code,200,response.get_json())
        ref=response.get_json()["reference"]
        self.assertEqual(self.receive(ref).status_code,200)
        self.assertEqual(self.confirm(ref).status_code,200)
        return ref

    def test_first_ten_then_five_and_no_duplicate(self):
        first=self.paid_cosmetic()
        self.assertEqual(self.balance(),2.1)  # 21 euro goods x 10%, excluding 5 euro delivery.
        second=self.paid_cosmetic()
        self.assertEqual(self.balance(),3.15)  # Second 21 euro x 5%.
        self.assertEqual(self.confirm(second).status_code,200)
        self.assertEqual(self.balance(),3.15)
        Credit=m.referral_rewards["Credit"]
        self.assertEqual([row.rate_percent for row in Credit.query.order_by(Credit.id)], [10,5])
        self.assertEqual(m.ReferralOrderEvent.query.count(),2)
        self.login(3)
        self.assertEqual(self.client.get("/api/me").get_json()["referral_points"],3.15)
        self.login(2)
        profile=self.request_bridge("profile",user={"id":103}).get_json()
        self.assertEqual(profile["referral_points"],3.15)

    def test_old_balance_is_kept_without_recalculating_past_orders(self):
        m.db.session.get(m.User,3).referral_points=7
        m.db.session.commit()
        self.paid_cosmetic()
        self.assertEqual(self.balance(),9.1)
        row=m.db.session.get(m.referral_rewards["Balance"],3)
        self.assertEqual(row.base_points,7)

    def test_unpaid_and_received_but_not_confirmed_do_not_credit(self):
        response=self.confirm_draft(self.new_draft())
        ref=response.get_json()["reference"]
        self.assertEqual(self.balance(),0)
        self.receive(ref)
        self.assertEqual(self.balance(),0)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.balance(),2.1)

    def test_historical_paid_order_means_new_order_is_five_percent(self):
        m.db.session.add(m.ConfirmedOrderEvent(external_order_id="historical-order",user_id=2,loyalty_points=10))
        m.db.session.add(m.ReferralOrderEvent(external_order_id="historical-order",referred_user_id=2,referrer_user_id=3))
        m.db.session.get(m.User,3).referral_points=1
        m.db.session.commit()
        self.paid_cosmetic()
        self.assertEqual(self.balance(),2.05)
        self.assertEqual(m.referral_rewards["Credit"].query.one().rate_percent,5)

    def test_discount_basis_uses_actual_goods_paid(self):
        product=m.db.session.get(m.Product,1)
        product.name,product.format,product.price="Crème test","",100
        m.db.session.commit()
        ref=self.create(reward=150)  # 100 euro goods minus 10 euro reward.
        self.assertEqual(self.order(ref).subtotal_cents,10000)
        self.assertEqual(self.order(ref).discount_cents,1000)
        self.receive(ref)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.balance(),9)

    def test_small_fractions_do_not_disappear(self):
        self.request_bridge("sync",products=[dict(id=1,name="Crème test",cents=1,category="Anti-Age/Peau/Cheveux")])
        self.paid_cosmetic()  # Two cents products x 10% = .002 points.
        self.paid_cosmetic()  # Two cents x 5% = .001 points.
        self.assertEqual(self.balance(),0.003)

    def test_external_confirmation_requires_net_amount_and_is_idempotent(self):
        oid="external-"+uuid.uuid4().hex
        payload=dict(order_id=oid,telegram_id=102,loyalty_points=100)
        headers={"X-Nyx-Secret":"test-secret"}
        before=m.db.session.get(m.User,2).loyalty_points
        missing=self.client.post("/api/internal/orders/confirmed",json=payload,headers=headers)
        self.assertEqual(missing.status_code,400)
        self.assertEqual(m.db.session.get(m.User,2).loyalty_points,before)
        payload["paid_products_cents"]=10000
        self.assertEqual(self.client.post("/api/internal/orders/confirmed",json=payload,headers=headers).status_code,200)
        self.assertEqual(self.client.post("/api/internal/orders/confirmed",json=payload,headers=headers).status_code,200)
        self.assertEqual(self.balance(),10)
        payload["order_id"]="external-"+uuid.uuid4().hex
        self.assertEqual(self.client.post("/api/internal/orders/confirmed",json=payload,headers=headers).status_code,200)
        self.assertEqual(self.balance(),15)

    def test_reconcile_keeps_fractional_credits(self):
        self.paid_cosmetic()
        m.db.session.get(m.User,3).referral_points=0
        m.db.session.commit()
        self.assertEqual(m.referral_rewards["expected_whole"](3),2)
        # The audit repairs the integer cache without losing .1 point.
        result=m.app.test_cli_runner().invoke(args=["reconcile-referrals","--repair"])
        self.assertEqual(result.exit_code,0,result.output)
        m.db.session.expire_all()
        self.assertEqual(m.db.session.get(m.User,3).referral_points,2)
        self.assertEqual(self.balance(),2.1)
