from flask import Flask, render_template, request, redirect, session, url_for, Response, jsonify
import cv2
import numpy as np
import os
import time
from threading import Thread, Lock
import mysql.connector
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'x8T#@Zq9!sP$7fBnW3J$Lm&vY1'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/dashboard_port')
def dashboard_port():
    return render_template('dashboard_port.html')

@app.route('/dashboard_ship')
def dashboard_ship():
    return render_template('dashboard_ship.html')

@app.route('/live_feed')
def live_feed():
    return render_template('live_feed.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/main_dashboard')
def main_dashboard():
    return render_template('main_dashboard.html')

@app.route('/register')
def register():
    return render_template('register.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

# === MySQL Setup ===
db, cursor = None, None

def connect_to_database():
    global db, cursor
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Appa@@@1980@@@",
            database="naval_surveillance"
        )
        cursor = db.cursor(dictionary=True)
        print("✅ MySQL connected.")
    except mysql.connector.Error as e:
        print("❌ MySQL connection failed:", e)

# === YOLO Setup ===
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

SOURCE_URL = "http://192.168.115.15:5001/stream.mjpg"
MODEL_PATH = r'D:\Project Webpage\Project\Datasets\fishing boats\runs\detect\train\weights\best.pt'
CONFIDENCE_THRESHOLD = 0.5

model, latest_frame, processed_frame = None, None, None
processing = True
summary_lock = Lock()
detection_summary = {"person": 0, "fishing_boat": 0, "merchant_ship": 0}

def initialize_model():
    global model
    if YOLO_AVAILABLE and os.path.exists(MODEL_PATH):
        print("🔍 Loading YOLOv8 model")
        model = YOLO(MODEL_PATH)
    else:
        print("⚠️ YOLO model unavailable.")
        model = None

def get_frames():
    global latest_frame
    cap = cv2.VideoCapture(SOURCE_URL)
    while processing:
        success, frame = cap.read()
        if success:
            latest_frame = frame
        else:
            cap = cv2.VideoCapture(SOURCE_URL)
            time.sleep(0.1)
    cap.release()

def process_frames():
    global processed_frame, latest_frame
    initialize_model()
    np.random.seed(42)
    colors = np.random.randint(0, 255, (100, 3), dtype=np.uint8)

    while processing:
        if latest_frame is not None and model:
            frame = latest_frame.copy()
            results = model(frame, conf=CONFIDENCE_THRESHOLD)
            annotated = frame.copy()
            summary = {"person": 0, "fishing_boat": 0, "merchant_ship": 0}

            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]
                    color = tuple(colors[cls_id % len(colors)])
                    label = f"{cls_name}: {conf:.2f}"

                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                    cv2.rectangle(annotated, (x1, y1 - th - 5), (x1 + tw, y1), color, -1)
                    cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                    if cls_name in summary:
                        summary[cls_name] += 1

            with summary_lock:
                detection_summary.update(summary)
            processed_frame = annotated
        else:
            if latest_frame is not None:
                processed_frame = latest_frame.copy()
        time.sleep(0.01)

def generate_frames():
    global processed_frame
    while True:
        if processed_frame is not None:
            _, buffer = cv2.imencode('.jpg', processed_frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.1)

# === AUTH ROUTES ===

