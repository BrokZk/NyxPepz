"""No real Telegram call, payment or production database."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nyx_custom_ui", ROOT / "catalog_bot/bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


class PersonnalisationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        assert Path(self.temp.name).resolve().is_relative_to((ROOT / "tests").resolve())
        self.path = str(Path(self.temp.name) / "test.sqlite3")
        self.store = bot.SelectionStore(self.path)
        bot.setup_commerce(self.store)
        bot.setup_ui(self.store)
        self.admin = {"id":8843973247}
        self.customer = {"id":123}
        self.bridge = bot.bridge
        bot.bridge = lambda *args, **kwargs: {"ok":True}

    def tearDown(self):
        bot.bridge = self.bridge
        self.store.db.close()
        self.temp.cleanup()

    def test_labels_are_private_to_admin_and_persistent(self):
        bot.screen("ui:label:catalog", [], self.customer, self.store)
        self.assertEqual(bot.draft(self.store), {})
        bot.screen("ui:label:catalog", [], self.admin, self.store)
        bot.admin_text("Nos soins", self.admin, self.store)
        menu = bot.screen("menu", [], self.customer, self.store)[1]
        self.assertEqual(menu["inline_keyboard"][0][0]["text"], "🛍 Nos soins")
        self.store.db.close()
        self.store = bot.SelectionStore(self.path)
        bot.setup_ui(self.store)
        self.assertEqual(bot.ui_label(self.store,"catalog"), "🛍 Nos soins")

    def test_categories_keep_products_and_cart(self):
        bot.screen("ui:newcat", [], self.admin, self.store)
        bot.admin_text("Soins", self.admin, self.store)
        cid = next(cid for cid,name in bot.categories(self.store) if name == "Soins")
        bot.screen("admin:new", [], self.admin, self.store)
        bot.admin_text("Crème", self.admin, self.store)
        bot.admin_text("10,50", self.admin, self.store)
        bot.screen(f"admin:category:{cid}", [], self.admin, self.store)
        bot.screen("admin:confirm", [], self.admin, self.store)
        pid = bot.products(self.store)[0][0]
        bot.screen(f"cosave:{pid}", [], self.customer, self.store)
        bot.screen(f"ui:rename:{cid}", [], self.admin, self.store)
        bot.admin_text("Soins du corps", self.admin, self.store)
        self.assertEqual(bot.products(self.store)[0][3], "Soins du corps")
        bot.screen(f"ui:delete:{cid}", [], self.admin, self.store)
        bot.screen("ui:move:1", [], self.admin, self.store)
        bot.screen("ui:confirm_delete", [], self.customer, self.store)
        self.assertIsNotNone(bot.category_by_id(self.store,cid))
        bot.screen("ui:confirm_delete", [], self.admin, self.store)
        self.assertIsNone(bot.category_by_id(self.store,cid))
        self.assertEqual(len(bot.products(self.store)), 1)
        self.assertEqual(bot.commerce_cart(self.store,123)[0][4], 1)
        self.store.db.close()
        self.store = bot.SelectionStore(self.path)
        bot.setup_ui(self.store)
        self.assertIsNone(bot.category_by_id(self.store,cid))

    def test_mini_app_has_four_navigation_buttons(self):
        for filename in ("templates/index.html","static/index.html"):
            text = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn('class="nyx-home-shortcuts"', text)
            nav = text.split('<nav class="nyx-four-nav"')[1].split("</nav>")[0]
            self.assertEqual(nav.count("<button"), 4)
            self.assertNotIn("Panier", nav)
            for label in ("Accueil","Boutique","Parrainage","Profil"):
                self.assertIn(label, nav)


if __name__ == "__main__":
    unittest.main()
