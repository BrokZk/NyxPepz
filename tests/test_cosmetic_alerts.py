"""Private alerts and alternative payment: temporary DB, fake PayGate."""
from test_cosmetics_checkout import CosmeticsTests, m


class AdminAlertTests(CosmeticsTests):
    def test_private_alerts_and_validated_payment(self):
        result = self.confirm_draft(self.new_draft())
        self.assertEqual(result.status_code, 200, result.get_json())
        ref = result.get_json()["reference"]
        notices = self.request_bridge("admin_notices").get_json()["notices"]
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["event"], "created")
        self.assertEqual(notices[0]["telegram_id"], 102)
        self.assertEqual(notices[0]["total_cents"], 2600)
        self.assertNotIn("Crème", str(notices))
        self.assertNotIn("contact", notices[0])
        self.assertEqual(self.request_bridge("admin_notices").get_json()["notices"], [])
        self.request_bridge("ack_admin_notice", id=notices[0]["id"], lease=notices[0]["lease"])
        self.receive(ref)
        self.assertEqual(m.db.session.get(m.User,2).loyalty_points,800)
        self.assertEqual(self.confirm(ref).status_code,200)
        self.assertEqual(self.confirm(ref).status_code,200)
        Notice = m.cosmetics_checkout["AdminNotice"]
        self.assertEqual(Notice.query.filter_by(event="paid").count(),1)
        self.assertEqual(m.db.session.get(m.User,2).loyalty_points,821)
        self.assertEqual(m.shop["Outbox"].query.filter_by(kind="telegram_paid").count(),0)

    def test_alternative_request_is_owned_idempotent_and_not_paid(self):
        draft = self.new_draft()
        result = self.confirm_draft(draft)
        ref = result.get_json()["reference"]
        outsider = self.request_bridge("alternate_payment",user={"id":103},draft_id=draft)
        self.assertEqual(outsider.status_code,404)
        first = self.request_bridge("alternate_payment",user={"id":102},draft_id=draft)
        again = self.request_bridge("alternate_payment",user={"id":102},draft_id=draft)
        self.assertEqual(first.status_code,200)
        self.assertTrue(again.get_json()["duplicate"])
        Notice = m.cosmetics_checkout["AdminNotice"]
        self.assertEqual(Notice.query.filter_by(event="alternate_payment").count(),1)
        self.assertEqual(self.order(ref).status,"awaiting_payment")
        self.assertEqual(m.db.session.get(m.User,2).loyalty_points,800)
