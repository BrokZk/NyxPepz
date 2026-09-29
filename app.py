import os, hmac, hashlib, json, secrets, string
from datetime import datetime, timezone
from urllib.parse import parse_qsl
import requests
from flask import Flask, jsonify, request, render_template, session
from flask_sqlalchemy import SQLAlchemy

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY",secrets.token_hex(32))
db_url=os.environ.get("DATABASE_URL","sqlite:///nyxpepz.db")
if db_url.startswith("postgres://"): db_url=db_url.replace("postgres://","postgresql+psycopg://",1)
elif db_url.startswith("postgresql://"): db_url=db_url.replace("postgresql://","postgresql+psycopg://",1)
app.config.update(SQLALCHEMY_DATABASE_URI=db_url,SQLALCHEMY_TRACK_MODIFICATIONS=False,
                  SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax")
db=SQLAlchemy(app)

class User(db.Model):
 id=db.Column(db.Integer,primary_key=True);telegram_id=db.Column(db.BigInteger,unique=True,nullable=False,index=True);username=db.Column(db.String(64));first_name=db.Column(db.String(100));referral_code=db.Column(db.String(5),unique=True,nullable=False,index=True);referred_by_user_id=db.Column(db.Integer,db.ForeignKey("user.id"));loyalty_points=db.Column(db.Integer,default=0,nullable=False);referral_points=db.Column(db.Integer,default=0,nullable=False);created_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Product(db.Model):
 id=db.Column(db.Integer,primary_key=True);name=db.Column(db.String(120),nullable=False);format=db.Column(db.String(80),default="");price=db.Column(db.Integer,nullable=False);category=db.Column(db.String(80),nullable=False,index=True);image_url=db.Column(db.Text);active=db.Column(db.Boolean,default=True,nullable=False);featured=db.Column(db.Boolean,default=False,nullable=False);sort_order=db.Column(db.Integer,default=0)
class NewsItem(db.Model):
 id=db.Column(db.Integer,primary_key=True);title=db.Column(db.String(140),nullable=False);subtitle=db.Column(db.String(200),default="");image_url=db.Column(db.Text);active=db.Column(db.Boolean,default=True,nullable=False);sort_order=db.Column(db.Integer,default=0)
class WeightEntry(db.Model):
 id=db.Column(db.Integer,primary_key=True);user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True);weight_kg=db.Column(db.Float,nullable=False);created_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Parcel(db.Model):
 id=db.Column(db.Integer,primary_key=True);user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True);tracking_number=db.Column(db.String(128),nullable=False);carrier=db.Column(db.String(64),default="mondialrelay-fr");aftership_id=db.Column(db.String(128));status=db.Column(db.String(64),default="Pending");last_checkpoint=db.Column(db.Text);updated_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc));__table_args__=(db.UniqueConstraint("user_id","tracking_number",name="uq_user_tracking"),)
class ReferralOrderEvent(db.Model):
 id=db.Column(db.Integer,primary_key=True);external_order_id=db.Column(db.String(128),unique=True,nullable=False);referred_user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False);referrer_user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False);credited_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

SEED=[
("Retatrutide","10 mg",80,"Perte de graisse","/static/reta10.webp"),("Retatrutide","15 mg",100,"Perte de graisse","/static/reta15.webp"),("Retatrutide","20 mg",120,"Perte de graisse","/static/reta20.webp"),("Retatrutide","30 mg",140,"Perte de graisse","/static/reta30.webp"),
("Tesamorelin","10 mg",80,"Perte de graisse",None),("Cagrilintide","10 mg",120,"Perte de graisse",None),("BPC-157","10 mg",50,"Régénération","/static/bpc.webp"),("Wolverine Stack","",70,"Régénération","/static/wolverine.webp"),("Semax","10 mg",50,"Régénération","/static/semax.webp"),("Selank","10 mg",50,"Régénération","/static/selank.webp"),
("DSIP","5 mg",40,"Nootropiques",None),("MOTS-C","10 mg",50,"Performance",None),("KLOW Stack","80 mg",120,"Longévité",None),("GHK-Cu","50 mg",40,"Beauté · peau","/static/ghk.webp"),("GLOW Stack","70 mg",100,"Beauté · peau","/static/glow.webp"),("Melanotan 2","10 mg",50,"Beauté · peau","/static/mt2.webp"),("Melanotan 1","10 mg",50,"Beauté · peau","/static/mt1.webp"),("5-Amino","50 mg",80,"Beauté · peau",None),("PT-141","10 mg",30,"Libido",None)]

