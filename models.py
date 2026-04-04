from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone
import secrets

bcrypt = Bcrypt()

db = SQLAlchemy()

def get_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    """Utilisateur de l'application — agent, manager ou admin."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="agent")  # admin | manager | agent
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    # Password reset
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime(timezone=True), nullable=True)

    # 2FA (TOTP)
    totp_secret = db.Column(db.String(32), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def generate_reset_token(self, expires_hours=1):
        from datetime import timedelta
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = get_now() + timedelta(hours=expires_hours)
        return self.reset_token

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None

    # Flask-Login required attributes
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "totp_enabled": self.totp_enabled,
        }
        if include_sensitive:
            data["totp_secret"] = self.totp_secret
        return data

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


class Shift(db.Model):
    """Poste de travail — pointage arrivée/départ d'un agent."""
    __tablename__ = "shifts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    clock_in = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)  # Calculé au clock_out

    # Relations
    user = db.relationship("User", backref="shifts")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "duration_minutes": self.duration_minutes,
        }


class Incident(db.Model):
    """Incident signalé par un agent."""
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)  # Dégradation | Incivilité | Problème Technique | Pénurie Matériel | Autre
    description = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    # Relations
    user = db.relationship("User", backref="incidents")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "type": self.type,
            "description": self.description,
            "image_path": self.image_path,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Intervention(db.Model):
    """Intervention avant/après sur une zone à nettoyer."""
    __tablename__ = "interventions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    location = db.Column(db.String(100), nullable=False)
    image_before_path = db.Column(db.String(500), nullable=True)
    image_after_path = db.Column(db.String(500), nullable=True)
    timestamp_start = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)
    timestamp_end = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relations
    user = db.relationship("User", backref="interventions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "location": self.location,
            "image_before_path": self.image_before_path,
            "image_after_path": self.image_after_path,
            "timestamp_start": self.timestamp_start.isoformat() if self.timestamp_start else None,
            "timestamp_end": self.timestamp_end.isoformat() if self.timestamp_end else None,
        }


class LoginLog(db.Model):
    """Journal des connexions pour audit."""
    __tablename__ = "login_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.email,
            "success": self.success,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
