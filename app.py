import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from models import db, Shift, Incident, Intervention
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv() # Load environments from .env file

app = Flask(__name__)

# -- CONFIGURATIONS --
BASE_DIR = os.path.abspath(os.path.dirname(__name__))

# Database: Use Neon (PostgreSQL) in production, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cloudinary Setup (Image Storage)
cloudinary_url = os.environ.get('CLOUDINARY_URL')
if cloudinary_url:
    cloudinary.config(cloudinary_url=cloudinary_url, secure=True)
else:
    cloudinary.config(
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key = os.environ.get('CLOUDINARY_API_KEY'),
        api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
        secure = True
    )

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)

with app.app_context():
    db.create_all()

def get_now():
    return datetime.now(timezone.utc)

def handle_upload(file, folder="pointeuse"):
    """Uploads to Cloudinary if configured, otherwise saves locally."""
    if not file or file.filename == '':
        return None
    
    # Try Cloudinary first
    if os.environ.get('CLOUDINARY_API_KEY'):
        try:
            upload_result = cloudinary.uploader.upload(file, folder=folder)
            return upload_result.get('secure_url')
        except Exception as e:
            print(f"Cloudinary Error: {e}")
    
    # Local fallback
    safe_filename = secure_filename(file.filename)
    timestamp_str = get_now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp_str}_{safe_filename}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return f"/uploads/{filename}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -- SHIFT API --
@app.route('/api/clock_in', methods=['POST'])
def clock_in():
    active_shift = Shift.query.filter_by(clock_out=None).first()
    if active_shift:
        return jsonify({'error': 'Shift already active'}), 400
    
    new_shift = Shift(clock_in=get_now())
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({'success': True, 'shift': new_shift.to_dict()})

@app.route('/api/clock_out', methods=['POST'])
def clock_out():
    active_shift = Shift.query.filter_by(clock_out=None).first()
    if not active_shift:
        return jsonify({'error': 'No active shift to clock out'}), 400
    
    active_shift.clock_out = get_now()
    duration = active_shift.clock_out - active_shift.clock_in
    active_shift.duration_minutes = int(duration.total_seconds() / 60)
    db.session.commit()
    return jsonify({'success': True, 'shift': active_shift.to_dict()})

@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    shifts = Shift.query.order_by(Shift.clock_in.desc()).all()
    return jsonify({'shifts': [s.to_dict() for s in shifts]})

# -- INCIDENT API --
@app.route('/api/incident', methods=['POST'])
def report_incident():
    incident_type = request.form.get('type')
    description = request.form.get('description', '')
    
    if not incident_type:
        return jsonify({'error': 'Type is required'}), 400

    img_url = None
    if 'image' in request.files:
        img_url = handle_upload(request.files['image'], folder="incidents")

    new_incident = Incident(
        type=incident_type,
        description=description,
        image_path=img_url
    )
    db.session.add(new_incident)
    db.session.commit()
    return jsonify({'success': True, 'incident': new_incident.to_dict()})

@app.route('/api/incidents', methods=['GET'])
def get_incidents():
    incidents = Incident.query.order_by(Incident.timestamp.desc()).all()
    return jsonify({'incidents': [i.to_dict() for i in incidents]})

# -- INTERVENTION API --
@app.route('/api/intervention/start', methods=['POST'])
def start_intervention():
    location = request.form.get('location')
    if not location:
        return jsonify({'error': 'Location is required'}), 400

    img_url = None
    if 'image_before' in request.files:
        img_url = handle_upload(request.files['image_before'], folder="z-avant")

    new_int = Intervention(location=location, image_before_path=img_url)
    db.session.add(new_int)
    db.session.commit()
    return jsonify({'success': True, 'intervention': new_int.to_dict()})

@app.route('/api/intervention/end/<int:int_id>', methods=['POST'])
def end_intervention(int_id):
    intervention = db.session.get(Intervention, int_id) # Modern Session.get()
    if not intervention:
        return jsonify({'error': 'Intervention not found'}), 404

    img_url = None
    if 'image_after' in request.files:
        img_url = handle_upload(request.files['image_after'], folder="z-apres")

    intervention.image_after_path = img_url
    intervention.timestamp_end = get_now()
    db.session.commit()
    return jsonify({'success': True, 'intervention': intervention.to_dict()})

@app.route('/api/interventions', methods=['GET'])
def get_interventions():
    interventions = Intervention.query.order_by(Intervention.timestamp_start.desc()).all()
    return jsonify({'interventions': [i.to_dict() for i in interventions]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)
