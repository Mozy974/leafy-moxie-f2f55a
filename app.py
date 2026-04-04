import os, smtplib, requests, io
import logging
import secrets
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, flash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from fpdf import FPDF
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask_compress import Compress
from marshmallow import Schema, fields, ValidationError
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask_migrate import Migrate

load_dotenv()

# -- MONITORING (SENTRY) --
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = Flask(__name__)
Compress(app)

# -- MIDDLEWARE --
from middleware import GlobalTimeoutLogger, slow_request_guard
app.wsgi_app = GlobalTimeoutLogger(app.wsgi_app, threshold_seconds=10)
logging.basicConfig(level=logging.INFO)

# -- CONFIGURATIONS --
BASE_DIR = os.path.abspath(os.path.dirname(__name__))
SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=14)

database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}

# Cloudinary Config
cloudinary_url = os.environ.get('CLOUDINARY_URL')
if cloudinary_url:
    cloudinary.config(cloudinary_url=cloudinary_url, secure=True)
else:
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )

# Email Settings (SMTP)
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASS = os.environ.get('SMTP_PASS')

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -- DATABASE + MIGRATE --
from models import db, bcrypt, User, Shift, Incident, Intervention
db.init_app(app)
bcrypt.init_app(app)
migrate = Migrate(app, db)

# -- AUTH BLUEPRINTS --
from auth import auth_bp, login_manager, login_required, current_user, role_required
from admin import admin_bp
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
login_manager.init_app(app)

@app.after_request
def add_pwa_headers(response):
    response.headers['Service-Worker-Allowed'] = '/'
    return response

with app.app_context():
    db.create_all()
    print("Database initialization successful!")
    print(f"PostgreSQL/SQLite Connected to: {app.config['SQLALCHEMY_DATABASE_URI'][:20]}...")

def get_now():
    return datetime.now(timezone.utc)

def normalize_dt(dt):
    if dt is None: return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# -- VALIDATION SCHEMAS --
class IncidentSchema(Schema):
    type = fields.Str(required=True)
    description = fields.Str(load_default="")

class InterventionStartSchema(Schema):
    location = fields.Str(required=True)

class ReportSendSchema(Schema):
    email = fields.Email(required=True)

incident_schema = IncidentSchema()
intervention_start_schema = InterventionStartSchema()
report_send_schema = ReportSendSchema()

def handle_upload(file, folder="pointeuse"):
    if not file or file.filename == '':
        return None
    if os.environ.get('CLOUDINARY_API_KEY'):
        try:
            upload_result = cloudinary.uploader.upload(file, folder=folder)
            return upload_result.get('secure_url')
        except Exception as e:
            print(f"Cloudinary Error: {e}")
    safe_filename = secure_filename(file.filename)
    filename = f"{get_now().strftime('%Y%m%d_%H%M%S')}_{safe_filename}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return f"/uploads/{filename}"

# -- DATA SCOPING HELPERS --
def _scoped_shifts(user):
    q = Shift.query.order_by(Shift.clock_in.desc())
    return q.all() if user.role in ("admin", "manager") else q.filter_by(user_id=user.id).all()

def _scoped_incidents(user):
    q = Incident.query.order_by(Incident.timestamp.desc())
    return q.all() if user.role in ("admin", "manager") else q.filter_by(user_id=user.id).all()

def _scoped_interventions(user):
    q = Intervention.query.order_by(Intervention.timestamp_start.desc())
    return q.all() if user.role in ("admin", "manager") else q.filter_by(user_id=user.id).all()

# -- FRONTEND ROUTES --
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -- SHIFT API --
@app.route('/api/clock_in', methods=['POST'])
@login_required
def clock_in():
    active = Shift.query.filter_by(user_id=current_user.id, clock_out=None).first()
    if active:
        return jsonify({'error': 'Shift already active'}), 400
    new_shift = Shift(user_id=current_user.id, clock_in=get_now())
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({'success': True, 'shift': new_shift.to_dict()})

@app.route('/api/clock_out', methods=['POST'])
@login_required
def clock_out():
    active = Shift.query.filter_by(user_id=current_user.id, clock_out=None).first()
    if not active:
        return jsonify({'error': 'No active shift'}), 400
    now = get_now()
    active.clock_out = now
    start, end = normalize_dt(active.clock_in), normalize_dt(active.clock_out)
    active.duration_minutes = int((end - start).total_seconds() / 60)
    db.session.commit()
    return jsonify({'success': True, 'shift': active.to_dict()})

