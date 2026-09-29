import unittest, uuid, os
from unittest.mock import patch, Mock
from shop_test_helpers import ShopTests, m, CONTACT, tearDownModule


class PacksTests(ShopTests):
 def setUp(self):
  super().setUp()
  m.db.session.add(m.PromoPack(id=1,title='Pack Reta 10 + GHK-CU',subtitle='Retatrutide 10 mg + GHK-CU',price=110,active=True))
  m.db.session.commit();m.pack_shop['seed']()
 def bundle_payload(self,items=None):
  items=items or [dict(pack_id=1,quantity=1)]
  quote=self.quote(items);self.assertEqual(quote.status_code,200,quote.json)
  return dict(items=items,contact=CONTACT,quote_hash=quote.json['quote_hash'])
 def bundle_create(self,items=None):
  r=self.client.post('/api/shop/orders',json=self.bundle_payload(items),headers={'Idempotency-Key':uuid.uuid4().hex})
  self.assertEqual(r.status_code,201,r.json);return r.json['order']['reference']
 def test_pack_price_and_inventory_cancel(self):
  ref=self.bundle_create([dict(pack_id=1,quantity=2),dict(product_id=1,quantity=1)])
  self.assertEqual(self.order(ref).subtotal_cents,30000)
  self.assertEqual(m.db.session.get(m.Product,1).stock,7)
  self.assertEqual(m.db.session.get(m.Product,2).stock,8)
  self.client.post('/api/shop/orders/'+ref+'/cancel')
  self.assertEqual(m.db.session.get(m.Product,1).stock,10)
  self.assertEqual(m.db.session.get(m.Product,2).stock,10)
 def test_shared_stock_all_or_nothing(self):
  r=self.quote([dict(pack_id=1,quantity=6),dict(product_id=1,quantity=5)])
  self.assertEqual(r.status_code,400)
  self.assertEqual(m.db.session.get(m.Product,1).stock,10)
 def test_pack_price_changed_since_quote(self):
  payload=self.bundle_payload();m.db.session.get(m.PromoPack,1).price=109;m.db.session.commit()
  r=self.client.post('/api/shop/orders',json=payload,headers={'Idempotency-Key':uuid.uuid4().hex})
  self.assertEqual(r.status_code,409)
 def test_snapshot_survives_pack_deletion(self):
  ref=self.bundle_create();self.login(1)
  self.assertEqual(self.client.delete('/api/admin/packs/1').status_code,200)
  self.login(2);self.client.post('/api/shop/orders/'+ref+'/cancel')
  self.assertEqual(m.db.session.get(m.Product,1).stock,10)
  self.assertEqual(m.db.session.get(m.Product,2).stock,10)
 def test_late_bundle_payment_credits_pack_price(self):
  ref=self.bundle_create();self.order(ref).expires_at=1;m.db.session.commit();m.shop['expire']()
  self.receive(ref);self.assertEqual(self.confirm(ref).status_code,200)
  self.assertEqual(m.db.session.get(m.Product,1).stock,9)
  self.assertEqual(m.db.session.get(m.Product,2).stock,9)
  self.assertEqual(m.db.session.get(m.User,2).loyalty_points,910)
 def test_bad_and_unconfigured_bundles(self):
  for items in [[dict(pack_id=1,product_id=1,quantity=1)],[dict(pack_id=1,quantity=1),dict(pack_id=1,quantity=1)],[dict(pack_id=True,quantity=1)]]:
   self.assertEqual(self.quote(items).status_code,400)
  self.login(1);r=self.client.post('/api/admin/packs',json=dict(title='Nouveau',price=25))
  self.assertEqual(r.status_code,201,r.json);self.login(2)
  self.assertEqual(self.quote([dict(pack_id=r.json['id'],quantity=1)]).status_code,400)
 def test_composition_and_auth(self):
  self.assertEqual(self.client.patch('/api/admin/packs/1',json=dict(price=1)).status_code,403)
  self.login(1)
  for parts in [[dict(product_id=1,quantity=0)],[dict(product_id=999,quantity=1)],[dict(product_id=1,quantity=True)]]:
   self.assertEqual(self.client.patch('/api/admin/packs/1',json=dict(components=parts)).status_code,400)
  self.assertEqual(self.client.patch('/api/admin/packs/1',json=dict(components=[dict(product_id=1,quantity=2)])).status_code,200)
  self.assertEqual(self.client.get('/api/packs').json[0]['stock'],5)
 def test_admin_groups_and_cursor(self):
  refs=[self.create() for _ in range(3)]
  self.order(refs[0]).status='paid';self.order(refs[1]).status='shipped';self.order(refs[2]).status='delivered';m.db.session.commit()
  self.login(1)
  for group,ref in zip(['action','shipping','history'],refs):
   self.assertEqual([o['reference'] for o in self.client.get('/api/shop/admin/orders?group='+group).json['orders']],[ref])
  self.assertEqual(self.client.get('/api/shop/admin/orders?group=invalid').status_code,400)
  self.login(2);self.assertEqual(self.client.get('/api/shop/admin/orders?group=history').status_code,403)
 def test_launcher_one_button_and_old_callback(self):
  calls=[]
  events=[{'update_id':1,'message':{'chat':{'id':102,'type':'private'},'text':'/start'}},
          {'update_id':2,'callback_query':{'id':'cb','data':'confirmer_commande','message':{'message_id':4,'chat':{'id':102,'type':'private'}}}}]
  def post(url,**kwargs):
   method=url.rsplit('/',1)[1];calls.append((method,kwargs['json']))
   result=events if method=='getUpdates' else {} if method=='getWebhookInfo' else True
   return Mock(ok=True,status_code=200,json=lambda:{'ok':True,'result':result})
  with patch.dict(os.environ,TELEGRAM_LAUNCHER_ENABLED='1',TELEGRAM_BOT_TOKEN='test'),patch('bot_launcher.requests.post',side_effect=post):
   m.shop['launcher_tick']()
  for method,data in calls:
   if method in ('sendMessage','editMessageReplyMarkup'):
    buttons=data['reply_markup']['inline_keyboard'];self.assertEqual(len(buttons),1);self.assertEqual(buttons[0][0]['text'],'🌙 Ouvrir NyxPepz')
  self.assertEqual(m.shop['Order'].query.count(),0)
  self.assertEqual(m.db.session.execute(m.db.text('SELECT offset FROM telegram_launcher_state')).scalar(),3)

 def test_order_pages_preserve_older_active_orders(self):
  ref=self.create();order=self.order(ref);Order=m.shop['Order']
  fields={c.name:getattr(order,c.name) for c in Order.__table__.columns if c.name not in ('id','reference','checkout_key')}
  for index in range(55):
   m.db.session.add(Order(**fields,reference='PAGE-'+str(index),checkout_key='page-'+str(index)))
  m.db.session.commit();self.login(1)
  first=self.client.get('/api/shop/admin/orders?group=action').json
  self.assertEqual(len(first['orders']),50);self.assertIsNotNone(first['next_before'])
  second=self.client.get('/api/shop/admin/orders?group=action&before='+str(first['next_before'])).json
  self.assertEqual(len(second['orders']),6);self.assertIsNone(second['next_before'])
  references=[o['reference'] for o in first['orders']+second['orders']]
  self.assertEqual(len(set(references)),56);self.assertIn(ref,references)


if __name__=='__main__':
 # Run only new scenarios; the legacy suite is executed separately.
 names=[name for name in PacksTests.__dict__ if name.startswith('test_')]
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(PacksTests(n) for n in names))
 with m.app.app_context():
  m.db.session.remove();m.db.engine.dispose()
 raise SystemExit(not result.wasSuccessful())
