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


class Client(db.Model):
    """Entreprise ou client pour lequel un agent travaille."""
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    color = db.Column(db.String(7), nullable=True)  # hex color e.g. "#2040a0"
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    tasks = db.relationship("Task", backref="client", lazy="dynamic")
    locations = db.relationship("WorkLocation", backref="client", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "color": self.color,
        }

    def __repr__(self):
        return f"<Client {self.name}>"


class Task(db.Model):
    """Tâche / catégorie de travail associée à un client."""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=True)  # hex e.g. "#22c55e"
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "name": self.name,
            "color": self.color,
        }

    def __repr__(self):
        return f"<Task {self.name}>"


class WorkLocation(db.Model):
    """Zone GPS pour déclenchement auto du pointage."""
    __tablename__ = "work_locations"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_meters": self.radius_meters,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<WorkLocation {self.name} [{self.latitude},{self.longitude}]>"


class Position(db.Model):
    """Position GPS d'un agent sur le terrain."""
    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)  # mètres
    altitude = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(20), nullable=False, default="gps")  # gps | network | manually
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    user = db.relationship("User", backref="positions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy": self.accuracy,
            "altitude": self.altitude,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<Position {self.user_id} [{self.latitude},{self.longitude}]>"


class Shift(db.Model):
    """Poste de travail — pointage arrivée/départ d'un agent."""
    __tablename__ = "shifts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    clock_in = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)  # Calculé au clock_out

    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(20), nullable=False, default="manual")  # manual | geo | wifi

    # Relations
    user = db.relationship("User", backref="shifts")
    client = db.relationship("Client", foreign_keys=[client_id])
    task = db.relationship("Task", foreign_keys=[task_id])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "duration_minutes": self.duration_minutes,
            "client_id": self.client_id,
            "client_name": self.client.name if self.client else None,
            "task_id": self.task_id,
            "task_name": self.task.name if self.task else None,
            "notes": self.notes,
            "source": self.source,
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
