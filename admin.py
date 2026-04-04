"""
Admin — CRUD sur les utilisateurs + vue logs de connexion.
Accessible uniquement aux admins.
"""

import secrets
from flask import (
    Blueprint, request, jsonify,
    render_template_string, redirect, url_for, flash
)
from flask_login import login_required, current_user

from models import db, User, LoginLog
from auth import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Helpers ───────────────────────────────────────────────────────────────────

def render_page(title, body_html, extra_js=""):
    """Wrap a body string in a minimal admin layout."""
    return f"""
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>{title} — Admin</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f0f2f5; color: #1a1a2e; }}
    nav {{ background: #2040a0; padding: 0.75rem 1.5rem; display: flex;
          align-items: center; gap: 1.5rem; }}
    nav h1 {{ color: white; font-size: 1.1rem; }}
    nav a {{ color: rgba(255,255,255,0.8); text-decoration: none; font-size: 0.9rem; }}
    nav a:hover {{ color: white; }}
    main {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
    h2 {{ margin-bottom: 1rem; font-size: 1.4rem; }}
    .card {{ background: white; border-radius: 8px; padding: 1.5rem;
             box-shadow: 0 2px 6px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }}
    table {{ width: 100%%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{ padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
    tr:hover td {{ background: #fafbff; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
               font-size: 0.75rem; font-weight: 600; }}
    .badge-admin {{ background: #e8f0fe; color: #1a56db; }}
    .badge-manager {{ background: #fef3c7; color: #92400e; }}
    .badge-agent {{ background: #d1fae5; color: #065f46; }}
    .badge-inactive {{ background: #fee2e2; color: #991b1b; }}
    .btn {{ padding: 5px 12px; border-radius: 4px; border: none; cursor: pointer;
            font-size: 0.85rem; text-decoration: none; display: inline-block; }}
    .btn-danger {{ background: #fee2e2; color: #991b1b; }}
    .btn-primary {{ background: #2040a0; color: white; }}
    .btn-sm {{ padding: 3px 8px; font-size: 0.8rem; }}
    form.inline {{ display: inline; }}
    .flash-error {{ background: #fee2e2; color: #991b1b; padding: 0.5rem 1rem;
                    border-radius: 4px; margin-bottom: 1rem; }}
    .flash-info  {{ background: #d1fae5; color: #065f46; padding: 0.5rem 1rem;
                    border-radius: 4px; margin-bottom: 1rem; }}
    .modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4);
              justify-content: center; align-items: center; z-index: 100; }}
    .modal.open {{ display: flex; }}
    .modal-box {{ background: white; border-radius: 8px; padding: 1.5rem; width: 400px; }}
    .modal-box h3 {{ margin-bottom: 1rem; }}
    .field {{ margin-bottom: 0.8rem; }}
    label {{ display: block; margin-bottom: 4px; font-size: 0.85rem; color: #555; }}
    input, select {{ width: 100%%; padding: 7px; border: 1px solid #ccc; border-radius: 4px; }}
    .modal-actions {{ display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }}
    .tab-bar {{ display: flex; gap: 0; margin-bottom: 1.5rem; }}
    .tab {{ padding: 8px 16px; border-radius: 6px 6px 0 0; cursor: pointer;
            color: #555; text-decoration: none; font-size: 0.9rem; }}
    .tab.active {{ background: white; color: #2040a0; font-weight: 600; box-shadow: 0 -2px 4px rgba(0,0,0,0.05); }}
  </style>
</head>
<body>
  <nav>
    <h1>☁️ Admin — Pointeuse</h1>
    <a href="{url_for('index')}">← Retour app</a>
    <a href="{url_for('admin.index')}">Utilisateurs</a>
    <a href="{url_for('admin.login_logs')}">Logs Connexion</a>
    <a href="{url_for('auth.logout')}">Déconnexion</a>
  </nav>
  <main>
    {body_html}
  </main>
  <script>{extra_js}</script>
</body>
</html>
"""


# ── User management ────────────────────────────────────────────────────────────

@admin_bp.route("/")
@login_required
@role_required("admin")
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    body = f"""
    <div class="tab-bar">
      <a class="tab active" href="{url_for('admin.index')}">Utilisateurs ({len(users)})</a>
      <a class="tab" href="{url_for('admin.login_logs')}">Logs Connexion</a>
    </div>
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <h2>Utilisateurs</h2>
        <button class="btn btn-primary" onclick="openCreate()">+ Nouvel utilisateur</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Nom</th><th>Email</th><th>Rôle</th><th>Statut</th><th>Créé le</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {"".join(_user_row(u) for u in users)}
        </tbody>
      </table>
    </div>

    <!-- Create / Edit Modal -->
    <div class="modal" id="modal">
      <div class="modal-box">
        <h3 id="modal-title">Nouvel utilisateur</h3>
        <form id="user-form" method="post" action="{url_for('admin.create_user')}">
          <input type="hidden" name="id" id="f-id">
          <div class="field">
            <label>Nom</label>
            <input type="text" name="name" id="f-name" required>
          </div>
          <div class="field">
            <label>Email</label>
            <input type="email" name="email" id="f-email" required>
          </div>
          <div class="field">
            <label>Mot de passe <span id="pw-hint" style="color:#888;font-weight:normal">(laisser vide pour ne pas changer)</span></label>
            <input type="password" name="password" id="f-password">
          </div>
          <div class="field">
            <label>Rôle</label>
            <select name="role" id="f-role">
              <option value="agent">Agent</option>
              <option value="manager">Manager</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div class="field">
            <label><input type="checkbox" name="is_active" id="f-active" value="1" checked> Compte actif</label>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn btn-danger" onclick="closeModal()">Annuler</button>
            <button type="submit" class="btn btn-primary">Enregistrer</button>
          </div>
        </form>
      </div>
    </div>
    """
    js = """
    function openCreate() {
      document.getElementById('modal-title').textContent = 'Nouvel utilisateur';
      document.getElementById('user-form').action = '/admin/users';
      document.getElementById('f-id').value = '';
      document.getElementById('f-name').value = '';
      document.getElementById('f-email').value = '';
      document.getElementById('f-password').value = '';
      document.getElementById('f-password').required = true;
      document.getElementById('pw-hint').style.display = 'none';
      document.getElementById('f-role').value = 'agent';
      document.getElementById('f-active').checked = true;
      document.getElementById('modal').classList.add('open');
    }
    function openEdit(id, name, email, role, is_active) {
      document.getElementById('modal-title').textContent = 'Modifier utilisateur';
      document.getElementById('user-form').action = '/admin/users/' + id;
      document.getElementById('f-id').value = id;
      document.getElementById('f-name').value = name;
      document.getElementById('f-email').value = email;
      document.getElementById('f-password').value = '';
      document.getElementById('f-password').required = false;
      document.getElementById('pw-hint').style.display = 'inline';
      document.getElementById('f-role').value = role;
      document.getElementById('f-active').checked = is_active === 1 || is_active === true;
      document.getElementById('modal').classList.add('open');
    }
    function closeModal() { document.getElementById('modal').classList.remove('open'); }
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
    """
    return render_page("Utilisateurs", body, js)


