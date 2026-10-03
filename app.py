import os, hmac, hashlib, json, secrets, string
from datetime import datetime, timezone
from urllib.parse import parse_qsl
import requests
from sqlalchemy import inspect, text, update, case, cast, func, or_, String
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import click
try:
 import cloudinary.uploader
except Exception:
 cloudinary=None
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
 id=db.Column(db.Integer,primary_key=True);name=db.Column(db.String(120),nullable=False);format=db.Column(db.String(80),default="");price=db.Column(db.Integer,nullable=False);category=db.Column(db.String(80),nullable=False,index=True);image_url=db.Column(db.Text);active=db.Column(db.Boolean,default=True,nullable=False);featured=db.Column(db.Boolean,default=False,nullable=False);sort_order=db.Column(db.Integer,default=0);stock=db.Column(db.Integer,default=0,nullable=False)
class NewsItem(db.Model):
 id=db.Column(db.Integer,primary_key=True);title=db.Column(db.String(140),nullable=False);subtitle=db.Column(db.String(200),default="");image_url=db.Column(db.Text);active=db.Column(db.Boolean,default=True,nullable=False);sort_order=db.Column(db.Integer,default=0)
class PromoPack(db.Model):
 id=db.Column(db.Integer,primary_key=True);title=db.Column(db.String(140),nullable=False);subtitle=db.Column(db.String(220),default="");price=db.Column(db.Integer,nullable=False);image_url=db.Column(db.Text);active=db.Column(db.Boolean,default=True,nullable=False);sort_order=db.Column(db.Integer,default=0)
class WeightEntry(db.Model):
 id=db.Column(db.Integer,primary_key=True);user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True);weight_kg=db.Column(db.Float,nullable=False);created_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Parcel(db.Model):
 id=db.Column(db.Integer,primary_key=True);user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True);tracking_number=db.Column(db.String(128),nullable=False);carrier=db.Column(db.String(64),default="mondialrelay-fr");aftership_id=db.Column(db.String(128));status=db.Column(db.String(64),default="Pending");last_checkpoint=db.Column(db.Text);updated_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc));__table_args__=(db.UniqueConstraint("user_id","tracking_number",name="uq_user_tracking"),)
class ReferralOrderEvent(db.Model):
 id=db.Column(db.Integer,primary_key=True);external_order_id=db.Column(db.String(128),unique=True,nullable=False);referred_user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False);referrer_user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False);credited_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class ConfirmedOrderEvent(db.Model):
 # Every processed order, including customers without a referrer. Existing
 # referral_order_event rows remain authoritative for pre-upgrade duplicates.
 id=db.Column(db.Integer,primary_key=True)
 external_order_id=db.Column(db.String(128),unique=True,nullable=False)
 user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True)
 loyalty_points=db.Column(db.Integer,nullable=False)
 processed_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)

class CatalogUpdate(db.Model):
 # A durable marker prevents a future restart from overwriting Admin edits.
 key=db.Column(db.String(100),primary_key=True)

def database_failure():
 db.session.rollback()
 app.logger.exception("Échec de la transaction de points/parrainage")
 response=jsonify(error="Base de données temporairement indisponible. Réessayez.")
 response.headers["Retry-After"]="1"
 return response,503

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
def product_json(p):return {"id":p.id,"name":p.name,"format":p.format,"price":p.price,"cat":p.category,"image_url":p.image_url,"active":p.active,"featured":p.featured,"sort_order":p.sort_order,"stock":p.stock}
def require_admin():
 u=current_user()
 return u if is_admin(u) else None

from journal import install_journal
JournalEntry=install_journal(app,db,Product,current_user)
from nutrition import install_nutrition
nutrition=install_nutrition(app,db,current_user,WeightEntry)

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
from shop_packs import install_packs
pack_shop=install_packs(app,db,Product,PromoPack,CatalogUpdate,require_admin)

@app.get("/api/admin/users")
def admin_users():
    if not require_admin():
        return jsonify(error="Interdit"), 403

    users = User.query.order_by(User.loyalty_points.desc()).all()

    return jsonify([
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "name": u.username or u.first_name or "Membre",
            "points": u.loyalty_points
        }
        for u in users
    ])


