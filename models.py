from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

def get_now():
    return datetime.now(timezone.utc)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clock_in = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True) # Calculated at clock_out

    def to_dict(self):
        return {
            'id': self.id,
            'clock_in': self.clock_in.isoformat(),
            'clock_out': self.clock_out.isoformat() if self.clock_out else None,
            'duration_minutes': self.duration_minutes
        }

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False) # Incivilité, Dégradation, Autre
    description = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'description': self.description,
            'image_path': self.image_path,
            'timestamp': self.timestamp.isoformat()
        }

class Intervention(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    image_before_path = db.Column(db.String(500), nullable=True)
    image_after_path = db.Column(db.String(500), nullable=True)
    timestamp_start = db.Column(db.DateTime(timezone=True), nullable=False, default=get_now)
    timestamp_end = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'location': self.location,
            'image_before_path': self.image_before_path,
            'image_after_path': self.image_after_path,
            'timestamp_start': self.timestamp_start.isoformat(),
            'timestamp_end': self.timestamp_end.isoformat() if self.timestamp_end else None
        }