def _user_row(u):
    badge_cls = {"admin": "badge-admin", "manager": "badge-manager", "agent": "badge-agent"}.get(u.role, "badge-agent")
    status_cls = "badge-inactive" if not u.is_active else ""
    status_txt = "Inactif" if not u.is_active else "Actif"
    created = u.created_at.strftime("%d/%m/%Y") if u.created_at else "-"
    return f"""
    <tr>
      <td>{u.name}</td>
      <td>{u.email}</td>
      <td><span class="badge {badge_cls}">{u.role}</span></td>
      <td><span class="badge {status_cls}">{status_txt}</span></td>
      <td>{created}</td>
      <td>
        <button class="btn btn-sm" onclick='openEdit({u.id}, "{u.name}", "{u.email}", "{u.role}", {1 if u.is_active else 0})'>Modifier</button>
        <form class="inline" method="post" action="{url_for('admin.delete_user', user_id=u.id)}"
              onsubmit="return confirm('Supprimer {u.name} ?')">
          <button type="submit" class="btn btn-sm btn-danger">Suppr.</button>
        </form>
      </td>
    </tr>
    """


@admin_bp.route("/users", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "agent")
    is_active = bool(request.form.get("is_active"))

    if not name or not email:
        flash("Nom et email obligatoires.", "error")
        return redirect(url_for("admin.index"))

    if User.query.filter_by(email=email).first():
        flash("Cet email existe déjà.", "error")
        return redirect(url_for("admin.index"))

    user = User(name=name, email=email, role=role, is_active=is_active)
    if password:
        user.set_password(password)
    else:
        user.set_password(secrets.token_urlsafe(12))  # temp password
    db.session.add(user)
    db.session.commit()
    flash(f"Utilisateur '{name}' créé.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("admin.index"))

    user.name = request.form.get("name", "").strip()
    user.email = request.form.get("email", "").strip().lower()
    user.role = request.form.get("role", "agent")
    user.is_active = bool(request.form.get("is_active"))

    password = request.form.get("password", "")
    if password:
        user.set_password(password)

    db.session.commit()
    flash(f"Modifications enregistrées.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Introuvable.", "error")
        return redirect(url_for("admin.index"))
    if user.id == current_user.id:
        flash("Vous ne pouvez pas vous supprimer vous-même.", "error")
        return redirect(url_for("admin.index"))
    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f"Utilisateur '{name}' supprimé.", "info")
    return redirect(url_for("admin.index"))


# ── Login logs ─────────────────────────────────────────────────────────────────

@admin_bp.route("/logs")
@login_required
@role_required("admin", "manager")
def login_logs():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    pagination = LoginLog.query.order_by(LoginLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    rows = "".join(_log_row(l) for l in pagination.items)

    body = f"""
    <div class="tab-bar">
      <a class="tab" href="{url_for('admin.index')}">Utilisateurs</a>
      <a class="tab active" href="{url_for('admin.login_logs')}">Logs Connexion</a>
    </div>
    <div class="card">
      <h2>Logs de connexion</h2>
      <table>
        <thead><tr><th>Date</th><th>Email</th><th>Succès</th><th>IP</th><th>User-Agent</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      {"<p style=\"margin-top:1rem;\"><a href=\"?page=" + str(page-1) + "\">← Précédent</a> | <a href=\"?page=" + str(page+1) + "\">Suivant →</a></p>" if pagination.has_prev else ""}
      {"<p style=\"margin-top:1rem;\"><a href=\"?page=" + str(page+1) + "\">Suivant →</a></p>" if pagination.has_next else ""}
    </div>
    """
    return render_page("Logs Connexion", body)


def _log_row(l):
    icon = "✅" if l.success else "❌"
    ts = l.timestamp.strftime("%d/%m/%Y %H:%M") if l.timestamp else "-"
    ua = (l.user_agent or "-")[:60]
    return f"""<tr>
      <td>{ts}</td><td>{l.email}</td>
      <td>{icon}</td><td>{l.ip_address or '-'}</td>
      <td style="font-size:0.8rem;color:#666">{ua}</td>
    </tr>"""
