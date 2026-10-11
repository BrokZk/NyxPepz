"""Inventory and tracking checks: isolated DB, simulated Telegram and payment."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from test_cosmetics_checkout import CosmeticsTests,m,init_data,CONTACT


class StockTrackingTests(CosmeticsTests):
    def stock(self):
        return self.request_bridge("stocks").get_json()["stocks"][0]["available"]

    def set_stock(self,quantity,key=None,tid=8843973247):
        return self.request_bridge("set_stock",user={"id":tid},product_id=1,
                                   quantity=quantity,key=key or uuid.uuid4().hex)

    def test_reserve_once_pay_once_and_metadata_does_not_reset_stock(self):
        self.set_stock(5)
        draft=self.new_draft()
        result=self.confirm_draft(draft)
        self.assertEqual(result.status_code,200,result.get_json())
        ref=result.get_json()["reference"]
        self.assertEqual(self.stock(),3)
        self.customer("confirm",draft,accepted=True)
        self.assertEqual(self.stock(),3)
        self.request_bridge("sync",products=[dict(id=1,name="Crème renommée",cents=1050,category="Anti-Age/Peau/Cheveux")])
        self.assertEqual(self.stock(),3)
        self.receive(ref)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.stock(),3)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.stock(),3)

    def test_cancellation_returns_units_once(self):
        self.set_stock(5)
        result=self.confirm_draft(self.new_draft())
        ref=result.get_json()["reference"]
        self.assertEqual(self.stock(),3)
        self.assertEqual(self.client.post("/api/shop/orders/"+ref+"/cancel").status_code,200)
        self.assertEqual(self.stock(),5)
        self.client.post("/api/shop/orders/"+ref+"/cancel")
        self.assertEqual(self.stock(),5)

    def test_expiry_and_late_payment_reacquire_stock(self):
        self.set_stock(5)
        result=self.confirm_draft(self.new_draft())
        ref=result.get_json()["reference"]
        order=self.order(ref)
        order.expires_at=int(time.time())-1
        m.db.session.commit()
        self.assertEqual(m.shop["expire"](),1)
        self.assertEqual(self.stock(),5)
        self.receive(ref)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.stock(),3)

    def test_late_payment_without_stock_does_not_credit_points(self):
        self.set_stock(2)
        ref=self.confirm_draft(self.new_draft()).get_json()["reference"]
        self.order(ref).expires_at=int(time.time())-1
        m.db.session.commit()
        m.shop["expire"]()
        self.set_stock(0)
        self.receive(ref)
        before=m.db.session.get(m.User,2).loyalty_points
        response=self.confirm(ref)
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertEqual(m.db.session.get(m.User,2).loyalty_points,before)
        self.assertEqual(self.order(ref).status,"payment_review")

    def test_out_of_stock_limits_and_admin_only(self):
        self.set_stock(0)
        result=self.request_bridge("draft",user={"id":102},key=uuid.uuid4().hex,
                                   items=[dict(cosmetic_id=1,quantity=1)])
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.set_stock(10,tid=102).status_code,403)
        self.assertEqual(self.set_stock(-1).status_code,400)
        self.assertEqual(self.set_stock(1.5).status_code,400)
        self.assertEqual(self.stock(),0)

    def test_repeated_stock_edit_cannot_restore_units_sold_since(self):
        key=uuid.uuid4().hex
        self.set_stock(5,key)
        ref=self.confirm_draft(self.new_draft()).get_json()["reference"]
        self.assertEqual(self.stock(),3)
        repeat=self.set_stock(5,key)
        self.assertTrue(repeat.get_json()["duplicate"])
        self.assertEqual(self.stock(),3)
        changed=self.set_stock(6,key)
        self.assertEqual(changed.status_code,400)
        self.assertEqual(self.stock(),3)

    def test_two_customers_cannot_reserve_last_unit(self):
        self.set_stock(2)
        drafts=[]
        for tid in (102,103):
            response=self.request_bridge("draft",user={"id":tid},key=uuid.uuid4().hex,
                                         items=[dict(cosmetic_id=1,quantity=1)])
            did=response.get_json()["draft_id"]
            quote=self.customer("quote",did,tid=tid,country="FR").get_json()["quote"]
            drafts.append((tid,did,quote["quote_hash"]))
        self.set_stock(1)
        def checkout(entry):
            tid,did,quote_hash=entry
            with m.app.test_client() as client:
                response=client.post("/api/cosmetics/customer",json=dict(
                    action="confirm",draft_id=did,init_data=init_data(tid),accepted=True,
                    contact=CONTACT,quote_hash=quote_hash))
                return response.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(checkout,drafts))
        self.assertEqual(codes.count(200),1,codes)
        self.assertEqual(self.stock(),0)
        self.assertEqual(m.shop["Order"].query.count(),1)

    def test_tracking_uses_admin_number_and_is_private(self):
        ref=self.confirm_draft(self.new_draft()).get_json()["reference"]
        self.receive(ref)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.login(1)
        result=self.client.post("/api/shop/admin/orders/"+ref+"/shipping",
                               json={"status":"shipped","tracking_number":"12345678"})
        self.assertEqual(result.status_code,200,result.get_json())
        self.login(2)
        rows=self.request_bridge("tracking",user={"id":102}).get_json()["orders"]
        self.assertEqual(rows[0]["number"],"12345678")
        self.assertEqual(rows[0]["postal_code"],"75001")
        self.assertIn("numeroExpedition=12345678",rows[0]["url"])
        self.assertIn("CodePostal=75001",rows[0]["url"])
        self.assertEqual(self.request_bridge("tracking",user={"id":103}).get_json()["orders"],[])

    def test_old_orders_without_reservation_do_not_add_units(self):
        ref=self.confirm_draft(self.new_draft()).get_json()["reference"]
        Reservation=m.cosmetics_checkout["inventory"]["Reservation"]
        m.db.session.delete(m.db.session.get(Reservation,self.order(ref).id))
        m.db.session.commit()
        before=self.stock()
        self.client.post("/api/shop/orders/"+ref+"/cancel")
        self.assertEqual(self.stock(),before)
