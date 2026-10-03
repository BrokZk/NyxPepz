import unittest
from decimal import Decimal
from unittest.mock import patch, Mock
from shop_test_helpers import ShopTests, m, tearDownModule, temp
from pathlib import Path
from real_sales import create_schema
import base64, json
from urllib.parse import urlencode
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes


class RealSalesTests(ShopTests):
    def setUp(self):
        # The original test module removes its shared temporary directory at
        # module teardown. Recreate it when discovery continues with this module.
        Path(temp.name).mkdir(parents=True, exist_ok=True)
        super().setUp()

    def manual(self, method='cash'):
        ref = self.create()
        self.login(1)
        response = self.client.post('/api/shop/admin/orders/'+ref+'/confirm-payment', json=dict(
            confirmed_total_cents=self.order(ref).total_cents, payment_method=method, note='Reçu réellement'))
        self.assertEqual(response.status_code, 200, response.json)
        return ref

    def test_unknown_is_never_zero(self):
        ref = self.manual('crypto')
        data = self.client.get('/api/shop/admin/sales/real').json
        self.assertEqual(data['metrics']['gross_cents'], 8500)
        self.assertEqual(data['metrics']['unavailable_orders'], 1)
        self.assertIsNone(data['orders'][0]['net_cents'])

    def test_zero_fee_explicit_idempotent_and_correction(self):
        ref = self.manual()
        detail=self.client.get('/api/shop/admin/orders/'+ref+'/accounting').json
        self.assertEqual(detail['payment']['net_cents'],8500)
        self.assertEqual(detail['payment']['fee_cents'],0)
        record=m.app.extensions['nyx_accounting']['PaymentRecord'].query.one()
        self.assertEqual(record.net_eur,Decimal('85'))
        result=self.client.post('/api/shop/admin/orders/'+ref+'/payment-method',json=dict(payment_method='crypto', expected_revision=1,note='Correction documentée'))
        self.assertEqual(result.status_code,200,result.json)
        detail=self.client.get('/api/shop/admin/orders/'+ref+'/accounting').json
        self.assertFalse(detail['payment']['net_is_verified'])
        self.assertEqual(len(detail['audit']),1)

    def test_callback_preserves_real_data_and_no_fake_fx(self):
        ref=self.create()
        self.assertEqual(self.receive(ref,txid='0x'+'a'*64).status_code,200)
        self.assertEqual(self.receive(ref,txid='0x'+'a'*64).status_code,200)
        self.confirm(ref);self.login(1)
        detail=self.client.get('/api/shop/admin/orders/'+ref+'/accounting').json
        self.assertEqual(len(detail['receipts']),1)
        self.assertEqual(Decimal(detail['payment']['value_forwarded_coin']),Decimal('84'))
        self.assertIsNone(detail['payment']['net_cents'])
        self.assertEqual(detail['payment']['payment_provider'],'paygate.to')

    def test_additive_migration_twice_and_backfill(self):
        ref=self.manual('crypto')
        Record=m.app.extensions['nyx_accounting']['PaymentRecord']
        Record.query.delete();m.db.session.commit()
        tables=('payment_accounting_audit','payment_receipt','payment_record')
        with m.db.engine.begin() as connection:
            for table in tables:m.db.metadata.tables[table].drop(connection)
        create_schema(m.db);create_schema(m.db)
        self.assertEqual(self.order(ref).total_cents,8500)
        runner=m.app.test_cli_runner()
        for _ in range(2):
            result=runner.invoke(args=['payments-backfill'])
            self.assertEqual(result.exit_code,0,result.output)
        self.assertEqual(Record.query.count(),1)
        self.assertIsNone(Record.query.one().net_eur)
        data=self.client.get('/api/shop/admin/sales/real').json
        self.assertEqual(data['orders'][0]['net_label'],'Net historique indisponible')

    def test_permissions_period_and_pagination(self):
        self.assertEqual(self.client.get('/api/shop/admin/sales/real').status_code,403)
        self.login(1)
        self.assertEqual(self.client.get('/api/shop/admin/sales/real?period=invalid').status_code,400)
        self.assertEqual(self.client.get('/api/shop/admin/sales/real?page=0').status_code,400)

    def test_real_rsa_signature_raw_url_and_replay(self):
        ref=self.create();order=self.order(ref)
        order.receiving_wallet='0x'+'2'*40;order.payout_wallet='0x'+'1'*40;m.db.session.commit()
        args=dict(order=ref,nonce=order.payment_nonce,address_in=order.receiving_wallet,value_coin='85',
                  value_forwarded_coin='84',coin='polygon_usdc',txid_in='0x'+'b'*64,txid_out='0x'+'c'*64,
                  address_out=json.dumps({order.payout_wallet:'0.9'}))
        raw=urlencode(args)+'&marker=hello%20world%7b'
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        signed=('https://shop.invalid/api/shop/paygate/callback?'+raw).encode()
        signature=base64.b64encode(private.sign(signed,padding.PKCS1v15(),hashes.SHA256())).decode()
        headers={'X-PayGate-Key-Id':'v1','X-PayGate-Signature':signature}
        with patch('cryptography.hazmat.primitives.serialization.load_pem_public_key',return_value=private.public_key()):
            self.assertEqual(self.client.get('/api/shop/paygate/callback?'+raw.replace('value_coin=85','value_coin=86'),headers=headers).status_code,403)
            first=self.client.get('/api/shop/paygate/callback?'+raw,headers=headers)
            self.assertEqual(first.status_code,200,first.json)
            self.assertTrue(self.client.get('/api/shop/paygate/callback?'+raw,headers=headers).json['duplicate'])
        receipts=m.app.extensions['nyx_accounting']['PaymentReceipt'].query.all()
        self.assertEqual(len(receipts),1)
        self.assertEqual(Decimal(receipts[0].payload['merchant_settled_coin']),Decimal('75.6'))

    def test_backfill_token_status_never_creates_euro_net(self):
        ref=self.manual('crypto');order=self.order(ref);order.ipn_token='test-only';m.db.session.commit()
        response=Mock();response.json.return_value=dict(status='paid',coin='polygon_usdc',value_coin='85',txid_out='0x'+'d'*64)
        with patch('real_sales.requests.get',return_value=response) as get:
            result=m.app.test_cli_runner().invoke(args=['payments-backfill','--recover-status'])
            self.assertEqual(result.exit_code,0,result.output)
            self.assertEqual(get.call_args.kwargs['params'],{'ipn_token':'test-only'})
        record=m.app.extensions['nyx_accounting']['PaymentRecord'].query.one()
        self.assertIsNone(record.net_eur)
        self.assertFalse(record.net_is_verified)


if __name__ == '__main__':unittest.main()
