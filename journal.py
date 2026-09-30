"""Private, manually entered journal. No dosing logic or external exports."""
import calendar
import re
from datetime import date, time
from decimal import Decimal, InvalidOperation
from uuid import UUID
from urllib.parse import urlsplit
from flask import jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def install_journal(app, db, Product, current_user):
 class JournalEntry(db.Model):
  id=db.Column(db.Integer,primary_key=True)
  user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False)
  client_id=db.Column(db.String(36),nullable=False)
  # Snapshot survives product edits/deletion. No relation to stock or orders.
  product_id=db.Column(db.Integer,nullable=False)
  product_name=db.Column(db.String(120),nullable=False)
  product_format=db.Column(db.String(80),nullable=False,default='')
  day=db.Column(db.Date,nullable=False)
  local_time=db.Column(db.String(5),nullable=False)
  amount=db.Column(db.String(32),nullable=False)
  unit=db.Column(db.String(12),nullable=False)
  status=db.Column(db.String(12),nullable=False)
  note=db.Column(db.String(1000),nullable=False,default='')
  version=db.Column(db.Integer,nullable=False,default=1)
  __table_args__=(db.UniqueConstraint('user_id','client_id',name='uq_journal_client'),db.Index('ix_journal_user_day','user_id','day'))

 def output(row):
  return dict(id=row.id,product_id=row.product_id,product_name=row.product_name,product_format=row.product_format,
   date=row.day.isoformat(),time=row.local_time,amount=row.amount,unit=row.unit,status=row.status,note=row.note,version=row.version)

 def failure():
  db.session.rollback()
  return jsonify(error='Journal temporairement indisponible. Réessayez.'),503

 @app.before_request
 def journal_origin():
  if (request.path.startswith('/api/journal') or request.path=='/api/weights') and request.method in ('POST','PATCH','DELETE'):
   origin=request.headers.get('Origin')
   if origin:
    # Render terminates TLS upstream: compare the browser host, not WSGI's scheme.
    try:
     parsed=urlsplit(origin)
     same_host=parsed.scheme in ('http','https') and parsed.netloc.lower()==request.host.lower()
    except ValueError:same_host=False
    if not same_host:return jsonify(error='Origine de la requête refusée.'),403

 @app.after_request
 def journal_private(response):
  if request.path.startswith('/api/journal') or request.path=='/api/weights':
   response.headers['Cache-Control']='private, no-store'
   response.vary.add('Cookie')
  return response

 def values(data, old=None):
  allowed={'product_id','date','time','amount','unit','status','note','client_id','version'}
  if not isinstance(data,dict) or set(data)-allowed:raise ValueError('Données du journal invalides.')
  pid=data.get('product_id')
  if type(pid) is not int:raise ValueError('Choisissez un produit.')
  product=db.session.get(Product,pid)
  if old and old.product_id==pid:
   name,fmt=old.product_name,old.product_format
  elif product and product.active and product.category!='Accessoires':name,fmt=product.name,product.format or ''
  else:raise ValueError('Ce produit n’est plus disponible. Choisissez un autre produit.')
  day_text=data.get('date','');clock=data.get('time','')
  if not isinstance(day_text,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day_text):raise ValueError('Date invalide.')
  day=date.fromisoformat(day_text)
  if not 1900<=day.year<=2100:raise ValueError('Date hors plage.')
  if not isinstance(clock,str) or not re.fullmatch(r'\d{2}:\d{2}',clock):raise ValueError('Heure invalide.')
  time.fromisoformat(clock)
  raw=data.get('amount')
  if not isinstance(raw,str) or not re.fullmatch(r'\d{1,7}(?:[.,]\d{1,6})?',raw.strip()):raise ValueError('Saisissez une quantité positive (6 décimales maximum).')
  try:amount=Decimal(raw.strip().replace(',','.'))
  except InvalidOperation:raise ValueError('Quantité invalide.')
  if not 0<amount<=1000000:raise ValueError('Quantité hors plage.')
  unit=data.get('unit');status=data.get('status');note=data.get('note','')
  if unit not in ('mg','mcg','mL','U-100'):raise ValueError('Unité invalide.')
  if status not in ('planned','done'):raise ValueError('Statut invalide.')
  if not isinstance(note,str) or len(note)>1000:raise ValueError('La note est limitée à 1 000 caractères.')
  return dict(product_id=pid,product_name=name,product_format=fmt,day=day,local_time=clock,
   amount=format(amount.normalize(),'f'),unit=unit,status=status,note=note.strip())

 @app.get('/api/journal')
 def journal_list():
  user=current_user()
  if not user:return jsonify(error='Ouvrez l’application depuis votre compte Telegram.'),401
  month=request.args.get('month','')
  try:
   if not re.fullmatch(r'\d{4}-\d{2}',month):raise ValueError()
   start=date.fromisoformat(month+'-01')
   if not 1900<=start.year<=2100:raise ValueError()
   end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1])
  except ValueError:return jsonify(error='Mois invalide.'),400
  try:
   rows=JournalEntry.query.filter(JournalEntry.user_id==user.id,JournalEntry.day.between(start,end)).order_by(JournalEntry.day,JournalEntry.local_time,JournalEntry.id).all()
   return jsonify(entries=[output(row) for row in rows])
  except SQLAlchemyError:return failure()

 @app.post('/api/journal')
 def journal_create():
  user=current_user()
  if not user:return jsonify(error='Non authentifié.'),401
  data=request.get_json(silent=True)
  try:
   vals=values(data)
   client_id=str(UUID(data.get('client_id','')))
  except (ValueError,TypeError,AttributeError):return jsonify(error='Vérifiez le produit, la date, l’heure et la quantité saisis.'),400
  try:
   existing=JournalEntry.query.filter_by(user_id=user.id,client_id=client_id).first()
   if existing:
    if all(getattr(existing,k)==v for k,v in vals.items()):return jsonify(entry=output(existing)),200
    return jsonify(error='Cette entrée a déjà été enregistrée. Actualisez le journal.'),409
   row=JournalEntry(user_id=user.id,client_id=client_id,**vals)
   db.session.add(row);db.session.commit()
   return jsonify(entry=output(row)),201
  except IntegrityError:
   db.session.rollback()
   return jsonify(error='Enregistrement déjà reçu. Actualisez le journal avant de réessayer.'),409
  except SQLAlchemyError:return failure()

 @app.route('/api/journal/<int:entry_id>',methods=['PATCH','DELETE'])
 def journal_change(entry_id):
  user=current_user()
  if not user:return jsonify(error='Non authentifié.'),401
  try:
   row=JournalEntry.query.filter_by(id=entry_id,user_id=user.id).first()
   if not row:return jsonify(error='Entrée introuvable.'),404
   data=request.get_json(silent=True)
   if not isinstance(data,dict) or type(data.get('version')) is not int:return jsonify(error='Version manquante. Actualisez le journal.'),400
   query=JournalEntry.query.filter_by(id=entry_id,user_id=user.id,version=data['version'])
   if request.method=='DELETE':count=query.delete(synchronize_session=False)
   else:
    try:vals=values(data,row)
    except (ValueError,TypeError):return jsonify(error='Vérifiez les valeurs saisies.'),400
    count=query.update({**vals,'version':data['version']+1},synchronize_session=False)
   if not count:
    db.session.rollback()
    return jsonify(error='Cette entrée a changé sur un autre appareil. Actualisez le journal.'),409
   db.session.commit()
   return jsonify(ok=True) if request.method=='DELETE' else jsonify(entry=output(db.session.get(JournalEntry,entry_id)))
  except SQLAlchemyError:return failure()

 return JournalEntry