def admin_user_summary(u, admin):
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "first_name": u.first_name,
        "username": u.username,
        "name": u.first_name or u.username or "Membre",
        "points": u.loyalty_points,
        "is_self": u.id == admin.id,
    }


def admin_users_response(payload, status=200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status


@app.get("/api/admin/users/search")
def admin_search_users():
    admin = require_admin()
    if not admin:
        return admin_users_response({"error": "Interdit"}, 403)

    try:
        page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        return admin_users_response({"error": "Page invalide"}, 400)
    if page < 1:
        return admin_users_response({"error": "Page invalide"}, 400)
    sort = request.args.get("sort", "recent")
    if sort not in ("recent", "points", "name"):
        return admin_users_response({"error": "Tri invalide"}, 400)

    query = User.query
    search = request.args.get("q", "").strip()
    if search.startswith("@"):
        search = search[1:]
    if search:
        # Treat user input literally: LIKE wildcards and its escape character
        # must not broaden an administrative search.
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(
            User.first_name.ilike(pattern, escape="\\"),
            User.username.ilike(pattern, escape="\\"),
            cast(User.telegram_id, String).like(pattern, escape="\\"),
        ))

    total_users = User.query.count()
    total = query.count()
    page_size = 10
    pages = max(1, (total + page_size - 1) // page_size)
    # Deleting the last user on a page should reveal the preceding page.
    page = min(page, pages)
    if sort == "points":
        query = query.order_by(User.loyalty_points.desc(), User.id.desc())
    elif sort == "name":
        display_name = func.coalesce(func.nullif(User.first_name, ""),
                                     func.nullif(User.username, ""), "Membre")
        query = query.order_by(func.lower(display_name).asc(), User.id.asc())
    else:
        query = query.order_by(User.created_at.desc(), User.id.desc())
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    return admin_users_response({
        "users": [admin_user_summary(u, admin) for u in users],
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "total": total,
        "total_users": total_users,
    })


@app.get("/api/admin/users/<int:uid>")
def admin_user_detail(uid):
    admin = require_admin()
    if not admin:
        return admin_users_response({"error": "Interdit"}, 403)
    user = db.session.get(User, uid)
    if not user:
        return admin_users_response({"error": "Utilisateur introuvable"}, 404)
    return admin_users_response(admin_user_summary(user, admin))


@app.patch("/api/admin/users/<int:uid>/points")
def admin_update_user_points(uid):
    if not require_admin():
        return jsonify(error="Interdit"), 403

    u = db.session.get(User, uid)
    if not u:
        return jsonify(error="Utilisateur introuvable"), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Valeur invalide"), 400

    try:
        delta = int(data.get("delta", 0))
    except (TypeError, ValueError):
        return jsonify(error="Valeur invalide"), 400

    if delta not in (-10, -1, 1, 10):
        return jsonify(error="Modification invalide"), 400

    try:
        total = User.loyalty_points + delta
        db.session.execute(update(User).where(User.id == uid).values(
            loyalty_points=case((total < 0, 0), else_=total)),
            execution_options={"synchronize_session": False})
        db.session.refresh(u)
        points = u.loyalty_points
        db.session.commit()
    except SQLAlchemyError:
        return database_failure()

    return jsonify(
        ok=True,
        id=u.id,
        points=points
    )


@app.delete("/api/admin/users/<int:uid>")
def admin_delete_user(uid):
    if not require_admin():
        return jsonify(error="Interdit"), 403

    u = db.session.get(User, uid)
    if not u:
        return jsonify(error="Utilisateur introuvable"), 404

    # Empêche l'admin de supprimer son propre compte
    if u.id == current_user().id:
        return jsonify(error="Impossible de supprimer votre propre compte"), 400

    try:
        # Serialize deletion with referral assignment and incoming orders.
        db.session.execute(update(User).where(User.id == uid).values(
            referral_points=User.referral_points))
        linked = (
            User.query.filter_by(referred_by_user_id=uid).first()
            or ReferralOrderEvent.query.filter(
                (ReferralOrderEvent.referred_user_id == uid)
                | (ReferralOrderEvent.referrer_user_id == uid)).first()
            or ConfirmedOrderEvent.query.filter_by(user_id=uid).first()
            or shop["Order"].query.filter_by(user_id=uid).first()
            or app.extensions['nyx_ambassadors']['linked'](uid)
        )
        if linked:
            db.session.rollback()
            return jsonify(error="Suppression impossible : compte lié à un parrainage, à des commandes ou à un espace ambassadeur"), 409
        shop["Profile"].query.filter_by(user_id=uid).delete()
        shop["Loyalty"].query.filter_by(user_id=uid).delete()
        JournalEntry.query.filter_by(user_id=uid).delete()
        nutrition['purge_user'](uid)
        giveaways['purge_user'](uid)
        gifts['purge_user'](uid)
        db.session.delete(u)
        db.session.commit()
    except SQLAlchemyError:
        return database_failure()
    return jsonify(ok=True)

@app.route("/api/weights",methods=["GET","POST"])
def weights():
 u=current_user()
 if not u:return jsonify(error="Non authentifié"),401
 if request.method=="POST":
  data=request.get_json(silent=True)
  if not isinstance(data,dict):return jsonify(error="Poids invalide"),400
  try:w=float(str(data.get("weight")).replace(',','.'))
  except Exception:return jsonify(error="Poids invalide"),400
  if not 25<=w<=350:return jsonify(error="Poids hors plage"),400
  measured_at=datetime.now(timezone.utc)
  if 'date' in data:
   try:
    measured_at=datetime.fromisoformat(data['date'].replace('Z','+00:00'))
    if measured_at.tzinfo is None or measured_at.year<1900 or measured_at>datetime.now(timezone.utc):raise ValueError()
    measured_at=measured_at.astimezone(timezone.utc)
   except (ValueError,TypeError,AttributeError):return jsonify(error="Date de pesée invalide ou future"),400
  # A retry of a dated measurement should not create a duplicate point.
  if not ('date' in data and WeightEntry.query.filter_by(user_id=u.id,created_at=measured_at,weight_kg=w).first()):
   db.session.add(WeightEntry(user_id=u.id,weight_kg=w,created_at=measured_at));db.session.commit()
 rows=WeightEntry.query.filter_by(user_id=u.id).order_by(WeightEntry.created_at.asc()).all()
 return jsonify([{"id":x.id,"weight":x.weight_kg,"date":(x.created_at if x.created_at.tzinfo else x.created_at.replace(tzinfo=timezone.utc)).isoformat()} for x in rows])
@app.post("/api/referral/apply")
def referral_apply():
 try:
  u=current_user()
  if not u:return jsonify(error="Non authentifié"),401
  if u.referred_by_user_id is not None:return jsonify(error="Parrain déjà défini"),409
  d=request.get_json(silent=True)
  if not isinstance(d,dict) or not isinstance(d.get("code"),str):
   return jsonify(error="Code invalide"),400
  ref=User.query.filter_by(referral_code=d["code"].upper().strip()).first()
  if not ref:return jsonify(error="Code introuvable"),404
  if ref.id==u.id:return jsonify(error="Auto-parrainage interdit"),400
  # A conditional UPDATE, rather than a read followed by an assignment,
  # guarantees that only one competing request can choose the referrer.
  exists=db.session.execute(update(User).where(User.id==ref.id).values(
   referral_points=User.referral_points)).rowcount
  if not exists:
   db.session.rollback()
   return jsonify(error="Code introuvable"),404
  changed=db.session.execute(update(User).where(
   User.id==u.id,User.referred_by_user_id.is_(None),User.id!=ref.id
  ).values(referred_by_user_id=ref.id),execution_options={"synchronize_session":False}).rowcount
  if changed!=1:
   db.session.rollback()
   return jsonify(error="Parrain déjà défini"),409
  db.session.commit()
  return jsonify(ok=True)
 except SQLAlchemyError:
  return database_failure()

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


@app.post("/api/admin/upload")
def admin_upload():
 if not require_admin():return jsonify(error="Interdit"),403
 if "file" not in request.files:return jsonify(error="Image manquante"),400
 f=request.files["file"]
 if not f or not f.filename:return jsonify(error="Image manquante"),400
 if f.mimetype not in ("image/jpeg","image/png","image/webp"):return jsonify(error="Format accepté : JPG, PNG ou WEBP"),400
 f.seek(0,2);size=f.tell();f.seek(0)
 if size>8*1024*1024:return jsonify(error="Image trop lourde (8 Mo max)"),400
 if not os.environ.get("CLOUDINARY_URL") or cloudinary is None:return jsonify(error="Stockage photo non configuré"),503
 try:
  r=cloudinary.uploader.upload(f,folder="nyxpepz",resource_type="image",transformation=[{"quality":"auto","fetch_format":"auto"}])
  return jsonify(url=r.get("secure_url"))
 except Exception:return jsonify(error="Échec de l’upload"),502

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
 for k,a in [("name","name"),("format","format"),("cat","category"),("image_url","image_url"),("active","active"),("featured","featured"),("sort_order","sort_order"),("stock","stock")]:
  if k in d:setattr(p,a,d[k])
 if "price" in d:p.price=max(int(d["price"]),0)
 if "stock" in d:p.stock=max(int(d["stock"]),0)
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
 d=request.get_json(silent=True)
 if not isinstance(d,dict):return jsonify(error="Données invalides"),400
 raw_oid=d.get("order_id")
 if isinstance(raw_oid,bool) or not isinstance(raw_oid,(str,int)):
  return jsonify(error="Identifiant de commande invalide"),400
 # Preserve the exact identifier used by the original bot and legacy events.
 oid=str(raw_oid)
 if not oid.strip() or len(oid)>128:return jsonify(error="Identifiant de commande invalide"),400
 try:
  tg_id=integer_value(d.get("telegram_id"))
  points=max(integer_value(d.get("loyalty_points",1)),0)
  if not 0<tg_id<=9223372036854775807 or points>2147483647:raise ValueError()
 except (TypeError,ValueError):return jsonify(error="Données de points ou Telegram invalides"),400
 try:
  duplicate=order_duplicate(oid,tg_id)
  if duplicate is not None:return duplicate
  u=User.query.filter_by(telegram_id=tg_id).first()
  if not u:return jsonify(error="Utilisateur inconnu"),404
  db.session.execute(update(User).where(User.id==u.id).values(loyalty_points=User.loyalty_points))
  db.session.refresh(u)
  gift_order=shop['Order'].query.filter_by(reference=oid.strip().upper()).first()
  if gift_order and gifts['is_gift_order'](gift_order):
   db.session.rollback()
   return jsonify(error="Une commande cadeau ne donne pas de crédit d’achat"),409
  # One referral credit per person, only on their first paid order.
  first_paid=ConfirmedOrderEvent.query.filter_by(user_id=u.id).first() is None
  # The unique insert claims the order before any balance is changed.
  db.session.add(ConfirmedOrderEvent(external_order_id=oid,user_id=u.id,loyalty_points=points))
  db.session.flush()
  # SQL arithmetic also serializes with admin adjustments and referral_apply.
  changed=db.session.execute(update(User).where(
   User.id==u.id,User.loyalty_points<=2147483647-points
  ).values(loyalty_points=User.loyalty_points+points),
   execution_options={"synchronize_session":False}).rowcount
  if changed!=1:
   db.session.rollback()
   return jsonify(error="Compte supprimé ou plafond de points atteint"),409
  db.session.refresh(u)
  if u.referred_by_user_id is not None and first_paid and not ReferralOrderEvent.query.filter_by(referred_user_id=u.id).first():
   ref_id=u.referred_by_user_id
   if ref_id==u.id:
    db.session.rollback()
    return jsonify(error="Auto-parrainage interdit : lien existant à corriger"),409
   # Lock the balance before counting events; concurrent orders for this
   # referrer cannot overwrite one another's credits (PostgreSQL and SQLite).
   exists=db.session.execute(update(User).where(User.id==ref_id).values(
    referral_points=User.referral_points),execution_options={"synchronize_session":False}).rowcount
   if exists!=1:
    db.session.rollback()
    return jsonify(error="Parrain introuvable : lien existant à corriger"),409
   db.session.add(ReferralOrderEvent(external_order_id=oid,referred_user_id=u.id,referrer_user_id=ref_id))
   db.session.flush()
   total=ReferralOrderEvent.query.filter_by(referrer_user_id=ref_id).count()
   db.session.execute(update(User).where(User.id==ref_id).values(referral_points=total),
    execution_options={"synchronize_session":False})
  db.session.commit()
  return jsonify(ok=True)
 except IntegrityError:
  db.session.rollback()
  # A competing request may have committed the same unique order while we
  # were inserting. Only that proven duplicate may be acknowledged as success.
  try:
   duplicate=order_duplicate(oid,tg_id)
   if duplicate is not None:return duplicate
  except SQLAlchemyError:
   return database_failure()
  return database_failure()
 except SQLAlchemyError:
  return database_failure()

def integer_value(value):
 if isinstance(value,bool) or not isinstance(value,(str,int)):raise ValueError()
 return int(value)

def order_duplicate(oid,tg_id):
 event=ConfirmedOrderEvent.query.filter_by(external_order_id=oid).first()
 if event is not None:
  owner_id=event.user_id
 else:
  # Do not credit orders already recorded by the original app a second time.
  event=ReferralOrderEvent.query.filter_by(external_order_id=oid).first()
  if event is None:return None
  owner_id=event.referred_user_id
 owner=db.session.get(User,owner_id)
 if owner is None or owner.telegram_id!=tg_id:
  return jsonify(error="Commande déjà associée à un autre compte ou compte supprimé"),409
 return jsonify(ok=True,duplicate=True)

@app.cli.command("reconcile-referrals")
@click.option("--repair",is_flag=True,help="Réaligner les compteurs sur les événements enregistrés.")
def reconcile_referrals(repair):
 """Audit des compteurs de parrainage ; aucune modification sans --repair."""
 try:
  differences=0
  for uid, in db.session.query(User.id).order_by(User.id).all():
   if repair:
    db.session.execute(update(User).where(User.id==uid).values(referral_points=User.referral_points))
   stored=db.session.query(User.referral_points).filter(User.id==uid).scalar()
   total=ReferralOrderEvent.query.filter_by(referrer_user_id=uid).count()
   if stored!=total:
    differences+=1
    click.echo(f"Utilisateur {uid}: referral_points={stored}, événements={total}")
    if repair:
     db.session.execute(update(User).where(User.id==uid).values(referral_points=total))
  if repair:db.session.commit()
  else:db.session.rollback()
  click.echo(f"{differences} écart(s) {'corrigé(s)' if repair else 'détecté(s)'}. Points fidélité inchangés.")
 except SQLAlchemyError as exc:
  db.session.rollback()
  raise click.ClickException("Audit interrompu ; aucune correction enregistrée. Réessayez.") from exc

from shop import install_shop
shop = install_shop(app, db, User, Product, ConfirmedOrderEvent, ReferralOrderEvent, current_user, require_admin, pack_shop)
from gifts import install_gifts
gifts = install_gifts(app, db, User, Product, shop, current_user, require_admin)
from sales import install_sales
install_sales(app, db, shop, ConfirmedOrderEvent, gifts, require_admin)
from leaderboard import install_leaderboard
install_leaderboard(app, db, User, ConfirmedOrderEvent, shop, gifts, current_user)
from giveaways import install_giveaways
def giveaway_customer_eligible(uid):
 return bool(ConfirmedOrderEvent.query.filter_by(user_id=uid).first() or shop['Order'].query.filter(shop['Order'].user_id==uid,shop['Order'].status.in_(['paid','shipped','available','delivered']),~gifts['order_clause'](shop['Order'].id)).first())
giveaways=install_giveaways(app,db,User,Product,current_user,require_admin,customer_eligible=giveaway_customer_eligible)
from giveaway_delivery import install_giveaway_delivery
install_giveaway_delivery(app,db,giveaways)
from shop_delivery import install_delivery
install_delivery(app, db, User, shop)
from shop_inventory import install_inventory
install_inventory(app, db, Product, CatalogUpdate, shop)

with app.app_context():
 db.create_all()
 # Lightweight migration for existing PostgreSQL database.
 try:
  cols={c["name"] for c in inspect(db.engine).get_columns("product")}
  if "stock" not in cols:
   db.session.execute(text("ALTER TABLE product ADD COLUMN stock INTEGER NOT NULL DEFAULT 0"))
   db.session.commit()
 except Exception:
  db.session.rollback()
 if Product.query.count()==0:
  for i,(n,f,p,c,img) in enumerate(SEED):db.session.add(Product(name=n,format=f,price=p,category=c,image_url=img,sort_order=i))
  db.session.add(NewsItem(title="GHK-CU",subtitle="Poudre pure",image_url="/static/ghk.webp",sort_order=1))
  db.session.add(NewsItem(title="AHK-CU",subtitle="Poudre pure",image_url="/static/glow.webp",sort_order=2))
  db.session.commit()

 # Upgrade the two original home pack images to transparent assets without touching custom admin images.
 try:
  changed=False
  for pk in PromoPack.query.all():
   if pk.image_url=="/static/reta10.webp": pk.image_url="/static/reta10-pack.webp";changed=True
   elif pk.image_url=="/static/reta15.webp": pk.image_url="/static/reta15-pack.webp";changed=True
  if changed: db.session.commit()
 except Exception:
  db.session.rollback()
 if PromoPack.query.count()==0:
  db.session.add(PromoPack(title="Pack Reta 10 + GHK-CU",subtitle="Retatrutide 10 mg + GHK-CU",price=110,image_url="/static/reta10-pack.webp",sort_order=1))
  db.session.add(PromoPack(title="Pack Reta 15 + Cagri",subtitle="Retatrutide 15 mg + Cagrilintide",price=200,image_url="/static/reta15-pack.webp",sort_order=2))
  db.session.add(PromoPack(title="Promo NyxPepz",subtitle="Personnalise cette offre depuis l’Admin",price=0,image_url="/static/ghk.webp",sort_order=3))
  db.session.commit()
def apply_mobile_catalog_update():
 key="2026-09-29-wolverine-ahk-mobile-v1"
 if db.session.get(CatalogUpdate,key):return False
 try:
  db.session.add(CatalogUpdate(key=key))
  db.session.flush()
  products=Product.query.all()
  def normalized(name):return "".join(c for c in (name or "").lower() if c.isalnum())
  for product in products:
   if normalized(product.name) in ("wolverine","wolverinestack"):
    product.format="10 mg / 10 mg"
    product.price=100
  matches=[p for p in products if normalized(p.name)=="ahkcu"]
  if matches:
   for product in matches:
    product.format="100 mg"
    product.price=60
  else:
   db.session.add(Product(name="AHK-CU",format="100 mg",price=60,
    category="Beauté · peau",sort_order=100,stock=0,active=True))
  db.session.commit()
  return True
 except IntegrityError:
  db.session.rollback()
  if db.session.get(CatalogUpdate,key):return False
  raise
 except SQLAlchemyError:
  db.session.rollback()
  raise

with app.app_context():
 apply_mobile_catalog_update()

def apply_shop_catalog_update():
 key="2026-09-29-shop-catalog-approved-v1"
 if db.session.get(CatalogUpdate,key):return False
 try:
  db.session.add(CatalogUpdate(key=key));db.session.flush()
  for product in Product.query.all():
   name="".join(c for c in product.name.lower() if c.isalnum())
   if name=="dsip":product.format="10 mg"
   if name in ("glow","glowstack"):product.price=100
   if name in ("klow","klowstack"):product.price=120;product.category="Régénération"
   if name=="pt141":product.price=40
   if name in ("semax","selank","dsip"):product.category="Nootropiques"
   if name=="motsc":product.category="Régénération"
  db.session.commit()
  return True
 except IntegrityError:
  db.session.rollback()
  if db.session.get(CatalogUpdate,key):return False
  raise
 except SQLAlchemyError:
  db.session.rollback();raise

with app.app_context():
 apply_shop_catalog_update()
 pack_shop["seed"]()

def apply_accessory_catalog_update():
 # One-time initial inventory: later deploys must preserve sales and admin edits.
 key="2026-09-30-syringes-swabs-100-packs-v1"
 if db.session.get(CatalogUpdate,key):return False
 try:
  db.session.add(CatalogUpdate(key=key));db.session.flush()
  name="Pack 10 seringues + 10 tampons alcool"
  if not Product.query.filter_by(name=name).first():
   db.session.add(Product(name=name,format="U-100 · 1 mL · 10 + 10 pièces",
    price=10,category="Accessoires",stock=100,active=True,sort_order=200,
    image_url="/static/protocols/amino-pack-original.png"))
  db.session.commit()
  return True
 except IntegrityError:
  db.session.rollback()
  if db.session.get(CatalogUpdate,key):return False
  raise
 except SQLAlchemyError:
  db.session.rollback();raise

with app.app_context():
 apply_accessory_catalog_update()

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
