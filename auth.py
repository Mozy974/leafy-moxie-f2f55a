"""
Auth — Flask-Login + bcrypt.
Protect routes with @login_required and @role_required.
"""

from functools import wraps
from flask import (
    Blueprint, request, jsonify,
    render_template_string, redirect, url_for, flash
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import check_password_hash

from models import db, User, LoginLog

# ── Blueprint ──────────────────────────────────────────────────────────────────
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── Login Manager (attached later via init_app) ───────────────────────────────
login_manager = LoginManager()
login_manager.login_view = "auth.login"   # redirects here if unauth


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Role decorator ─────────────────────────────────────────────────────────────
def role_required(*roles):
    """Restrict route to users with one of the given roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
            if current_user.role not in roles:
                return jsonify({"error": "Forbidden: insufficient role"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── HTML login page (simple, no external templates needed) ────────────────────
LOGIN_TEMPLATE = """
<!doctype html>
<title>Connexion</title>
<style>
  body { font-family: sans-serif; background: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
  .card { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); width: 320px; }
  h2 { margin-top: 0; color: #2040a0; }
  .field { margin-bottom: 1rem; }
  label { display: block; margin-bottom: 4px; font-size: 0.9rem; color: #555; }
  input { width: 100%%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
  button { width: 100%%; padding: 10px; background: #2040a0; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
  button:hover { background: #102070; }
  .error { color: #c00; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .info { color: #080; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .links { margin-top: 1rem; text-align: center; font-size: 0.85rem; }
</style>
<div class="card">
  <h2>Connexion</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="post">
    <div class="field">
      <label>Email</label>
      <input type="email" name="email" required autofocus>
    </div>
    <div class="field">
      <label>Mot de passe</label>
      <input type="password" name="password" required>
    </div>
    <button type="submit">Se connecter</button>
  </form>
  <div class="links">
    <a href="{{ url_for('auth.register') }}">Créer un compte</a>
  </div>
</div>
"""


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/me")
def me():
    """JSON endpoint: renvoie l'utilisateur courant (ou 401)."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(current_user.to_dict())


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template_string(LOGIN_TEMPLATE)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.args.get("next", url_for("index"))

    # Log attempt
    log_entry = LoginLog(
        email=email,
        success=False,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500] if request.user_agent else None,
    )

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        if not user.is_active:
            flash("Compte désactivé. Contactez l'administrateur.", "error")
            db.session.add(log_entry)
            db.session.commit()
            return render_template_string(LOGIN_TEMPLATE), 403

        log_entry.success = True
        log_entry.user_id = user.id
        db.session.add(log_entry)
        db.session.commit()

        login_user(user, remember=True)
        flash("Connexion réussie.", "info")
        return redirect(next_url)

    flash("Email ou mot de passe incorrect.", "error")
    db.session.add(log_entry)
    db.session.commit()
    return render_template_string(LOGIN_TEMPLATE), 401


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Déconnecté.", "info")
    return redirect(url_for("auth.login"))


REGISTER_TEMPLATE = """
<!doctype html>
<title>Créer un compte</title>
<style>
  body { font-family: sans-serif; background: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
  .card { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); width: 340px; }
  h2 { margin-top: 0; color: #2040a0; }
  .field { margin-bottom: 1rem; }
  label { display: block; margin-bottom: 4px; font-size: 0.9rem; color: #555; }
  input, select { width: 100%%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
  button { width: 100%%; padding: 10px; background: #2040a0; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
  button:hover { background: #102070; }
  .error { color: #c00; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .info { color: #080; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .links { margin-top: 1rem; text-align: center; font-size: 0.85rem; }
</style>
<div class="card">
  <h2>Créer un compte</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="post">
    <div class="field">
      <label>Nom complet</label>
      <input type="text" name="name" required autofocus>
    </div>
    <div class="field">
      <label>Email</label>
      <input type="email" name="email" required>
    </div>
    <div class="field">
      <label>Mot de passe</label>
      <input type="password" name="password" minlength="8" required>
    </div>
    <button type="submit">S'inscrire</button>
  </form>
  <div class="links">
    <a href="{{ url_for('auth.login') }}">Déjà un compte ?</a>
  </div>
</div>
"""


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template_string(REGISTER_TEMPLATE)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if len(name) < 2:
        flash("Le nom doit contenir au moins 2 caractères.", "error")
        return render_template_string(REGISTER_TEMPLATE), 400

    if len(password) < 8:
        flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        return render_template_string(REGISTER_TEMPLATE), 400

    if User.query.filter_by(email=email).first():
        flash("Cet email est déjà utilisé.", "error")
        return render_template_string(REGISTER_TEMPLATE), 400

    # Default role = agent; first user ever gets admin
    is_first = db.session.query(User).count() == 0
    role = "admin" if is_first else "agent"

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f"Compte créé ({role}). Connectez-vous.", "info")
    return redirect(url_for("auth.login"))
