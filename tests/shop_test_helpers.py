import os, sys, tempfile, unittest, uuid, time, json, base64
from pathlib import Path
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
temp=tempfile.TemporaryDirectory()
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(temp.name)/'shop.db').replace('\\','/'),
 SHOP_ENABLED='1',PAYGATE_ENABLED='1',PAYGATE_WALLET='0x'+'1'*40,SHOP_PUBLIC_URL='https://shop.invalid',
 ADMIN_TELEGRAM_IDS='101',ORDER_WEBHOOK_SECRET='test-secret',SECRET_KEY='test-session-key')
sys.path.insert(0,str(ROOT))
import app as m
from shop import REWARDS
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives import serialization,hashes

CONTACT=dict(first_name='Alice',last_name='Test',email='alice@example.com',phone='+33612345678',address='1 rue Exemple',address_extra='',postal_code='75001',city='Paris',country='FR',discovery='Telegram')
class ShopTests(unittest.TestCase):
 def setUp(self):
  self.ctx=m.app.app_context();self.ctx.push();m.db.drop_all();m.db.create_all()
  m.db.session.add_all([m.User(id=1,telegram_id=101,referral_code='ADMIN',loyalty_points=0),m.User(id=2,telegram_id=102,referral_code='ALICE',loyalty_points=800),m.User(id=3,telegram_id=103,referral_code='BOBBB',loyalty_points=0)])
  m.db.session.add_all([m.Product(id=1,name='Retatrutide',format='10 mg',price=80,category='Perte de graisse',stock=10),m.Product(id=2,name='GHK-CU',format='50 mg',price=40,category='Beauté · peau',stock=10)])
  m.db.session.commit();self.client=m.app.test_client();self.login(2)
 def tearDown(self):m.db.session.remove();self.ctx.pop()
 def login(self,uid):
  with self.client.session_transaction() as session:session['uid']=uid
 def quote(self,items=None,country='FR',reward=0):return self.client.post('/api/shop/quote',json=dict(items=items or [dict(product_id=1,quantity=1)],country=country,reward_points=reward))
 def payload(self,reward=0,ref='',country='FR',quantity=1):
  items=[dict(product_id=1,quantity=quantity)];q=self.quote(items,country,reward).get_json();contact={**CONTACT,'country':country,'postal_code':'1000' if country=='BE' else '28001' if country=='ES' else '75001'}
  return dict(items=items,contact=contact,reward_points=reward,referral_code=ref,quote_hash=q['quote_hash'])
 def create(self,**kwargs):
  p=self.payload(**kwargs);r=self.client.post('/api/shop/orders',json=p,headers={'Idempotency-Key':uuid.uuid4().hex});self.assertEqual(r.status_code,201,r.get_json());return r.get_json()['order']['reference']
 def order(self,ref):return m.shop['Order'].query.filter_by(reference=ref).one()
 def receive(self,ref,txid=None,signature=True):
  order=self.order(ref);order.receiving_wallet='0x'+'2'*40;order.payout_wallet='0x'+'1'*40;order.encrypted_wallet='abc';m.db.session.commit()
  args=dict(order=ref,nonce=order.payment_nonce,address_in=order.receiving_wallet,value_coin='85',value_forwarded_coin='84',coin='polygon_usdc',txid_in=txid or '0x'+uuid.uuid4().hex,address_out=json.dumps({order.payout_wallet:'1'}))
  with patch.dict(m.app.view_functions['payment_callback'].__globals__,{}):
   with patch('cryptography.hazmat.primitives.serialization.load_pem_public_key') as key:
    if not signature:key.return_value.verify.side_effect=ValueError('bad signature')
    return self.client.get('/api/shop/paygate/callback',query_string=args,headers={'X-PayGate-Key-Id':'v1','X-PayGate-Signature':base64.b64encode(b'test').decode()})
 def confirm(self,ref):
  self.login(1);order=self.order(ref);r=self.client.post('/api/shop/admin/orders/'+ref+'/confirm-payment',json=dict(confirmed_total_cents=order.total_cents,note='PayGate gross EUR amount verified'));self.login(2);return r

def tearDownModule():
 with m.app.app_context():
  m.db.session.remove();m.db.engine.dispose()
 temp.cleanup()
