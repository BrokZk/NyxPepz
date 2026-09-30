"""Private ambassador ledger. Money is integer cents; transfers remain manual."""
import re
import time
from datetime import datetime,timezone,date
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from uuid import UUID
from urllib.parse import urlsplit
from flask import request,jsonify,session
from sqlalchemy import update,func
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from werkzeug.security import generate_password_hash,check_password_hash


def install_ambassadors(app,db,User,Order,Confirmed,current_user,require_admin):
 class Ambassador(db.Model):
  id=db.Column(db.Integer,primary_key=True)
  user_id=db.Column(db.Integer,db.ForeignKey('user.id'),unique=True,nullable=False)
  name=db.Column(db.String(80),nullable=False)
  code=db.Column(db.String(20),unique=True,nullable=False)
  password_hash=db.Column(db.Text,nullable=False)
  active=db.Column(db.Boolean,nullable=False,default=True)
  mode=db.Column(db.String(12),nullable=False,default='pending')
  auth_version=db.Column(db.Integer,nullable=False,default=1)
  failures=db.Column(db.Integer,nullable=False,default=0)
  locked_until=db.Column(db.BigInteger,nullable=False,default=0)

 class AmbassadorAttribution(db.Model):
  customer_id=db.Column(db.Integer,db.ForeignKey('user.id'),primary_key=True)
  ambassador_id=db.Column(db.Integer,db.ForeignKey('ambassador.id'),nullable=False,index=True)
  first_order_id=db.Column(db.Integer,db.ForeignKey('shop_order.id'),nullable=False,unique=True)

 class AmbassadorOrder(db.Model):
  order_id=db.Column(db.Integer,db.ForeignKey('shop_order.id'),primary_key=True)
  ambassador_id=db.Column(db.Integer,db.ForeignKey('ambassador.id'),nullable=False)
  code=db.Column(db.String(20),nullable=False)

 class AmbassadorCommission(db.Model):
  id=db.Column(db.Integer,primary_key=True)
  order_id=db.Column(db.Integer,db.ForeignKey('shop_order.id'),unique=True,nullable=False)
  ambassador_id=db.Column(db.Integer,db.ForeignKey('ambassador.id'),nullable=False,index=True)
  basis_cents=db.Column(db.BigInteger,nullable=False)
  amount_cents=db.Column(db.BigInteger,nullable=False)
  first_order=db.Column(db.Boolean,nullable=False)
  status=db.Column(db.String(12),nullable=False)
  created_at=db.Column(db.BigInteger,nullable=False)
  reason=db.Column(db.String(300),nullable=False,default='')

 class AmbassadorPayout(db.Model):
  id=db.Column(db.Integer,primary_key=True)
  ambassador_id=db.Column(db.Integer,db.ForeignKey('ambassador.id'),nullable=False,index=True)
  client_id=db.Column(db.String(36),nullable=False)
  amount_cents=db.Column(db.BigInteger,nullable=False)
  period=db.Column(db.String(7),nullable=False)
  paid_date=db.Column(db.String(10),nullable=False)
  reference=db.Column(db.String(160),nullable=False)
  created_at=db.Column(db.BigInteger,nullable=False)
  admin_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
  __table_args__=(db.UniqueConstraint('ambassador_id','client_id',name='uq_amb_payout'),)

 class AmbassadorAudit(db.Model):
  id=db.Column(db.Integer,primary_key=True)
  ambassador_id=db.Column(db.Integer,db.ForeignKey('ambassador.id'),nullable=False,index=True)
  admin_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
  action=db.Column(db.String(300),nullable=False)
  created_at=db.Column(db.BigInteger,nullable=False)

 def fail(message,status=400):
  db.session.rollback();return jsonify(error=message),status
 def now():return int(time.time())
 def audit(amb,admin,action):db.session.add(AmbassadorAudit(ambassador_id=amb.id,admin_id=admin.id,action=action,created_at=now()))
 def lock(amb):
  db.session.execute(update(Ambassador).where(Ambassador.id==amb.id).values(auth_version=Ambassador.auth_version))
  db.session.refresh(amb)
 def find(ident):return db.session.get(Ambassador,ident)
 def own():
  u=current_user()
  return Ambassador.query.filter_by(user_id=u.id).first() if u else None
 def verified(amb):
  return bool(amb and amb.active and session.get('amb_id')==amb.id and session.get('amb_version')==amb.auth_version and session.get('amb_until',0)>now())
 def config(amb):return dict(id=amb.id,user_id=amb.user_id,name=amb.name,code=amb.code,mode=amb.mode,active=amb.active,rate=10)
 def totals(amb):
  sums={status:int(value or 0) for status,value in db.session.query(AmbassadorCommission.status,func.sum(AmbassadorCommission.amount_cents)).filter_by(ambassador_id=amb.id).group_by(AmbassadorCommission.status)}
  paid=int(db.session.query(func.sum(AmbassadorPayout.amount_cents)).filter_by(ambassador_id=amb.id).scalar() or 0)
  earned=sums.get('approved',0)
  sales=int(db.session.query(func.sum(AmbassadorCommission.basis_cents)).filter(AmbassadorCommission.ambassador_id==amb.id,AmbassadorCommission.status!='void').scalar() or 0)
  customers=AmbassadorAttribution.query.filter_by(ambassador_id=amb.id).count()
  return dict(sales_cents=sales,customers=customers,earned_cents=earned,pending_cents=sums.get('pending',0),paid_cents=paid,available_cents=max(0,earned-paid),adjustment_cents=max(0,paid-earned))

 @app.before_request
 def ambassador_origin():
  if request.path.startswith(('/api/ambassador','/api/admin/ambassadors')) and request.method in ('POST','PATCH','DELETE'):
   origin=request.headers.get('Origin')
   if origin:
    try:p=urlsplit(origin);safe=p.scheme in ('http','https') and p.netloc.lower()==request.host.lower()
    except ValueError:safe=False
    if not safe:return fail('Origine refusée.',403)
 @app.after_request
 def ambassador_private(response):
  if request.path.startswith(('/api/ambassador','/api/admin/ambassadors')):
   response.headers['Cache-Control']='private, no-store';response.vary.add('Cookie')
  return response

 def prepare(user,code):
  if not isinstance(code,str) or len(code)>20:raise ValueError('Code ambassadeur invalide.')
  code=code.strip().upper()
  attribution=db.session.get(AmbassadorAttribution,user.id)
  amb=find(attribution.ambassador_id) if attribution else None
  if code:
   chosen=Ambassador.query.filter_by(code=code,active=True).first()
   if not chosen:raise ValueError('Code ambassadeur inconnu ou inactif.')
   if chosen.user_id==user.id:raise ValueError('Votre propre code ambassadeur ne peut pas être utilisé.')
   if attribution and chosen.id!=amb.id:raise ValueError('Votre compte est déjà rattaché à un autre ambassadeur.')
   if not attribution and Confirmed.query.filter_by(user_id=user.id).first():raise ValueError('Ce code est réservé aux nouveaux clients.')
   amb=chosen
  return amb if amb and amb.active else None

 def attach(order,amb):
  if amb:db.session.add(AmbassadorOrder(order_id=order.id,ambassador_id=amb.id,code=amb.code))

 def credit(order,first_paid):
  # Called inside the payment transaction, after the customer lock is acquired.
  if AmbassadorCommission.query.filter_by(order_id=order.id).first():return
  attribution=db.session.get(AmbassadorAttribution,order.user_id)
  candidate=db.session.get(AmbassadorOrder,order.id)
  if first_paid and candidate and not attribution:
   amb=find(candidate.ambassador_id)
   if not amb or amb.user_id==order.user_id:return
   lock(amb)
   if not amb.active:return
   attribution=AmbassadorAttribution(customer_id=order.user_id,ambassador_id=amb.id,first_order_id=order.id)
   db.session.add(attribution)
  elif attribution:
   amb=find(attribution.ambassador_id);lock(amb)
   if not amb.active:return
  else:return
  is_first=attribution.first_order_id==order.id
  state='approved' if is_first or amb.mode=='all' else 'excluded' if amb.mode=='first' else 'pending'
  basis=max(0,order.subtotal_cents-order.discount_cents)
  db.session.add(AmbassadorCommission(order_id=order.id,ambassador_id=amb.id,basis_cents=basis,
   amount_cents=(basis+5)//10,first_order=is_first,status=state,created_at=now()))

 @app.get('/api/ambassador/access')
 def access():
  if not current_user():return fail('Ouvrez l’application depuis Telegram.',401)
  amb=own();return jsonify(member=bool(amb and amb.active),unlocked=verified(amb))

 @app.post('/api/ambassador/login')
 def login():
  amb=own()
  if not amb or not amb.active:return fail('Accès ambassadeur non attribué à ce compte.',403)
  data=request.get_json(silent=True);password=data.get('password') if isinstance(data,dict) else None
  if not isinstance(password,str) or len(password)>128:return fail('Mot de passe invalide.')
  try:
   lock(amb)
   if amb.locked_until>now():return fail('Trop de tentatives. Réessayez dans 15 minutes.',429)
   if not check_password_hash(amb.password_hash,password):
    amb.failures+=1
    if amb.failures>=5:amb.locked_until=now()+900;amb.failures=0
    db.session.commit();return jsonify(error='Mot de passe incorrect.'),403
   amb.failures=0;amb.locked_until=0;db.session.commit()
   session.update(amb_id=amb.id,amb_version=amb.auth_version,amb_until=now()+43200)
   return jsonify(ok=True)
  except SQLAlchemyError:return fail('Connexion indisponible.',503)

 @app.post('/api/ambassador/logout')
 def logout():
  for key in ('amb_id','amb_version','amb_until'):session.pop(key,None)
  return jsonify(ok=True)

 def dashboard(amb,admin=False):
  # Only attributed orders: Telegram first name and purchased item snapshots.
  # Never return contact details, Telegram IDs, payment or journal data.
  rows=AmbassadorCommission.query.filter_by(ambassador_id=amb.id).order_by(AmbassadorCommission.created_at.desc(),AmbassadorCommission.id.desc()).limit(500).all()
  payouts=AmbassadorPayout.query.filter_by(ambassador_id=amb.id).order_by(AmbassadorPayout.id.desc()).limit(500).all()
  orders={o.id:o for o in db.session.query(Order.id,Order.reference,Order.lines,User.first_name).outerjoin(User,User.id==Order.user_id).filter(Order.id.in_([c.order_id for c in rows])).all()}
  def sale_details(c):
   order=orders.get(c.order_id)
   items=[dict(name=line.get('name') or 'Produit',format=line.get('format') or '',quantity=line.get('quantity',1),line_cents=line.get('line_cents',0)) for line in (order.lines or [])] if order else []
   return dict(customer_first_name=(order.first_name or '').strip() or 'Client Telegram',items=items,**({'order_reference':order.reference} if admin else {})) if order else dict(customer_first_name='Client Telegram',items=[])
  return dict(ambassador=config(amb),totals=totals(amb),
   commissions=[dict(id=c.id,sale='Vente '+str(c.id),basis_cents=c.basis_cents,amount_cents=c.amount_cents,first_order=c.first_order,status=c.status,date=c.created_at,reason=c.reason,**sale_details(c)) for c in rows],
   payouts=[dict(id=p.id,amount_cents=p.amount_cents,period=p.period,date=p.paid_date,reference=p.reference) for p in payouts],history_limit=500)

 @app.get('/api/ambassador/dashboard')
 def own_dashboard():
  amb=own()
  if not verified(amb):return fail('Déverrouillez votre espace ambassadeur.',403)
  return jsonify(dashboard(amb))

 @app.route('/api/admin/ambassadors',methods=['GET','POST'])
 def admin_list():
  admin=require_admin()
  if not admin:return fail('Interdit.',403)
  if request.method=='GET':return jsonify(ambassadors=[dict(**config(a),totals=totals(a)) for a in Ambassador.query.order_by(Ambassador.name).all()])
  data=request.get_json(silent=True)
  if not isinstance(data,dict):return fail('Données invalides.')
  uid=data.get('user_id');name=data.get('name');code=data.get('code');password=data.get('password')
  if type(uid) is not int or not db.session.get(User,uid):return fail('Choisissez un utilisateur déjà inscrit dans l’application.')
  if not isinstance(name,str) or not 1<=len(name.strip())<=80:return fail('Nom invalide.')
  if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9_-]{6,20}',code.strip().upper()):return fail('Code : 6 à 20 lettres ou chiffres, tirets autorisés.')
  if not isinstance(password,str) or not 12<=len(password)<=128:return fail('Mot de passe : 12 à 128 caractères.')
  try:
   a=Ambassador(user_id=uid,name=name.strip(),code=code.strip().upper(),password_hash=generate_password_hash(password))
   db.session.add(a);db.session.flush();audit(a,admin,'Création · 10 % · règle des commandes suivantes à décider');db.session.commit()
   return jsonify(ambassador=config(a)),201
  except IntegrityError:return fail('Ce compte ou ce code possède déjà un espace ambassadeur.',409)
  except SQLAlchemyError:return fail('Création indisponible.',503)

 @app.route('/api/admin/ambassadors/<int:ident>',methods=['GET','PATCH'])
 def admin_detail(ident):
  admin=require_admin()
  if not admin:return fail('Interdit.',403)
  a=find(ident)
  if not a:return fail('Ambassadeur introuvable.',404)
  if request.method=='GET':return jsonify(dashboard(a,admin=True))
  data=request.get_json(silent=True)
  if not isinstance(data,dict) or set(data)-{'mode','active','password'}:return fail('Réglage invalide.')
  try:
   lock(a)
   if 'mode' in data:
    mode=data['mode']
    if mode not in ('pending','first','all'):return fail('Règle invalide.')
    a.mode=mode
    if mode!='pending':AmbassadorCommission.query.filter_by(ambassador_id=a.id,status='pending').update({'status':'approved' if mode=='all' else 'excluded'},synchronize_session=False)
    audit(a,admin,'Règle commandes suivantes : '+mode+' · attente résolue, écritures déjà décidées conservées')
   if 'active' in data:
    if type(data['active']) is not bool:return fail('Activation invalide.')
    a.active=data['active'];a.auth_version+=1;audit(a,admin,'Activation' if a.active else 'Désactivation')
   if 'password' in data:
    password=data['password']
    if not isinstance(password,str) or not 12<=len(password)<=128:return fail('Mot de passe : 12 à 128 caractères.')
    a.password_hash=generate_password_hash(password);a.auth_version+=1;a.failures=0;a.locked_until=0;audit(a,admin,'Mot de passe remplacé')
   db.session.commit();return jsonify(ambassador=config(a))
  except SQLAlchemyError:return fail('Modification indisponible.',503)

 @app.post('/api/admin/ambassadors/<int:ident>/payouts')
 def payout(ident):
  admin=require_admin()
  if not admin:return fail('Interdit.',403)
  a=find(ident)
  if not a:return fail('Ambassadeur introuvable.',404)
  data=request.get_json(silent=True)
  try:
   if not isinstance(data,dict):raise ValueError()
   if data.get('transfer_confirmed') is not True:raise ValueError()
   raw=data.get('amount','')
   if not isinstance(raw,str) or not re.fullmatch(r'\d{1,9}(?:[.,]\d{1,2})?',raw.strip()):raise ValueError()
   cents=int((Decimal(raw.replace(',','.'))*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))
   period=data['period'];paid_date=data['date'];reference=data['reference'];key=str(UUID(data['client_id']))
   if not isinstance(period,str) or not re.fullmatch(r'\d{4}-\d{2}',period):raise ValueError()
   date.fromisoformat(period+'-01')
   if date.fromisoformat(paid_date)>datetime.now(timezone.utc).date():raise ValueError()
   if not isinstance(reference,str) or not 3<=len(reference.strip())<=160 or cents<=0:raise ValueError()
  except (ValueError,TypeError,KeyError,InvalidOperation,AttributeError):return fail('Vérifiez le montant, le mois, la date et la référence du versement.')
  try:
   lock(a)
   existing=AmbassadorPayout.query.filter_by(ambassador_id=a.id,client_id=key).first()
   if existing:
    if (existing.amount_cents,existing.period,existing.paid_date,existing.reference)!=(cents,period,paid_date,reference.strip()):return fail('Ce versement a déjà été enregistré avec d’autres valeurs.',409)
    return jsonify(ok=True,duplicate=True)
   if cents>totals(a)['available_cents']:return fail('Le versement dépasse le solde disponible.',409)
   db.session.add(AmbassadorPayout(ambassador_id=a.id,client_id=key,amount_cents=cents,period=period,paid_date=paid_date,reference=reference.strip(),created_at=now(),admin_id=admin.id))
   audit(a,admin,'Versement manuel enregistré : '+str(cents)+' centimes, période '+period)
   db.session.commit();return jsonify(ok=True),201
  except SQLAlchemyError:return fail('Versement non enregistré. Réessayez avec le même formulaire.',503)

 @app.post('/api/admin/ambassadors/<int:ident>/commissions/<int:cid>/void')
 def void_commission(ident,cid):
  admin=require_admin()
  if not admin:return fail('Interdit.',403)
  a=find(ident);data=request.get_json(silent=True);reason=data.get('reason') if isinstance(data,dict) else None
  if not a:return fail('Ambassadeur introuvable.',404)
  if not isinstance(reason,str) or not 3<=len(reason.strip())<=300:return fail('Indiquez le motif de correction (remboursement, erreur…).')
  try:
   lock(a);c=AmbassadorCommission.query.filter_by(id=cid,ambassador_id=a.id).first()
   if not c:return fail('Commission introuvable.',404)
   if c.status!='void':c.status='void';c.reason=reason.strip();audit(a,admin,'Commission '+str(cid)+' annulée : '+reason.strip())
   db.session.commit();return jsonify(ok=True)
  except SQLAlchemyError:return fail('Correction indisponible.',503)

 def linked(uid):
  return Ambassador.query.filter_by(user_id=uid).first() or db.session.get(AmbassadorAttribution,uid)
 app.extensions['nyx_ambassadors']=dict(Ambassador=Ambassador,Commission=AmbassadorCommission,Payout=AmbassadorPayout,Attribution=AmbassadorAttribution,OrderLink=AmbassadorOrder,prepare=prepare,attach=attach,credit=credit,linked=linked)
 return app.extensions['nyx_ambassadors']