@app.route('/api/shifts', methods=['GET'])
@login_required
def get_shifts():
    return jsonify({'shifts': [s.to_dict() for s in _scoped_shifts(current_user)]})

# -- INCIDENT & INTERVENTION API --
@app.route('/api/incident', methods=['POST'])
@login_required
def report_incident():
    try:
        data = incident_schema.load(request.form)
    except ValidationError as err:
        return jsonify(err.messages), 400
    url = handle_upload(request.files.get('image'), folder="incidents")
    new_inc = Incident(user_id=current_user.id, type=data['type'], description=data['description'], image_path=url)
    db.session.add(new_inc)
    db.session.commit()
    return jsonify({'success': True, 'incident': new_inc.to_dict()})

@app.route('/api/incidents', methods=['GET'])
@login_required
def get_incidents():
    return jsonify({'incidents': [i.to_dict() for i in _scoped_incidents(current_user)]})

@app.route('/api/intervention/start', methods=['POST'])
@login_required
def start_intervention():
    try:
        data = intervention_start_schema.load(request.form)
    except ValidationError as err:
        return jsonify(err.messages), 400
    url = handle_upload(request.files.get('image_before'), folder="z-avant")
    new_int = Intervention(user_id=current_user.id, location=data['location'], image_before_path=url)
    db.session.add(new_int)
    db.session.commit()
    return jsonify({'success': True, 'intervention': new_int.to_dict()})

@app.route('/api/intervention/end/<int:int_id>', methods=['POST'])
@login_required
def end_intervention(int_id):
    intervention = db.session.get(Intervention, int_id)
    if not intervention:
        return jsonify({'error': 'Not found'}), 404
    url = handle_upload(request.files.get('image_after'), folder="z-apres")
    intervention.image_after_path = url
    intervention.timestamp_end = get_now()
    db.session.commit()
    return jsonify({'success': True, 'intervention': intervention.to_dict()})

@app.route('/api/interventions', methods=['GET'])
@login_required
def get_interventions():
    return jsonify({'interventions': [i.to_dict() for i in _scoped_interventions(current_user)]})

# -- REPORT API (PDF & EMAIL) --
class PDFReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(20, 40, 80)
        self.cell(0, 10, "RAPPORT D'ACTIVITÉ HEBDOMADAIRE", 0, 1, 'C')
        self.set_font('Helvetica', 'I', 10)
        self.cell(0, 10, f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'R')
        self.ln(10)

