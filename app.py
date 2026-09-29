import os, hmac, hashlib, json, secrets, string
from datetime import datetime, timezone
from urllib.parse import parse_qsl
import requests
from flask import Flask, jsonify, request, render_template, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
db_url = os.environ.get("DATABASE_URL", "sqlite:///nyxpepz.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(64))
    first_name = db.Column(db.String(100))
    referral_code = db.Column(db.String(5), unique=True, nullable=False, index=True)
    referred_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    loyalty_points = db.Column(db.Integer, default=0, nullable=False)
    referral_points = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class WeightEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    weight_kg = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Parcel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    tracking_number = db.Column(db.String(128), nullable=False)
    carrier = db.Column(db.String(64), default="mondialrelay-fr")
    aftership_id = db.Column(db.String(128))
    status = db.Column(db.String(64), default="Pending")
    last_checkpoint = db.Column(db.Text)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("user_id", "tracking_number", name="uq_user_tracking"),)

class ReferralOrderEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_order_id = db.Column(db.String(128), unique=True, nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    referrer_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    credited_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

PRODUCTS = [
{"name":"Retatrutide","format":"10 mg","price":80,"cat":"Perte de graisse"},
{"name":"Retatrutide","format":"15 mg","price":100,"cat":"Perte de graisse"},
{"name":"Retatrutide","format":"20 mg","price":120,"cat":"Perte de graisse"},
{"name":"Retatrutide","format":"30 mg","price":140,"cat":"Perte de graisse"},
{"name":"Tesamorelin","format":"10 mg","price":80,"cat":"Perte de graisse"},
{"name":"Cagrilintide","format":"10 mg","price":120,"cat":"Perte de graisse"},
{"name":"BPC-157","format":"10 mg","price":50,"cat":"Régénération"},
{"name":"Wolverine Stack","format":"","price":70,"cat":"Régénération"},
{"name":"Semax","format":"10 mg","price":50,"cat":"Nootropiques"},
{"name":"Selank","format":"10 mg","price":50,"cat":"Nootropiques"},
{"name":"DSIP","format":"5 mg","price":40,"cat":"Nootropiques"},
{"name":"MOTS-C","format":"10 mg","price":50,"cat":"Performance"},
{"name":"KLOW Stack","format":"80 mg","price":120,"cat":"Longévité"},
{"name":"GHK-Cu","format":"50 mg","price":40,"cat":"Beauté · peau"},
{"name":"GLOW Stack","format":"70 mg","price":100,"cat":"Beauté · peau"},
{"name":"Melanotan 2","format":"10 mg","price":50,"cat":"Beauté · peau"},
{"name":"Melanotan 1","format":"10 mg","price":50,"cat":"Beauté · peau"},
{"name":"5-Amino","format":"50 mg","price":80,"cat":"Beauté · peau"},
{"name":"PT-141","format":"10 mg","price":30,"cat":"Libido"}]

def new_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(5))
        if not User.query.filter_by(referral_code=code).first():
            return code

def validate_telegram(init_data):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not init_data:
        return None
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received = data.pop("hash", None)
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if abs(datetime.now(timezone.utc).timestamp() - int(data.get("auth_date","0"))) > 86400:
            return None
        return json.loads(data["user"])
    except Exception:
        return None

def current_user():
    return db.session.get(User, session.get("uid")) if session.get("uid") else None

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.post("/api/auth/telegram")
def auth():
    tg = validate_telegram((request.json or {}).get("initData",""))
    if not tg and os.environ.get("DEV_MODE") == "1":
        tg = {"id":999001,"first_name":"Nyx","username":"demo"}
    if not tg:
        return jsonify(error="Authentification Telegram invalide"), 401
    u = User.query.filter_by(telegram_id=tg["id"]).first()
    if not u:
        u = User(telegram_id=tg["id"], username=tg.get("username"),
                 first_name=tg.get("first_name"), referral_code=new_code())
        db.session.add(u)
    else:
        u.username, u.first_name = tg.get("username"), tg.get("first_name")
    db.session.commit()
    session["uid"] = u.id
    return jsonify(ok=True)

@app.get("/api/me")
def me():
    u = current_user()
    if not u: return jsonify(error="Non authentifié"), 401
    return jsonify(first_name=u.first_name, username=u.username,
        referral_code=u.referral_code, loyalty_points=u.loyalty_points,
        referral_points=u.referral_points,
        filleuls=User.query.filter_by(referred_by_user_id=u.id).count())

@app.get("/api/catalog")
def catalog():
    return jsonify(PRODUCTS)