@app.route('/')
def index(): return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        form = request.form
        hashed_pw = generate_password_hash(form['password'])
        cursor.execute("""
            INSERT INTO officers (officerid, name, dob, username, password, role)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (form['officerid'], form['name'], form['dob'], form['username'], hashed_pw, form['role']))
        db.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor.execute("SELECT * FROM officers WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            if user['approved']:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(f"/{user['role'].replace('_officer','')}_dashboard")
            else:
                error = "Awaiting approval from main officer."
        else:
            error = "Invalid credentials."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# === DASHBOARDS ===

@app.route('/main_dashboard')
def main_dashboard():
    if session.get('role') != 'main_officer': return redirect('/login')
    cursor.execute("SELECT * FROM officers WHERE approved=0")
    pending = cursor.fetchall()
    cursor.execute("SELECT * FROM officers WHERE approved=1")
    approved = cursor.fetchall()
    cursor.execute("SELECT * FROM fishing_data")
    fishing_data = cursor.fetchall()
    cursor.execute("SELECT * FROM merchant_data")
    merchant_data = cursor.fetchall()
    return render_template('main_dashboard.html', pending=pending, approved=approved,
                           fishing_data=fishing_data, merchant_data=merchant_data)

@app.route('/approve/<int:id>')
def approve(id):
    if session.get('role') == 'main_officer':
        cursor.execute("UPDATE officers SET approved=1 WHERE id=%s", (id,))
        db.commit()
    return redirect('/main_dashboard')

@app.route('/port_dashboard')
def port_dashboard():
    if session.get('role') != 'port_officer': return redirect('/login')
    return render_template('dashboard_port.html')

@app.route('/ship_dashboard')
def ship_dashboard():
    if session.get('role') != 'ship_officer': return redirect('/login')
    cursor.execute("SELECT * FROM fishing_data")
    fishing_data = cursor.fetchall()
    cursor.execute("SELECT * FROM merchant_data")
    merchant_data = cursor.fetchall()
    return render_template('dashboard_ship.html', fishing_data=fishing_data, merchant_data=merchant_data)

@app.route('/submit_fishing_data', methods=['POST'])
def submit_fishing_data():
    form = request.form
    cursor.execute("""
        INSERT INTO fishing_data (
            boat_name, reg_no, owner_name, harbour, crew_count, docs, nav_eqpt, comm_eqpt, life_eqpt,
            fishing_licence, owner_contact, color_code, remarks, sailing_pattern, fishing_type,
            crew_identity, permit_validity, fishing_area, medevac, weather,
            coastal_security, suspicious_items
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
    """, (
        form['boat_name'], form['reg_no'], form['owner_name'], form['harbour'], form['crew_count'],
        form['docs'], form['nav_eqpt'], form['comm_eqpt'], form['life_eqpt'],
        form['fishing_licence'], form['owner_contact'], form['color_code'], form['remarks'],
        form['sailing_pattern'], form['fishing_type'], form['crew_identity'], form['permit_validity'],
        form['fishing_area'], form['medevac'], form['weather'],
        form['coastal_security'], form['suspicious_items']
    ))
    db.commit()
    return redirect('/port_dashboard')


@app.route('/submit_merchant_data', methods=['POST'])
def submit_merchant_data():
    form = request.form
    cursor.execute("""
        INSERT INTO merchant_data (
            datetime, own_position, vessel_position, co_speed, vessel_name, vessel_type, call_sign,
            mmsi_imo, inmarsat, cargo, lpc_etd, npc_eta, master_nation, crew_nation, flag_port,
            route_history, cargo_issues, armed_guards, conflict_zones, traffic_area, sar_data,
            weather_merchant, sat_phone, hull_survey, solas, dangerous_cargo, agent_port, isps,
            approved
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        form['datetime'], form['own_position'], form['vessel_position'], form['co_speed'],
        form['vessel_name'], form['vessel_type'], form['call_sign'], form['mmsi_imo'],
        form['inmarsat'], form['cargo'], form['lpc_etd'], form['npc_eta'], form['master_nation'],
        form['crew_nation'], form['flag_port'], form['route_history'], form['cargo_issues'],
        form['armed_guards'], form['conflict_zones'], form['traffic_area'], form['sar_data'],
        form['weather_merchant'], form['sat_phone'], form['hull_survey'], form['solas'],
        form['dangerous_cargo'], form['agent_port'], form['isps'], 0
    ))
    db.commit()
    return redirect('/port_dashboard')


@app.route('/approve_fishing/<int:id>')
def approve_fishing(id):
    if session.get('role') in ['main_officer', 'ship_officer']:
        cursor.execute("UPDATE fishing_data SET approved = 1 WHERE id = %s", (id,))
        db.commit()
    return redirect(request.referrer)

@app.route('/approve_merchant/<int:id>')
def approve_merchant(id):
    if session.get('role') in ['main_officer', 'ship_officer']:
        cursor.execute("UPDATE merchant_data SET approved = 1 WHERE id = %s", (id,))
        db.commit()
    return redirect(request.referrer)

# === FEEDS ===

@app.route('/live_feed')
def live_feed():
    if 'role' not in session: return redirect('/login')
    return render_template('live_feed.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/summary')
def summary():
    with summary_lock:
        return jsonify(detection_summary)

# === Run App ===
if __name__ == '__main__':
    connect_to_database()
    Thread(target=get_frames, daemon=True).start()
    Thread(target=process_frames, daemon=True).start()
    app.run(host='0.0.0.0', port=5002, debug=True)

from datetime import datetime