def new_code():
 alphabet=string.ascii_uppercase+string.digits
 while True:
  code="".join(secrets.choice(alphabet) for _ in range(5))
  if not User.query.filter_by(referral_code=code).first():return code
def validate_telegram(init_data):
 token=os.environ.get("TELEGRAM_BOT_TOKEN")
 if not token or not init_data:return None
 data=dict(parse_qsl(init_data,keep_blank_values=True));received=data.pop("hash",None)
 if not received:return None
 check="\n".join(f"{k}={v}" for k,v in sorted(data.items()));secret=hmac.new(b"WebAppData",token.encode(),hashlib.sha256).digest();expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
 if not hmac.compare_digest(expected,received):return None
 try:
  if abs(datetime.now(timezone.utc).timestamp()-int(data.get("auth_date","0")))>86400:return None
  return json.loads(data["user"])
 except Exception:return None
def current_user():return db.session.get(User,session.get("uid")) if session.get("uid") else None
def is_admin(u):
 ids={x.strip() for x in os.environ.get("ADMIN_TELEGRAM_IDS","").split(",") if x.strip()}
 return bool(u and str(u.telegram_id) in ids)
def product_json(p):return {"id":p.id,"name":p.name,"format":p.format,"price":p.price,"cat":p.category,"image_url":p.image_url,"active":p.active,"featured":p.featured,"sort_order":p.sort_order}
def require_admin():
 u=current_user()
 return u if is_admin(u) else None

@app.get("/")
def index():return render_template("index.html")
@app.get("/health")
def health():return jsonify(ok=True)
@app.post("/api/auth/telegram")
def auth():
 tg=validate_telegram((request.json or {}).get("initData",""))
 if not tg and os.environ.get("DEV_MODE")=="1":tg={"id":999001,"first_name":"Nyx","username":"demo"}
 if not tg:return jsonify(error="Authentification Telegram invalide"),401
 u=User.query.filter_by(telegram_id=tg["id"]).first()
 if not u:u=User(telegram_id=tg["id"],username=tg.get("username"),first_name=tg.get("first_name"),referral_code=new_code());db.session.add(u)
 else:u.username,u.first_name=tg.get("username"),tg.get("first_name")
 db.session.commit();session["uid"]=u.id;return jsonify(ok=True)
@app.get("/api/me")
def me():
 u=current_user()
 if not u:return jsonify(error="Non authentifié"),401
 return jsonify(first_name=u.first_name,username=u.username,telegram_id=u.telegram_id,referral_code=u.referral_code,loyalty_points=u.loyalty_points,referral_points=u.referral_points,filleuls=User.query.filter_by(referred_by_user_id=u.id).count(),is_admin=is_admin(u))
@app.get("/api/catalog")
def catalog():return jsonify([product_json(p) for p in Product.query.filter_by(active=True).order_by(Product.category,Product.sort_order,Product.id).all()])
@app.get("/api/news")
def news():return jsonify([{"id":n.id,"title":n.title,"subtitle":n.subtitle,"image_url":n.image_url} for n in NewsItem.query.filter_by(active=True).order_by(NewsItem.sort_order,NewsItem.id).all()])
@app.get("/api/leaderboard")
def leaderboard():
 rows=User.query.order_by(User.loyalty_points.desc()).limit(20).all()
 return jsonify([{"name":u.username or u.first_name or "Membre","points":u.loyalty_points} for u in rows])