@app.get("/api/leaderboard")
def leaderboard():
    rows = User.query.order_by(User.loyalty_points.desc()).limit(20).all()
    return jsonify([{"name":u.username or u.first_name or "Membre","points":u.loyalty_points} for u in rows])

@app.route("/api/weights", methods=["GET","POST"])
def weights():
    u = current_user()
    if not u: return jsonify(error="Non authentifié"), 401
    if request.method == "POST":
        try: w = float((request.json or {}).get("weight"))
        except Exception: return jsonify(error="Poids invalide"), 400
        if not 25 <= w <= 350: return jsonify(error="Poids hors plage"), 400
        db.session.add(WeightEntry(user_id=u.id, weight_kg=w)); db.session.commit()
    rows = WeightEntry.query.filter_by(user_id=u.id).order_by(WeightEntry.created_at.asc()).all()
    return jsonify([{"id":x.id,"weight":x.weight_kg,"date":x.created_at.isoformat()} for x in rows])

@app.post("/api/referral/apply")
def referral_apply():
    u = current_user()
    if not u: return jsonify(error="Non authentifié"), 401
    if u.referred_by_user_id: return jsonify(error="Parrain déjà défini"), 409
    ref = User.query.filter_by(referral_code=str((request.json or {}).get("code","")).upper().strip()).first()
    if not ref: return jsonify(error="Code introuvable"), 404
    if ref.id == u.id: return jsonify(error="Auto-parrainage interdit"), 400
    u.referred_by_user_id = ref.id; db.session.commit()
    return jsonify(ok=True)

# AfterShip: endpoint/base version should be checked against the current API docs before production.
AFTERSHIP_BASE = os.environ.get("AFTERSHIP_BASE_URL", "https://api.aftership.com/tracking/2024-07")

def aftership(method, path, payload=None):
    key = os.environ.get("AFTERSHIP_API_KEY")
    if not key: return None, "Clé AfterShip non configurée"
    r = requests.request(method, AFTERSHIP_BASE + path,
        headers={"as-api-key":key,"Content-Type":"application/json"},
        json=payload, timeout=15)
    if r.status_code >= 400: return None, f"AfterShip {r.status_code}"
    return r.json(), None

@app.route("/api/parcels", methods=["GET","POST"])
def parcels():
    u = current_user()
    if not u: return jsonify(error="Non authentifié"), 401
    if request.method == "POST":
        num = str((request.json or {}).get("tracking_number","")).strip()
        if len(num) < 4: return jsonify(error="Numéro invalide"), 400
        p = Parcel.query.filter_by(user_id=u.id, tracking_number=num).first()
        if not p:
            data, err = aftership("POST","/trackings",
                                  {"tracking_number":num,"slug":"mondialrelay-fr"})
            if err: return jsonify(error=err), 502
            t = ((data or {}).get("data") or {}).get("tracking") or {}
            p = Parcel(user_id=u.id, tracking_number=num,
                       aftership_id=t.get("id"),
                       status=t.get("tag") or t.get("delivery_status") or "Pending")
            db.session.add(p); db.session.commit()
    rows = Parcel.query.filter_by(user_id=u.id).order_by(Parcel.updated_at.desc()).all()
    return jsonify([{"id":p.id,"tracking_number":p.tracking_number,
                     "status":p.status,"checkpoint":p.last_checkpoint} for p in rows])

@app.post("/api/internal/orders/confirmed")
def order_confirmed():
    expected = os.environ.get("ORDER_WEBHOOK_SECRET","")
    if not expected or not hmac.compare_digest(request.headers.get("X-Nyx-Secret",""), expected):
        return jsonify(error="Interdit"), 403
    d = request.json or {}
    oid, tg = str(d.get("order_id","")), d.get("telegram_id")
    if not oid or not tg: return jsonify(error="Données manquantes"), 400
    if ReferralOrderEvent.query.filter_by(external_order_id=oid).first():
        return jsonify(ok=True, duplicate=True)
    u = User.query.filter_by(telegram_id=tg).first()
    if not u: return jsonify(error="Utilisateur inconnu"), 404
    u.loyalty_points += max(int(d.get("loyalty_points",1)), 0)
    if u.referred_by_user_id:
        ref = db.session.get(User, u.referred_by_user_id)
        ref.referral_points += 1
        db.session.add(ReferralOrderEvent(external_order_id=oid,
            referred_user_id=u.id, referrer_user_id=ref.id))
    db.session.commit()
    return jsonify(ok=True)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
