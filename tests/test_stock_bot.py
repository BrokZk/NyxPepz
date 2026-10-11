import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("stock_bot_test",ROOT/"catalog_bot/bot.py")
bot=importlib.util.module_from_spec(spec);spec.loader.exec_module(bot)


class StockBotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tests")
        self.store=bot.SelectionStore(str(Path(self.temp.name)/"state.sqlite3"))
        bot.setup_commerce(self.store);bot.setup_ui(self.store)
        self.admin={"id":8843973247}
        self.customer={"id":123,"first_name":"Alice"}
        self.values={}
        self.calls=[]
        self.old_bridge=bot.bridge
        bot.bridge=self.bridge
        bot.screen("admin:new",[],self.admin,self.store)
        bot.admin_text("Crème",self.admin,self.store)
        bot.admin_text("10",self.admin,self.store)
        bot.screen("admin:category:1",[],self.admin,self.store)
        bot.screen("admin:confirm",[],self.admin,self.store)
        self.pid=bot.products(self.store)[0][0]
        self.values[self.pid]=0

    def tearDown(self):
        bot.bridge=self.old_bridge
        self.store.db.close();self.temp.cleanup()

    def bridge(self,action,**payload):
        self.calls.append((action,payload))
        if action=="stocks":
            return {"stocks":[{"id":key,"available":value} for key,value in self.values.items()]}
        if action=="set_stock":
            self.values[payload["product_id"]]=payload["quantity"]
            return {"available":payload["quantity"],"duplicate":False}
        if action=="profile":
            return {"points":10,"referral_points":2.1,"referral_code":"ABCDE"}
        if action=="tracking":
            return {"orders":[{"reference":"NYX-TEST","number":"12345678","postal_code":"75001",
                              "url":"https://www.mondialrelay.fr/suivi-de-colis/?numeroExpedition=12345678&CodePostal=75001"}]}
        return {"ok":True}

    def test_stock_menu_and_admin_permission(self):
        denied=bot.screen(f"stock:product:{self.pid}",[],self.customer,self.store)
        self.assertIn("réservé",denied[0])
        self.assertEqual(bot.draft(self.store),{})
        bot.screen(f"stock:product:{self.pid}",[],self.admin,self.store)
        bad=bot.admin_text("2,5",self.admin,self.store)
        self.assertIn("entier",bad[0])
        bot.admin_text("2",self.admin,self.store)
        bot.screen("stock:confirm:"+bot.draft(self.store)["key"],[],self.admin,self.store)
        self.assertEqual(self.values[self.pid],2)
        request=next(payload for action,payload in self.calls if action=="set_stock")
        self.assertEqual(request["user"]["id"],8843973247)
        self.assertEqual(len(request["key"]),32)

    def test_out_of_stock_is_visible_and_cannot_be_added(self):
        category=bot.screen("category:1",[],self.customer,self.store)
        self.assertIn("RUPTURE DE STOCK",str(category[1]))
        card=bot.screen(f"cosave:{self.pid}",[],self.customer,self.store)
        self.assertIn("RUPTURE DE STOCK",card[0])
        self.assertNotIn("Ajouter au panier",str(card[1]))
        self.assertEqual(bot.commerce_cart(self.store,123),[])

    def test_old_confirmation_cannot_apply_a_new_stock_edit(self):
        bot.screen(f"stock:product:{self.pid}",[],self.admin,self.store)
        bot.admin_text("5",self.admin,self.store)
        old=bot.draft(self.store)["key"]
        bot.screen(f"stock:product:{self.pid}",[],self.admin,self.store)
        bot.admin_text("2",self.admin,self.store)
        current=bot.draft(self.store)["key"]
        self.assertNotEqual(old,current)
        expired=bot.screen("stock:confirm:"+old,[],self.admin,self.store)
        self.assertIn("expiré",expired[0])
        self.assertEqual(self.values[self.pid],0)
        bot.screen("stock:confirm:"+current,[],self.admin,self.store)
        self.assertEqual(self.values[self.pid],2)

    def test_cart_quantity_cannot_exceed_available(self):
        self.values[self.pid]=2
        for _ in range(3):
            bot.screen(f"cosave:{self.pid}",[],self.customer,self.store)
        self.assertEqual(bot.commerce_cart(self.store,123)[0][4],2)
        self.values[self.pid]=0
        bot.screen(f"quantity:{self.pid}:down",[],self.customer,self.store)
        self.assertEqual(bot.commerce_cart(self.store,123)[0][4],1)

    def test_profile_tracking_button_and_copied_numbers(self):
        profile=bot.screen("profile",[],self.customer,self.store)
        self.assertIn("Mondial Relay",str(profile[1]))
        tracking=bot.screen("tracking",[],self.customer,self.store)
        self.assertIn("12345678",tracking[0])
        self.assertIn("75001",tracking[0])
        self.assertIn("copy_text",str(tracking[1]))
        request=next(payload for action,payload in self.calls if action=="tracking")
        self.assertEqual(request["user"]["id"],123)


if __name__=="__main__":unittest.main()
