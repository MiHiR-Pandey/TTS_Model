from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import asyncio
import edge_tts
import os
import re
import requests
import time
from datetime import date, datetime

app = Flask(__name__)
app.secret_key = 'm2%F8a@7#BqZ!92L$yT1vNk'  # Keep this secure

DB_PATH = 'ttsapp.db'
MODEL_FOLDER = 'models'
MODEL_FILE = os.path.join(MODEL_FOLDER, 'model.pth')  # Change filename if needed
MODEL_DRIVE_ID = '1itDP5_JzQKR77ifVs4OeSoJAK8eO36Vs'  # Replace with your Google Drive model file ID

# =========================
# Google Drive Downloader
# =========================
def download_model_from_drive(file_id, dest_path):
    if os.path.exists(dest_path):
        print("Model already exists. Skipping download.")
        return

    print("Downloading model from Google Drive...")
    URL = "https://drive.google.com/uc?export=download"

    session_req = requests.Session()
    response = session_req.get(URL, params={'id': file_id}, stream=True)

    def get_confirm_token(response):
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                return value
        return None

    token = get_confirm_token(response)
    if token:
        params = {'id': file_id, 'confirm': token}
        response = session_req.get(URL, params=params, stream=True)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

    print("Download completed!")

# ========================
# Init DB and Download Model
# ========================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tb_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 5,
                special_key TEXT DEFAULT NULL
            )
        ''')
        conn.commit()

# ========================
# Auto Cleanup Audio Files
# ========================
def cleanup_audio_folder(folder='generated_audio', age_seconds=3600):
    now = time.time()
    os.makedirs(folder, exist_ok=True)
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            file_age = now - os.path.getmtime(file_path)
            if file_age > age_seconds:
                os.remove(file_path)
                print(f"Deleted old file: {filename}")

# Initialize on startup
init_db()
download_model_from_drive(MODEL_DRIVE_ID, MODEL_FILE)
cleanup_audio_folder()

# ========================
# TTS Setup
# ========================
VOICES = {
    "Natasha (AU)": 'en-AU-NatashaNeural',
    "William (AU)": 'en-AU-WilliamNeural',
    "Clara (CA)": 'en-CA-ClaraNeural',
    "Liam (CA)": 'en-CA-LiamNeural',
    "Libby (UK)": 'en-GB-LibbyNeural',
    "Maisie (UK)": 'en-GB-MaisieNeural',
    "Jenny (US)": 'en-US-JennyNeural',
    "Guy (US)": 'en-US-GuyNeural',
    "Aria (US)": 'en-US-AriaNeural',
    "Davis (US)": 'en-US-DavisNeural'
}

async def generate_tts(text, voice, output_file):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# ========================
# Routes
# ========================
    
@app.route('/sw.js')
def service_worker():
    return send_file('sw.js')
@app.route('/monetag')
def monetag_verify():
    return render_template('monetag.html')

@app.route('/')
def home():
    if 'loggedin' in session:
        user_id = session['id']
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT credits, special_key FROM tb_users WHERE id = ?', (user_id,))
            credits, special_key = cursor.fetchone()

            last_credit_date = session.get('last_credit_date')
            if last_credit_date != today:
                default_daily = 5
                bonus_map = {'SPONSOR100': 30, 'YTBOOST20': 20}
                daily_credit = bonus_map.get(special_key, default_daily)

                cursor.execute('UPDATE tb_users SET credits = credits + ? WHERE id = ?', (daily_credit, user_id))
                conn.commit()
                session['credits'] = credits + daily_credit
                session['last_credit_date'] = today

        return render_template('index.html', username=session['username'], credits=session['credits'], voices=list(VOICES.keys()))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tb_users WHERE username = ?', (username,))
            account = cursor.fetchone()
            if account and check_password_hash(account[2], password):
                session['loggedin'] = True
                session['id'] = account[0]
                session['username'] = account[1]
                session['credits'] = account[4]
                session.pop('last_credit_date', None)
                return redirect(url_for('home'))
            else:
                msg = 'Incorrect username/password!'
    return render_template('login.html', msg=msg)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tb_users WHERE username = ?', (username,))
            account = cursor.fetchone()

            if account:
                msg = 'Account already exists!'
            elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
                msg = 'Invalid email address!'
            elif not re.match(r'[A-Za-z0-9]+', username):
                msg = 'Username must contain only letters and numbers!'
            else:
                hashed_password = generate_password_hash(password)
                cursor.execute('INSERT INTO tb_users (username, password, email, credits) VALUES (?, ?, ?, ?)',
                               (username, hashed_password, email, 5))
                conn.commit()
                msg = 'You have successfully registered!'
                return redirect(url_for('login'))
    return render_template('register.html', msg=msg)

@app.route('/generate', methods=['POST'])
def generate():
    if 'loggedin' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    text = data.get('text', '')
    voice_key = data.get('voice', '')
    voice = VOICES.get(voice_key)

    if not text or not voice:
        return jsonify({'error': 'Invalid input'}), 400

    user_id = session['id']
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT credits FROM tb_users WHERE id = ?', (user_id,))
        credits_data = cursor.fetchone()

        if credits_data[0] <= 0:
            return jsonify({'error': 'No credits left'}), 403

        try:
            filename = f"output_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
            output_file = os.path.join("generated_audio", filename)
            os.makedirs("generated_audio", exist_ok=True)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(generate_tts(text, voice, output_file))
            loop.close()

            cursor.execute('UPDATE tb_users SET credits = credits - 1 WHERE id = ?', (user_id,))
            conn.commit()
            session['credits'] -= 1

            return jsonify({'download_url': url_for('download_file', filename=filename)})
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({'error': 'Failed to generate audio'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join("generated_audio", filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return "File not found.", 404

@app.route('/submit_key', methods=['POST'])
def submit_key():
    if 'loggedin' not in session:
        return jsonify({'msg': 'Unauthorized'}), 401

    data = request.get_json()
    submitted_key = data.get('key', '').strip()

    valid_keys = {'SPONSOR100': 30, 'YTBOOST20': 20}
    user_id = session['id']

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT special_key FROM tb_users WHERE id = ?', (user_id,))
        existing_key = cursor.fetchone()[0]

        if existing_key:
            return jsonify({'msg': f'You have already used a special key: {existing_key}. Keys can only be used once.'}), 400

        if submitted_key in valid_keys:
            daily_bonus = valid_keys[submitted_key]
            instant_bonus = 10

            cursor.execute('''
                UPDATE tb_users
                SET special_key = ?, credits = credits + ?
                WHERE id = ?
            ''', (submitted_key, instant_bonus, user_id))
            conn.commit()

            cursor.execute('SELECT credits FROM tb_users WHERE id = ?', (user_id,))
            updated_credits = cursor.fetchone()[0]
            session['credits'] = updated_credits

            return jsonify({'msg': f'Special key accepted! You received {instant_bonus} credits now and will get {daily_bonus} credits daily.'})
        else:
            return jsonify({'msg': 'Invalid key!'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

