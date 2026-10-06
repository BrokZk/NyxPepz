import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from shop_test_helpers import ShopTests, m
from admin_dashboard import bounds
from sales import PARIS
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql


def tearDownModule():
 with m.app.app_context():
  m.db.session.remove()
  m.db.engine.dispose()


class AdminControlTests(ShopTests):
 def test_admin_access(self):
  for path in ('/api/admin/dashboard', '/api/admin/protocols'):
   self.assertEqual(self.client.get(path).status_code,403)
  self.assertEqual(self.client.post('/api/admin/protocols',json={}).status_code,403)
  self.assertEqual(self.client.patch('/api/admin/protocols/1',json={}).status_code,403)
  self.assertEqual(self.client.delete('/api/admin/protocols/1').status_code,403)

 def test_migration_preserves_sources_and_edits(self):
  original=json.loads((Path(m.app.root_path)/'static/protocols.json').read_text(encoding='utf-8'))
  self.assertTrue(m.protocols['migrate']())
  public=self.client.get('/api/protocols').json
  self.assertEqual(len(public['entries']),len(original['entries']))
  self.assertEqual(public['sources'],original['sources'])
  self.assertEqual(public['entries'][0]['mix'],original['entries'][0]['mix'])
  self.login(1);pid=public['entries'][0]['id']
  self.assertEqual(self.client.patch(f'/api/admin/protocols/{pid}',json={'title':'Mon édition','active':False}).status_code,200)
  self.assertFalse(m.protocols['migrate']())
  self.assertEqual(self.client.get(f'/api/admin/protocols/{pid}').json['title'],'Mon édition')
  self.assertEqual(len(self.client.get('/api/protocols').json['entries']),len(original['entries'])-1)
  self.client.delete(f'/api/admin/protocols/{pid}')
  self.assertFalse(m.protocols['migrate']())

 def test_protocol_crud_validation_order_and_text(self):
  self.login(1)
  payload=dict(title='<script>texte</script>',category='Information',description='Description',content='Texte libre',steps=[dict(title='Étape',text='Texte')],active=True,sort_order=2,image_url='https://res.cloudinary.com/demo/image/upload/test.jpg')
  created=self.client.post('/api/admin/protocols',json=payload);self.assertEqual(created.status_code,201,created.json);pid=created.json['id']
  second=self.client.post('/api/admin/protocols',json=dict(title='Premier',category='Information',sort_order=1)).json
  self.assertEqual([p['id'] for p in self.client.get('/api/protocols').json['entries']],[second['id'],pid])
  self.assertEqual(self.client.patch(f'/api/admin/protocols/{pid}',json={'active':False}).status_code,200)
  self.assertEqual(len(self.client.get('/api/protocols').json['entries']),1)
  for bad in ({'active':'false'},{'sort_order':True},{'steps':[{'title':1,'text':'x'}]},{'image_url':'javascript:alert(1)'},{'title':''},{'unknown':1},[]):
   self.assertEqual(self.client.patch(f'/api/admin/protocols/{pid}',json=bad).status_code,400)
  self.assertEqual(self.client.get(f'/api/admin/protocols/{pid}').json['content'],'Texte libre')
  self.assertEqual(self.client.delete(f'/api/admin/protocols/{pid}').status_code,200)
  self.assertEqual(self.client.get(f'/api/admin/protocols/{pid}').status_code,404)

 def test_legacy_steps_can_be_replaced_or_cleared(self):
  m.protocols['migrate']();self.login(1);pid=self.client.get('/api/admin/protocols').json[0]['id']
  result=self.client.patch(f'/api/admin/protocols/{pid}',json={'steps':[]}).json
  self.assertNotIn('mix',result)
  self.assertIn('reference',result)

 def test_import_is_atomic_and_cli_is_repeatable(self):
  with patch('protocols.json.loads',return_value={'categories':[], 'entries':[{'title':'Incomplete'}]}):
   with self.assertRaises(KeyError):m.protocols['migrate']()
  self.assertIsNone(m.db.session.get(m.CatalogUpdate,'protocols-editorial-import-v1'))
  self.assertEqual(m.protocols['Model'].query.count(),0)
  runner=m.app.test_cli_runner()
  self.assertEqual(runner.invoke(args=['protocols-migrate']).exit_code,0)
  count=m.protocols['Model'].query.count()
  self.assertEqual(runner.invoke(args=['protocols-migrate']).exit_code,0)
  self.assertEqual(m.protocols['Model'].query.count(),count)
  ddl=str(CreateTable(m.protocols['Model'].__table__).compile(dialect=postgresql.dialect()))
  self.assertIn('CREATE TABLE protocol',ddl)
  self.assertIn('steps JSON NOT NULL',ddl)

 def test_real_totals_methods_and_unknown_history(self):
  ref=self.create();self.receive(ref);self.assertEqual(self.confirm(ref).status_code,200)
  old=self.create();self.order(old).status='shipped';self.order(old).tracking_number='';m.db.session.commit()
  self.login(1)
  alltime=self.client.get('/api/admin/dashboard?period=all').json
  self.assertEqual(alltime['gross_cents'],17000)
  self.assertIsNone(alltime['fees_cents']);self.assertIsNone(alltime['net_cents'])
  self.assertEqual(alltime['undated_orders'],1);self.assertEqual(alltime['missing_tracking'],1)
  self.assertEqual(alltime['payment_split']['crypto']['gross_cents'],8500)
  self.assertEqual(alltime['payment_split']['unknown']['gross_cents'],8500)
  today=self.client.get('/api/admin/dashboard?period=today').json
  self.assertEqual(today['gross_cents'],8500);self.assertEqual(today['orders_today'],2)
  for period in ('7d','30d'):
   self.assertEqual(self.client.get('/api/admin/dashboard?period='+period).json['gross_cents'],8500)
  self.assertEqual(self.client.get('/api/admin/dashboard?period=nope').status_code,400)
  m.db.session.add(m.shop['PaymentRecord'](order_id=self.order(ref).id,revision=2,method='cash',note='Vérifié',source='admin_correction'))
  m.db.session.commit()
  data=self.client.get('/api/admin/dashboard?period=all').json
  self.assertEqual(data['payment_split']['other']['gross_cents'],8500)
  self.assertEqual(data['payment_split']['crypto']['orders'],0)

 def test_alerts_stock_clients_preparation(self):
  ref=self.create();order=self.order(ref);order.status='gifted'
  m.db.session.get(m.Product,1).stock=3;m.db.session.commit();self.login(1)
  data=self.client.get('/api/admin/dashboard?period=all').json
  self.assertEqual(data['gross_cents'],0);self.assertEqual(data['preparing'],1)
  self.assertEqual(data['low_stock'][0]['stock'],3);self.assertEqual(data['clients'],3)
  m.db.session.add(m.shop['Preparation'](order_id=order.id,prepared_at=1,prepared_by_telegram_id=101));m.db.session.commit()
  self.assertEqual(self.client.get('/api/admin/dashboard').json['preparing'],0)
  order.status='payment_review';m.db.session.commit()
  self.assertEqual(self.client.get('/api/admin/dashboard').json['payment_review'],1)

 def test_paris_periods_across_dst(self):
  now=datetime(2026,10,26,12,tzinfo=timezone.utc)
  start,end=bounds('7d',now)
  self.assertEqual(start.astimezone(PARIS).day,20)
  self.assertEqual(start.hour,22);self.assertEqual(end,now)
  today,_=bounds('today',now);self.assertEqual(today.hour,23)
  self.assertEqual(bounds('all',now),(None,None))

 def test_dashboard_details_auth_validation_and_pagination(self):
  self.assertEqual(self.client.get('/api/admin/dashboard/details?metric=clients').status_code,403)
  self.login(1)
  for params in ('metric=nope','metric=clients&period=nope','metric=clients&page=0','metric=clients&page=abc'):
   self.assertEqual(self.client.get('/api/admin/dashboard/details?'+params).status_code,400)
  for i in range(22):
   m.db.session.add(m.User(telegram_id=2000+i,referral_code=f'D{i:04}',first_name=f'Client {i}'))
  m.db.session.commit()
  first=self.client.get('/api/admin/dashboard/details?metric=clients').json
  second=self.client.get('/api/admin/dashboard/details?metric=clients&page=2').json
  self.assertEqual(first['total'],25);self.assertEqual(len(first['items']),20)
  self.assertEqual(len(second['items']),5)
  self.assertFalse({u['id'] for u in first['items']} & {u['id'] for u in second['items']})
  response=self.client.get('/api/admin/dashboard/details?metric=clients&page=999')
  self.assertEqual(response.json['page'],2);self.assertEqual(response.headers['Cache-Control'],'no-store')

 def test_dashboard_details_match_every_counter(self):
  refs=[self.create() for _ in range(3)]
  self.order(refs[0]).status='paid'
  self.order(refs[1]).status='payment_review'
  self.order(refs[2]).status='shipped';self.order(refs[2]).tracking_number=' '
  m.db.session.get(m.Product,1).stock=3
  m.db.session.commit();self.login(1)
  mapping={'orders_today':'orders_today','orders_in_period':'orders_in_period','preparing':'preparing',
           'clients':'clients','clients_in_period':'clients_in_period','payment_review':'payment_review','missing_tracking':'missing_tracking','gross':'paid_orders'}
  for period in ('today','7d','30d','all'):
   counters=self.client.get('/api/admin/dashboard?period='+period).json
   for metric,counter in mapping.items():
    response=self.client.get(f'/api/admin/dashboard/details?metric={metric}&period={period}')
    self.assertEqual(response.status_code,200,response.json)
    self.assertEqual(response.json['total'],counters[counter],(period,metric))
   self.assertEqual(self.client.get(f'/api/admin/dashboard/details?metric=low_stock&period={period}').json['total'],len(counters['low_stock']))
  paid=self.client.get('/api/admin/dashboard/details?metric=gross&period=all').json
  self.assertEqual(sum(row['total_cents'] for row in paid['items']),17000)
  self.assertTrue(all(row['name']=='Alice Test' for row in paid['items']))

 def test_details_periods_filter_dates_not_alerts(self):
  ref=self.create();order=self.order(ref)
  order.created_at=int((datetime.now(timezone.utc)-timedelta(days=10)).timestamp())
  order.status='paid'
  m.db.session.add(m.ConfirmedOrderEvent(external_order_id=ref,user_id=2,loyalty_points=80,
                                      processed_at=datetime.now(timezone.utc)-timedelta(days=10)))
  user=m.db.session.get(m.User,2);user.created_at=datetime.now(timezone.utc)-timedelta(days=10)
  m.db.session.commit();self.login(1)
  for metric in ('orders_today','orders_in_period','gross'):
   self.assertEqual(self.client.get(f'/api/admin/dashboard/details?metric={metric}&period=7d').json['total'],0)
  for metric in ('orders_in_period','gross'):
   self.assertEqual(self.client.get(f'/api/admin/dashboard/details?metric={metric}&period=30d').json['total'],1)
  self.assertEqual(self.client.get('/api/admin/dashboard/details?metric=preparing&period=today').json['total'],1)
  self.assertEqual(self.client.get('/api/admin/dashboard/details?metric=clients_in_period&period=7d').json['total'],2)
  self.assertEqual(self.client.get('/api/admin/dashboard/details?metric=clients_in_period&period=30d').json['total'],3)