@app.route("/api/weights",methods=["GET","POST"])
def weights():
 u=current_user()
 if not u:return jsonify(error="Non authentifié"),401
 if request.method=="POST":
  try:w=float((request.json or {}).get("weight"))
  except Exception:return jsonify(error="Poids invalide"),400
  if not 25<=w<=350:return jsonify(error="Poids hors plage"),400
  db.session.add(WeightEntry(user_id=u.id,weight_kg=w));db.session.commit()
 rows=WeightEntry.query.filter_by(user_id=u.id).order_by(WeightEntry.created_at.asc()).all()
 return jsonify([{"id":x.id,"weight":x.weight_kg,"date":x.created_at.isoformat()} for x in rows])
@app.post("/api/referral/apply")
def referral_apply():
 u=current_user()
 if not u:return jsonify(error="Non authentifié"),401
 if u.referred_by_user_id:return jsonify(error="Parrain déjà défini"),409
 ref=User.query.filter_by(referral_code=str((request.json or {}).get("code","")).upper().strip()).first()
 if not ref:return jsonify(error="Code introuvable"),404
 if ref.id==u.id:return jsonify(error="Auto-parrainage interdit"),400
 u.referred_by_user_id=ref.id;db.session.commit();return jsonify(ok=True)

AFTERSHIP_BASE=os.environ.get("AFTERSHIP_BASE_URL","https://api.aftership.com/tracking/2024-07")
def aftership(method,path,payload=None):
 key=os.environ.get("AFTERSHIP_API_KEY")
 if not key:return None,"Clé AfterShip non configurée"
 r=requests.request(method,AFTERSHIP_BASE+path,headers={"as-api-key":key,"Content-Type":"application/json"},json=payload,timeout=15)
 if r.status_code>=400:return None,f"AfterShip {r.status_code}"
 return r.json(),None
@app.route("/api/parcels",methods=["GET","POST"])
def parcels():
 u=current_user()
 if not u:return jsonify(error="Non authentifié"),401
 if request.method=="POST":
  num=str((request.json or {}).get("tracking_number","")).strip()
  if len(num)<4:return jsonify(error="Numéro invalide"),400
  p=Parcel.query.filter_by(user_id=u.id,tracking_number=num).first()
  if not p:
   data,err=aftership("POST","/trackings",{"tracking_number":num,"slug":"mondialrelay-fr"})
   if err:return jsonify(error=err),502
   t=((data or {}).get("data") or {}).get("tracking") or {}
   p=Parcel(user_id=u.id,tracking_number=num,aftership_id=t.get("id"),status=t.get("tag") or t.get("delivery_status") or "Pending");db.session.add(p);db.session.commit()
 rows=Parcel.query.filter_by(user_id=u.id).order_by(Parcel.updated_at.desc()).all()
 return jsonify([{"id":p.id,"tracking_number":p.tracking_number,"status":p.status,"checkpoint":p.last_checkpoint} for p in rows])

@app.get("/api/admin/products")
def admin_products():
 if not require_admin():return jsonify(error="Interdit"),403
 return jsonify([product_json(p) for p in Product.query.order_by(Product.sort_order,Product.id).all()])
@app.post("/api/admin/products")
def admin_product_create():
 if not require_admin():return jsonify(error="Interdit"),403
 d=request.json or {}
 try:p=Product(name=str(d["name"]).strip(),format=str(d.get("format","")).strip(),price=int(d["price"]),category=str(d["cat"]).strip(),image_url=(d.get("image_url") or None),active=True,sort_order=int(d.get("sort_order",0)))
 except Exception:return jsonify(error="Données produit invalides"),400
 if not p.name or not p.category or p.price<0:return jsonify(error="Données produit invalides"),400
 db.session.add(p);db.session.commit();return jsonify(product_json(p)),201