@app.route('/api/report/send', methods=['POST'])
@login_required
@slow_request_guard(threshold_seconds=15)
def send_report():
    try:
        data = report_send_schema.load(request.json)
    except ValidationError as err:
        return jsonify(err.messages), 400

    recipient = data['email']

    if not SMTP_USER or not SMTP_PASS:
        return jsonify({'error': 'CONFIGURATION REQUISE : Veuillez ajouter SMTP_USER et SMTP_PASS dans le tableau de bord Render.'}), 400

    now = get_now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    try:
        shifts = [s for s in _scoped_shifts(current_user) if normalize_dt(s.clock_in) >= monday]
        shifts.sort(key=lambda x: x.clock_in)
        incidents = [i for i in _scoped_incidents(current_user) if normalize_dt(i.timestamp) >= monday]
        interventions = [iv for iv in _scoped_interventions(current_user)
                         if normalize_dt(iv.timestamp_start) >= monday and iv.timestamp_end]
    except Exception as e:
        import traceback
        print(f"Fetch Error: {traceback.format_exc()}")
        return jsonify({'error': 'Erreur lors de la lecture des données'}), 500

    try:
        pdf = PDFReport()
        pdf.add_page()

        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, '1. POINTAGES DE LA SEMAINE', 0, 1)
        pdf.set_font('Helvetica', '', 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(40, 8, 'Date', 1, 0, 'C', 1)
        pdf.cell(40, 8, 'Arrivée', 1, 0, 'C', 1)
        pdf.cell(40, 8, 'Départ', 1, 0, 'C', 1)
        pdf.cell(40, 8, 'Durée', 1, 1, 'C', 1)

        total_min = 0
        for s in shifts:
            ck_in = normalize_dt(s.clock_in)
            ck_out = normalize_dt(s.clock_out)
            dur_mins = int((ck_out - ck_in).total_seconds() / 60) if ck_in and ck_out else 0
            total_min += dur_mins
            pdf.cell(40, 8, ck_in.strftime("%d/%m"), 1, 0, 'C')
            pdf.cell(40, 8, ck_in.strftime("%H:%M"), 1, 0, 'C')
            pdf.cell(40, 8, ck_out.strftime("%H:%M") if ck_out else "--:--", 1, 0, 'C')
            pdf.cell(40, 8, f"{dur_mins} min", 1, 1, 'C')

        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(120, 8, 'TOTAL SEMAINE', 1, 0, 'R')
        pdf.cell(40, 8, f"{total_min//60}h {total_min%60}min", 1, 1, 'C')
        pdf.ln(10)

        if incidents:
            pdf.set_font('Helvetica', 'B', 14)
            pdf.cell(0, 10, '2. INCIDENTS SIGNALÉS', 0, 1)
            pdf.set_font('Helvetica', '', 10)
            for inc in incidents:
                ts = normalize_dt(inc.timestamp)
                pdf.set_text_color(180, 0, 0)
                pdf.cell(0, 8, f"[{inc.type}] le {ts.strftime('%d/%m à %H:%M')}", 0, 1)
                pdf.set_text_color(0)
                pdf.multi_cell(0, 6, inc.description or "Sans description")
                if inc.image_path:
                    try:
                        img_data = requests.get(inc.image_path, timeout=10).content \
                            if inc.image_path.startswith('http') \
                            else open(os.path.join(BASE_DIR, inc.image_path.lstrip('/')), 'rb').read()
                        pdf.image(io.BytesIO(img_data), x=None, y=None, w=60)
                    except: pass
                pdf.ln(5)

        if interventions:
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 14)
            pdf.cell(0, 10, '3. INTERVENTIONS (AVANT/APRÈS)', 0, 1)
            for intv in interventions:
                ts_start = normalize_dt(intv.timestamp_start)
                ts_end = normalize_dt(intv.timestamp_end)
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, f"Lieu : {intv.location}", 0, 1)
                pdf.set_font('Helvetica', '', 9)
                pdf.cell(0, 6, f"Début: {ts_start.strftime('%H:%M')} | Fin: {ts_end.strftime('%H:%M') if ts_end else '--:--'}", 0, 1)
                y_start = pdf.get_y()
                if intv.image_before_path:
                    try:
                        img_b = requests.get(intv.image_before_path, timeout=10).content \
                            if intv.image_before_path.startswith('http') \
                            else open(os.path.join(BASE_DIR, intv.image_before_path.lstrip('/')), 'rb').read()
                        pdf.image(io.BytesIO(img_b), x=10, y=y_start+2, w=85)
                    except: pass
                if intv.image_after_path:
                    try:
                        img_a = requests.get(intv.image_after_path, timeout=10).content \
                            if intv.image_after_path.startswith('http') \
                            else open(os.path.join(BASE_DIR, intv.image_after_path.lstrip('/')), 'rb').read()
                        pdf.image(io.BytesIO(img_a), x=105, y=y_start+2, w=85)
                    except: pass
                pdf.set_y(y_start + 65)
                pdf.ln(5)

        pdf_output = pdf.output(dest='S')
    except Exception as e:
        import traceback
        print(f"PDF Generation Error: {traceback.format_exc()}")
        return jsonify({'error': 'Erreur lors de la génération du PDF'}), 500

    if not SMTP_USER or not SMTP_PASS:
        return jsonify({'error': 'Serveur email non configuré sur Render'}), 500

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = recipient
        msg['Subject'] = f"Rapport Pointeuse - {monday.strftime('%d/%m/%Y')}"
        msg.attach(MIMEText(
            "Bonjour,\n\nVeuillez trouver ci-joint le rapport hebdomadaire d'activité.\n\n"
            "Cordialement,\nService de Maintenance", 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_output)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                        f'attachment; filename="rapport_semaine_{monday.strftime("%Y_%m_%d")}.pdf"')
        msg.attach(part)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.set_debuglevel(1)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        print(f"Email Error: {traceback.format_exc()}")
        return jsonify({'error': f"Erreur lors de l'envoi de l'email: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)