@app.route("/api/admin/products/<int:pid>",methods=["PATCH","DELETE"])
def admin_product(pid):
 if not require_admin():return jsonify(error="Interdit"),403
 p=db.session.get(Product,pid)
 if not p:return jsonify(error="Produit introuvable"),404
 if request.method=="DELETE":db.session.delete(p);db.session.commit();return jsonify(ok=True)
 d=request.json or {}
 for k,a in [("name","name"),("format","format"),("cat","category"),("image_url","image_url"),("active","active"),("featured","featured"),("sort_order","sort_order")]:
  if k in d:setattr(p,a,d[k])
 if "price" in d:p.price=int(d["price"])
 db.session.commit();return jsonify(product_json(p))
@app.get("/api/admin/news")
def admin_news():
 if not require_admin():return jsonify(error="Interdit"),403
 return jsonify([{"id":n.id,"title":n.title,"subtitle":n.subtitle,"image_url":n.image_url,"active":n.active,"sort_order":n.sort_order} for n in NewsItem.query.order_by(NewsItem.sort_order,NewsItem.id).all()])
@app.post("/api/admin/news")
def admin_news_create():
 if not require_admin():return jsonify(error="Interdit"),403
 d=request.json or {};n=NewsItem(title=str(d.get("title","")).strip(),subtitle=str(d.get("subtitle","")).strip(),image_url=(d.get("image_url") or None),active=True,sort_order=int(d.get("sort_order",0)))
 if not n.title:return jsonify(error="Titre requis"),400
 db.session.add(n);db.session.commit();return jsonify(id=n.id),201
@app.route("/api/admin/news/<int:nid>",methods=["PATCH","DELETE"])
def admin_news_item(nid):
 if not require_admin():return jsonify(error="Interdit"),403
 n=db.session.get(NewsItem,nid)
 if not n:return jsonify(error="Nouveauté introuvable"),404
 if request.method=="DELETE":db.session.delete(n);db.session.commit();return jsonify(ok=True)
 d=request.json or {}
 for k in ("title","subtitle","image_url","active","sort_order"):
  if k in d:setattr(n,k,d[k])
 db.session.commit();return jsonify(ok=True)

@app.post("/api/internal/orders/confirmed")
def order_confirmed():
 expected=os.environ.get("ORDER_WEBHOOK_SECRET","")
 if not expected or not hmac.compare_digest(request.headers.get("X-Nyx-Secret",""),expected):return jsonify(error="Interdit"),403
 d=request.json or {};oid,tg_id=str(d.get("order_id","")),d.get("telegram_id")
 if not oid or not tg_id:return jsonify(error="Données manquantes"),400
 if ReferralOrderEvent.query.filter_by(external_order_id=oid).first():return jsonify(ok=True,duplicate=True)
 u=User.query.filter_by(telegram_id=tg_id).first()
 if not u:return jsonify(error="Utilisateur inconnu"),404
 u.loyalty_points+=max(int(d.get("loyalty_points",1)),0)
 if u.referred_by_user_id:
  ref=db.session.get(User,u.referred_by_user_id);ref.referral_points+=1;db.session.add(ReferralOrderEvent(external_order_id=oid,referred_user_id=u.id,referrer_user_id=ref.id))
 db.session.commit();return jsonify(ok=True)

with app.app_context():
 db.create_all()
 if Product.query.count()==0:
  for i,(n,f,p,c,img) in enumerate(SEED):db.session.add(Product(name=n,format=f,price=p,category=c,image_url=img,sort_order=i))
  db.session.add(NewsItem(title="GHK-CU",subtitle="Poudre pure",image_url="/static/ghk.webp",sort_order=1))
  db.session.add(NewsItem(title="AHK-CU",subtitle="Poudre pure",image_url="/static/glow.webp",sort_order=2))
  db.session.commit()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
