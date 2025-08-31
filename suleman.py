from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, flash
import pyodbc
from azure.storage.blob import BlobServiceClient
import os
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from textblob import TextBlob
import cv2
import tempfile
app = Flask(__name__)
app.secret_key = 'b9e4f7a1c02d8e93f67a4c5d2e8ab91ff4763a6d85c24550'
AZURE_SQL_SERVER = "suleman12345.database.windows.net"
AZURE_SQL_DATABASE = "Sulemanafzal"
AZURE_SQL_USERNAME = "Botharoad"
AZURE_SQL_PASSWORD = "07311530504S@"
AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=suleman123;AccountKey=kLBJa666rWu4MISqFe1UqRNHsoIJ6Rdh7HiVR2DUDNXMLyWntZ4oZMpRBk2C8+65kprgV+kro/H3+AStMfKf9Q==;EndpointSuffix=core.windows.net"
AZURE_STORAGE_CONTAINER = "videos"
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, user_type):
        self.id = id
        self.username = username
        self.user_type = user_type

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, user_type FROM users WHERE id = ?", user_id)
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2])
    return None

def get_db_connection():
    connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={AZURE_SQL_SERVER};DATABASE={AZURE_SQL_DATABASE};UID={AZURE_SQL_USERNAME};PWD={AZURE_SQL_PASSWORD}'
    return pyodbc.connect(connection_string)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
        CREATE TABLE users (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(50) UNIQUE NOT NULL,
            email NVARCHAR(100) UNIQUE NOT NULL,
            password_hash NVARCHAR(255) NOT NULL,
            user_type NVARCHAR(10) NOT NULL,
            created_at DATETIME DEFAULT GETDATE()
        )
    ''')

    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='videos' AND xtype='U')
        CREATE TABLE videos (
            id INT IDENTITY(1,1) PRIMARY KEY,
            title NVARCHAR(200) NOT NULL,
            publisher NVARCHAR(100) NOT NULL,
            producer NVARCHAR(100) NOT NULL,
            genre NVARCHAR(50) NOT NULL,
            age_rating NVARCHAR(10) NOT NULL,
            video_url NVARCHAR(500) NOT NULL,
            thumbnail_url NVARCHAR(500),
            creator_id INT NOT NULL,
            created_at DATETIME DEFAULT GETDATE(),
            FOREIGN KEY (creator_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ratings' AND xtype='U')
        CREATE TABLE ratings (
            id INT IDENTITY(1,1) PRIMARY KEY,
            video_id INT NOT NULL,
            user_id INT NOT NULL,
            rating INT NOT NULL,
            created_at DATETIME DEFAULT GETDATE(),
            FOREIGN KEY (video_id) REFERENCES videos(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='comments' AND xtype='U')
        CREATE TABLE comments (
            id INT IDENTITY(1,1) PRIMARY KEY,
            video_id INT NOT NULL,
            user_id INT NOT NULL,
            comment NVARCHAR(500) NOT NULL,
            sentiment NVARCHAR(10),
            created_at DATETIME DEFAULT GETDATE(),
            FOREIGN KEY (video_id) REFERENCES videos(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()

blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']

        password_hash = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, user_type) VALUES (?, ?, ?, ?)",
                username, email, password_hash, user_type
            )
            conn.commit()
            conn.close()
            flash('Registration successful!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Username or email already exists!', 'error')

    return render_template_string(REGISTER_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash, user_type FROM users WHERE username = ?", username)
        user_data = cursor.fetchone()
        conn.close()

        if user_data and check_password_hash(user_data[2], password):
            user = User(user_data[0], user_data[1], user_data[3])
            login_user(user)
            if user.user_type == 'creator':
                return redirect(url_for('creator_dashboard'))
            else:
                return redirect(url_for('consumer_dashboard'))
        else:
            flash('Invalid credentials!', 'error')

    return render_template_string(LOGIN_TEMPLATE)

@app.route('/creator-dashboard')
@login_required
def creator_dashboard():
    if current_user.user_type != 'creator':
        return redirect(url_for('login'))
    return render_template_string(CREATOR_DASHBOARD_TEMPLATE)

@app.route('/consumer-dashboard')
@login_required
def consumer_dashboard():
    if current_user.user_type != 'consumer':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT v.id,
                          v.title,
                          v.publisher,
                          v.producer,
                          v.genre,
                          v.age_rating,
                          v.video_url,
                          AVG(CAST(r.rating AS FLOAT)) as avg_rating,
                          v.thumbnail_url
                   FROM videos v
                   LEFT JOIN ratings r ON v.id = r.video_id
                   GROUP BY v.id, v.title, v.publisher, v.producer, v.genre, v.age_rating, v.video_url, v.created_at, v.thumbnail_url
                   ORDER BY v.created_at DESC
                   ''')
    videos = cursor.fetchall()

    # Fetch user ratings
    user_ratings = {}
    cursor.execute('''
        SELECT video_id, rating
        FROM ratings
        WHERE user_id = ?
    ''', current_user.id)
    for row in cursor.fetchall():
        user_ratings[row[0]] = row[1]

    # Fetch comments
    comments_dict = {}
    cursor.execute('''
        SELECT c.video_id, u.username, c.comment, c.created_at, c.sentiment
        FROM comments c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at DESC
    ''')
    all_comments = cursor.fetchall()
    for comment in all_comments:
        vid = comment[0]
        if vid not in comments_dict:
            comments_dict[vid] = []
        comments_dict[vid].append({
            'username': comment[1],
            'comment': comment[2],
            'created_at': comment[3].strftime('%Y-%m-%d %H:%M:%S'),
            'sentiment': comment[4]
        })

    conn.close()

    return render_template_string(CONSUMER_DASHBOARD_TEMPLATE, videos=videos, user_ratings=user_ratings, comments=comments_dict)

@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    if current_user.user_type != 'creator':
        return redirect(url_for('login'))

    title = request.form['title']
    publisher = request.form['publisher']
    producer = request.form['producer']
    genre = request.form['genre']
    age_rating = request.form['age_rating']
    video_file = request.files['video']

    if video_file:
        filename = secure_filename(video_file.filename)
        blob_name = f"{uuid.uuid4()}_{filename}"

        try:
            # Save video to temp file
            with tempfile.NamedTemporaryFile(delete=False) as temp_video:
                video_file.save(temp_video.name)
                temp_video_path = temp_video.name

            # Upload video
            blob_client = blob_service_client.get_blob_client(
                container=AZURE_STORAGE_CONTAINER,
                blob=blob_name
            )
            with open(temp_video_path, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            video_url = blob_client.url

            # Generate thumbnail
            thumbnail_url = None
            cap = cv2.VideoCapture(temp_video_path)
            success, frame = cap.read()
            if success:
                thumbnail_blob_name = f"{uuid.uuid4()}_thumb.jpg"
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_thumb:
                    cv2.imwrite(temp_thumb.name, frame)
                    temp_thumb_path = temp_thumb.name

                blob_client_thumb = blob_service_client.get_blob_client(
                    container=AZURE_STORAGE_CONTAINER,
                    blob=thumbnail_blob_name
                )
                with open(temp_thumb_path, "rb") as f:
                    blob_client_thumb.upload_blob(f, overwrite=True)
                thumbnail_url = blob_client_thumb.url

                os.unlink(temp_thumb_path)

            cap.release()
            os.unlink(temp_video_path)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO videos (title, publisher, producer, genre, age_rating, video_url, thumbnail_url, creator_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                title, publisher, producer, genre, age_rating, video_url, thumbnail_url, current_user.id
            )
            conn.commit()
            conn.close()

            flash('Video uploaded successfully!', 'success')
        except Exception as e:
            flash(f'Upload failed: {str(e)}', 'error')

    return redirect(url_for('creator_dashboard'))

@app.route('/rate-video', methods=['POST'])
@login_required
def rate_video():
    if current_user.user_type != 'consumer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    video_id = data['video_id']
    rating = data['rating']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM ratings WHERE video_id = ? AND user_id = ?", video_id, current_user.id)
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE ratings SET rating = ? WHERE video_id = ? AND user_id = ?",
                       rating, video_id, current_user.id)
    else:
        cursor.execute("INSERT INTO ratings (video_id, user_id, rating) VALUES (?, ?, ?)",
                       video_id, current_user.id, rating)

    conn.commit()

    # Fetch new average
    cursor.execute("SELECT AVG(CAST(rating AS FLOAT)) FROM ratings WHERE video_id = ?", video_id)
    new_avg = cursor.fetchone()[0]

    conn.close()

    return jsonify({'success': True, 'avg_rating': new_avg})

@app.route('/add-comment', methods=['POST'])
@login_required
def add_comment():
    if current_user.user_type != 'consumer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    video_id = data['video_id']
    comment_text = data['comment']

    # Perform sentiment analysis
    blob = TextBlob(comment_text)
    polarity = blob.sentiment.polarity
    if polarity > 0:
        sentiment = 'positive'
    elif polarity < 0:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO comments (video_id, user_id, comment, sentiment) VALUES (?, ?, ?, ?)",
                   video_id, current_user.id, comment_text, sentiment)
    conn.commit()
    conn.close()

    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return jsonify({'success': True, 'comment': {'username': current_user.username, 'comment': comment_text, 'created_at': created_at, 'sentiment': sentiment}})

@app.route('/search-videos')
@login_required
def search_videos():
    query = request.args.get('q', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT v.id,
                          v.title,
                          v.publisher,
                          v.producer,
                          v.genre,
                          v.age_rating,
                          v.video_url,
                          AVG(CAST(r.rating AS FLOAT)) as avg_rating,
                          v.thumbnail_url
                   FROM videos v
                            LEFT JOIN ratings r ON v.id = r.video_id
                   WHERE v.title LIKE ?
                      OR v.genre LIKE ?
                      OR v.publisher LIKE ?
                   GROUP BY v.id, v.title, v.publisher, v.producer, v.genre, v.age_rating, v.video_url, v.thumbnail_url
                   ''', f'%{query}%', f'%{query}%', f'%{query}%')
    videos = cursor.fetchall()

    video_list = [{
        'id': v[0], 'title': v[1], 'publisher': v[2], 'producer': v[3],
        'genre': v[4], 'age_rating': v[5], 'video_url': v[6], 'avg_rating': v[7], 'thumbnail_url': v[8]
    } for v in videos]

    # Fetch user ratings
    user_ratings = {}
    cursor.execute('''
        SELECT video_id, rating
        FROM ratings
        WHERE user_id = ?
    ''', current_user.id)
    for row in cursor.fetchall():
        user_ratings[row[0]] = row[1]

    for video in video_list:
        video['user_rating'] = user_ratings.get(video['id'], 0)

    # Fetch comments
    comments_dict = {}
    if video_list:
        video_ids = [v['id'] for v in video_list]
        placeholders = ','.join(['?'] * len(video_ids))
        cursor.execute(f'''
            SELECT c.video_id, u.username, c.comment, c.created_at, c.sentiment
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.video_id IN ({placeholders})
            ORDER BY c.created_at DESC
        ''', video_ids)
        all_comments = cursor.fetchall()
        for comment in all_comments:
            vid = comment[0]
            if vid not in comments_dict:
                comments_dict[vid] = []
            comments_dict[vid].append({
                'username': comment[1],
                'comment': comment[2],
                'created_at': comment[3].strftime('%Y-%m-%d %H:%M:%S'),
                'sentiment': comment[4]
            })

    for video in video_list:
        video['comments'] = comments_dict.get(video['id'], [])

    conn.close()

    return jsonify(video_list)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


HOME_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VidFlow - Next Generation Media Platform</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            color: #ffffff;
            overflow-x: hidden;
        }

        .navigation {
            position: fixed;
            top: 0;
            width: 100%;
            background: rgba(15, 15, 35, 0.9);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
            padding: 1rem 0;
            z-index: 1000;
        }

        .nav-content {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 2rem;
        }

        .logo {
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .auth-buttons {
            display: flex;
            gap: 1rem;
        }

        .btn {
            padding: 0.7rem 1.5rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .btn-outline {
            background: transparent;
            border: 2px solid #4facfe;
            color: #4facfe;
        }

        .btn-outline:hover {
            background: #4facfe;
            color: #0f0f23;
            transform: translateY(-2px);
        }

        .btn-primary {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(79, 172, 254, 0.4);
        }

        .hero-section {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            padding: 120px 2rem 0;
        }

        .hero-background {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 20% 80%, rgba(79, 172, 254, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 20%, rgba(0, 242, 254, 0.1) 0%, transparent 50%);
        }

        .hero-content {
            text-align: center;
            max-width: 800px;
            z-index: 2;
            position: relative;
        }

        .hero-title {
            font-size: 3.5rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            line-height: 1.2;
        }

        .hero-title .gradient-text {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .hero-subtitle {
            font-size: 1.3rem;
            color: #a0a0a0;
            margin-bottom: 3rem;
            line-height: 1.6;
        }

        .cta-buttons {
            display: flex;
            gap: 1.5rem;
            justify-content: center;
            margin-bottom: 4rem;
        }

        .btn-cta {
            padding: 1rem 2.5rem;
            font-size: 1.1rem;
            border-radius: 50px;
        }

        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 2rem;
        }

        .feature-card {
            background: rgba(26, 26, 46, 0.6);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 16px;
            padding: 2rem;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
        }

        .feature-card:hover {
            transform: translateY(-10px);
            border-color: #4facfe;
            box-shadow: 0 20px 40px rgba(79, 172, 254, 0.1);
        }

        .feature-icon {
            width: 60px;
            height: 60px;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .feature-title {
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: #ffffff;
        }

        .feature-description {
            color: #a0a0a0;
            line-height: 1.6;
        }

        .footer {
            margin-top: 6rem;
            padding: 2rem;
            text-align: center;
            border-top: 1px solid rgba(79, 172, 254, 0.2);
            color: #707070;
        }

        @media (max-width: 768px) {
            .hero-title {
                font-size: 2.5rem;
            }

            .cta-buttons {
                flex-direction: column;
                align-items: center;
            }

            .nav-content {
                padding: 0 1rem;
            }
        }
    </style>
</head>
<body>
    <nav class="navigation">
        <div class="nav-content">
            <div class="logo">VidFlow</div>
            <div class="auth-buttons">
                <a href="{{ url_for('login') }}" class="btn btn-outline">Login</a>
                <a href="{{ url_for('register') }}" class="btn btn-primary">Get Started</a>
            </div>
        </div>
    </nav>

    <section class="hero-section">
        <div class="hero-background"></div>
        <div class="hero-content">
            <h1 class="hero-title">
                The Future of <span class="gradient-text">Digital Content</span> is Here
            </h1>
            <p class="hero-subtitle">
                Discover, create, and share extraordinary video experiences with our cutting-edge platform built for the next generation of content creators and viewers.
            </p>
            <div class="cta-buttons">
                <a href="{{ url_for('register') }}" class="btn btn-primary btn-cta">Start Creating</a>
                <a href="{{ url_for('login') }}" class="btn btn-outline btn-cta">Explore Content</a>
            </div>
        </div>
    </section>

    <section class="features-grid">
        <div class="feature-card">
            <div class="feature-icon">🚀</div>
            <h3 class="feature-title">Lightning Fast</h3>
            <p class="feature-description">Ultra-fast video processing and streaming with advanced compression algorithms for seamless viewing experience.</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🎨</div>
            <h3 class="feature-title">Creative Tools</h3>
            <p class="feature-description">Professional-grade editing tools and AI-powered enhancements to bring your creative vision to life.</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🌐</div>
            <h3 class="feature-title">Global Reach</h3>
            <p class="feature-description">Connect with millions of viewers worldwide through our intelligent content distribution network.</p>
        </div>
    </section>

    <footer class="footer">
        <p>&copy; 2024 VidFlow. Pioneering the future of digital media.</p>
    </footer>
</body>
</html>
'''

REGISTER_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VidFlow - Create Account</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }

        .register-container {
            width: 100%;
            max-width: 900px;
            background: rgba(26, 26, 46, 0.9);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
        }

        .register-header {
            padding: 3rem;
            text-align: center;
            background: linear-gradient(135deg, rgba(79, 172, 254, 0.1), rgba(0, 242, 254, 0.1));
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
        }

        .header-title {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header-subtitle {
            color: #a0a0a0;
            font-size: 1.1rem;
        }

        .form-container {
            padding: 3rem;
        }

        .alert {
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            font-weight: 500;
        }

        .alert-success {
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            color: #22c55e;
        }

        .alert-error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #ef4444;
        }

        .form-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 2rem;
            margin-bottom: 2rem;
        }

        .form-group {
            display: flex;
            flex-direction: column;
        }

        .form-group.full-width {
            grid-column: 1 / -1;
        }

        .form-label {
            color: #ffffff;
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }

        .form-input {
            padding: 1rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 12px;
            color: #ffffff;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-input:focus {
            outline: none;
            border-color: #4facfe;
            box-shadow: 0 0 0 4px rgba(79, 172, 254, 0.1);
        }

        .role-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-top: 0.5rem;
        }

        .role-option {
            position: relative;
        }

        .role-input {
            display: none;
        }

        .role-label {
            display: block;
            padding: 1.5rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 12px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            color: #ffffff;
            font-weight: 600;
        }

        .role-input:checked + .role-label {
            background: rgba(79, 172, 254, 0.2);
            border-color: #4facfe;
            color: #4facfe;
        }

        .submit-btn {
            width: 100%;
            padding: 1.2rem;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
            border-radius: 12px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            margin: 2rem 0;
        }

        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(79, 172, 254, 0.3);
        }

        .back-link {
            display: block;
            text-align: center;
            color: #4facfe;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }

        .back-link:hover {
            color: #00f2fe;
        }

        @media (max-width: 768px) {
            .form-grid {
                grid-template-columns: 1fr;
                gap: 1.5rem;
            }

            .role-grid {
                grid-template-columns: 1fr;
            }

            .register-container {
                margin: 1rem;
            }
        }
    </style>
</head>
<body>
    <div class="register-container">
        <div class="register-header">
            <h1 class="header-title">Join VidFlow</h1>
            <p class="header-subtitle">Start your creative journey today</p>
        </div>

        <div class="form-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            <form method="POST">
                <div class="form-grid">
                    <div class="form-group">
                        <label for="username" class="form-label">Username</label>
                        <input type="text" id="username" name="username" class="form-input" required>
                    </div>

                    <div class="form-group">
                        <label for="email" class="form-label">Email Address</label>
                        <input type="email" id="email" name="email" class="form-input" required>
                    </div>

                    <div class="form-group full-width">
                        <label for="password" class="form-label">Password</label>
                        <input type="password" id="password" name="password" class="form-input" required>
                    </div>

                    <div class="form-group full-width">
                        <label class="form-label">Choose Your Role</label>
                        <div class="role-grid">
                            <div class="role-option">
                                <input type="radio" id="creator" name="user_type" value="creator" class="role-input" required>
                                <label for="creator" class="role-label">Creator</label>
                            </div>
                            <div class="role-option">
                                <input type="radio" id="consumer" name="user_type" value="consumer" class="role-input" required>
                                <label for="consumer" class="role-label">Viewer</label>
                            </div>
                        </div>
                    </div>
                </div>

                <button type="submit" class="submit-btn">Create Account</button>
            </form>

            <a href="{{ url_for('home') }}" class="back-link">← Back to Home</a>
        </div>
    </div>
</body>
</html>
'''
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VidFlow - Sign In</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }

        .login-card {
            width: 100%;
            max-width: 450px;
            background: rgba(26, 26, 46, 0.9);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.3);
        }

        .login-header {
            padding: 3rem 3rem 2rem;
            text-align: center;
            background: linear-gradient(135deg, rgba(79, 172, 254, 0.1), rgba(0, 242, 254, 0.1));
        }

        .brand-logo {
            font-size: 2.2rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .welcome-text {
            color: #a0a0a0;
            font-size: 1rem;
        }

        .form-section {
            padding: 2rem 3rem 3rem;
        }

        .alert {
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            font-weight: 500;
        }

        .alert-success {
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            color: #22c55e;
        }

        .alert-error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #ef4444;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-label {
            display: block;
            color: #ffffff;
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }

        .form-input {
            width: 100%;
            padding: 1.2rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 12px;
            color: #ffffff;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-input:focus {
            outline: none;
            border-color: #4facfe;
            box-shadow: 0 0 0 4px rgba(79, 172, 254, 0.1);
        }

        .form-input::placeholder {
            color: #707070;
        }

        .login-btn {
            width: 100%;
            padding: 1.2rem;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
            border-radius: 12px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            margin: 1.5rem 0;
        }

        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(79, 172, 254, 0.3);
        }

        .form-footer {
            text-align: center;
            padding-top: 1rem;
            border-top: 1px solid rgba(79, 172, 254, 0.2);
        }

        .footer-link {
            color: #4facfe;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }

        .footer-link:hover {
            color: #00f2fe;
        }

        .floating-elements {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            overflow: hidden;
        }

        .floating-element {
            position: absolute;
            background: rgba(79, 172, 254, 0.1);
            border-radius: 50%;
            animation: float 6s ease-in-out infinite;
        }

        .floating-element:nth-child(1) {
            width: 80px;
            height: 80px;
            top: 10%;
            left: 10%;
            animation-delay: 0s;
        }

        .floating-element:nth-child(2) {
            width: 120px;
            height: 120px;
            top: 70%;
            right: 10%;
            animation-delay: 2s;
        }

        .floating-element:nth-child(3) {
            width: 60px;
            height: 60px;
            bottom: 20%;
            left: 20%;
            animation-delay: 4s;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-20px) rotate(180deg); }
        }

        @media (max-width: 768px) {
            .login-card {
                margin: 1rem;
            }

            .form-section {
                padding: 2rem;
            }

            .login-header {
                padding: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="floating-elements">
        <div class="floating-element"></div>
        <div class="floating-element"></div>
        <div class="floating-element"></div>
    </div>

    <div class="login-card">
        <div class="login-header">
            <div class="brand-logo">VidFlow</div>
            <p class="welcome-text">Welcome back to the future</p>
        </div>

        <div class="form-section">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            <form method="POST">
                <div class="form-group">
                    <label for="username" class="form-label">Username</label>
                    <input type="text" id="username" name="username" class="form-input" placeholder="Enter your username" required>
                </div>

                <div class="form-group">
                    <label for="password" class="form-label">Password</label>
                    <input type="password" id="password" name="password" class="form-input" placeholder="Enter your password" required>
                </div>

                <button type="submit" class="login-btn">Sign In</button>
            </form>

            <div class="form-footer">
                <a href="{{ url_for('home') }}" class="footer-link">← Return to Homepage</a>
            </div>
        </div>
    </div>
</body>
</html>
'''

CREATOR_DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VidFlow - Creator Studio</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            color: #ffffff;
            min-height: 100vh;
        }

        .dashboard-nav {
            background: rgba(26, 26, 46, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .nav-container {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 2rem;
        }

        .studio-brand {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .nav-controls {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }

        .user-badge {
            padding: 0.5rem 1rem;
            background: rgba(79, 172, 254, 0.2);
            border: 1px solid #4facfe;
            border-radius: 20px;
            color: #4facfe;
            font-weight: 600;
            font-size: 0.9rem;
        }

        .logout-btn {
            padding: 0.7rem 1.2rem;
            background: rgba(239, 68, 68, 0.2);
            border: 1px solid #ef4444;
            color: #ef4444;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }

        .logout-btn:hover {
            background: #ef4444;
            color: #ffffff;
        }

        .studio-container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 3rem 2rem;
        }

        .upload-panel {
            background: rgba(26, 26, 46, 0.8);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 20px;
            overflow: hidden;
        }

        .panel-header {
            background: linear-gradient(135deg, rgba(79, 172, 254, 0.2), rgba(0, 242, 254, 0.1));
            padding: 2.5rem;
            text-align: center;
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
        }

        .header-title {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .header-subtitle {
            color: #a0a0a0;
            font-size: 1rem;
        }

        .upload-form {
            padding: 3rem;
        }

        .alert {
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            font-weight: 500;
        }

        .alert-success {
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            color: #22c55e;
        }

        .alert-error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #ef4444;
        }

        .form-layout {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 2rem;
            margin-bottom: 2rem;
        }

        .form-field {
            display: flex;
            flex-direction: column;
        }

        .form-field.full-span {
            grid-column: 1 / -1;
        }

        .field-label {
            color: #ffffff;
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }

        .field-input, .field-select {
            padding: 1rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 12px;
            color: #ffffff;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .field-input:focus, .field-select:focus {
            outline: none;
            border-color: #4facfe;
            box-shadow: 0 0 0 4px rgba(79, 172, 254, 0.1);
        }

        .upload-zone {
            border: 3px dashed rgba(79, 172, 254, 0.5);
            border-radius: 16px;
            padding: 4rem 2rem;
            text-align: center;
            background: rgba(79, 172, 254, 0.05);
            cursor: pointer;
            transition: all 0.3s ease;
            margin: 2rem 0;
        }

        .upload-zone:hover {
            border-color: #4facfe;
            background: rgba(79, 172, 254, 0.1);
        }

        .upload-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: #4facfe;
        }

        .upload-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: #ffffff;
        }

        .upload-subtitle {
            color: #a0a0a0;
        }

        .file-display {
            background: rgba(79, 172, 254, 0.1);
            border: 1px solid #4facfe;
            border-radius: 12px;
            padding: 1rem;
            margin: 1rem 0;
            display: none;
            color: #4facfe;
        }

        .progress-section {
            margin: 2rem 0;
            display: none;
        }

        .progress-label {
            color: #ffffff;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .progress-track {
            width: 100%;
            height: 8px;
            background: rgba(79, 172, 254, 0.2);
            border-radius: 4px;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4facfe, #00f2fe);
            width: 0%;
            transition: width 0.3s ease;
        }

        .upload-submit {
            width: 100%;
            padding: 1.2rem;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
            border-radius: 12px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 2rem;
        }

        .upload-submit:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(79, 172, 254, 0.3);
        }

        .upload-submit:disabled {
            background: #444;
            color: #888;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        #videoFile {
            display: none;
        }

        @media (max-width: 768px) {
            .form-layout {
                grid-template-columns: 1fr;
            }

            .studio-container {
                padding: 2rem 1rem;
            }

            .nav-container {
                padding: 0 1rem;
            }

            .upload-zone {
                padding: 3rem 1rem;
            }
        }
    </style>
</head>
<body>
    <nav class="dashboard-nav">
        <div class="nav-container">
            <div class="studio-brand">Creator Studio</div>
            <div class="nav-controls">
                <span class="user-badge">{{ current_user.username }}</span>
                <a href="{{ url_for('logout') }}" class="logout-btn">Logout</a>
            </div>
        </div>
    </nav>

    <div class="studio-container">
        <div class="upload-panel">
            <div class="panel-header">
                <h1 class="header-title">Upload Your Content</h1>
                <p class="header-subtitle">Share your creativity with the world</p>
            </div>

            <div class="upload-form">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <form method="POST" action="{{ url_for('upload_video') }}" enctype="multipart/form-data" id="uploadForm">
                    <div class="form-layout">
                        <div class="form-field">
                            <label for="title" class="field-label">Video Title</label>
                            <input type="text" id="title" name="title" class="field-input" required>
                        </div>
                        <div class="form-field">
                            <label for="publisher" class="field-label">Publisher</label>
                            <input type="text" id="publisher" name="publisher" class="field-input" required>
                        </div>
                        <div class="form-field">
                            <label for="producer" class="field-label">Producer</label>
                            <input type="text" id="producer" name="producer" class="field-input" required>
                        </div>
                        <div class="form-field">
                            <label for="genre" class="field-label">Genre</label>
                            <select id="genre" name="genre" class="field-select" required>
                                <option value="">Select Genre</option>
                                <option value="Action">Action</option>
                                <option value="Comedy">Comedy</option>
                                <option value="Drama">Drama</option>
                                <option value="Horror">Horror</option>
                                <option value="Romance">Romance</option>
                                <option value="Sci-Fi">Sci-Fi</option>
                                <option value="Documentary">Documentary</option>
                                <option value="Animation">Animation</option>
                                <option value="Thriller">Thriller</option>
                                <option value="Adventure">Adventure</option>
                            </select>
                        </div>
                        <div class="form-field full-span">
                            <label for="age_rating" class="field-label">Content Rating</label>
                            <select id="age_rating" name="age_rating" class="field-select" required>
                                <option value="">Select Rating</option>
                                <option value="G">G - General</option>
                                <option value="PG">PG - Parental Guidance</option>
                                <option value="PG-13">PG-13 - Teen</option>
                                <option value="R">R - Restricted</option>
                                <option value="NC-17">NC-17 - Adult</option>
                                <option value="18">18+ - Mature</option>
                            </select>
                        </div>
                    </div>

                    <div class="upload-zone" onclick="document.getElementById('videoFile').click()">
                        <div class="upload-icon">⬆</div>
                        <div class="upload-title">Drop your video here</div>
                        <div class="upload-subtitle">or click to browse files</div>
                    </div>

                    <input type="file" id="videoFile" name="video" accept="video/*" required>
                    <div class="file-display" id="fileDisplay"></div>

                    <div class="progress-section" id="progressSection">
                        <div class="progress-label">Uploading...</div>
                        <div class="progress-track">
                            <div class="progress-fill" id="progressFill"></div>
                        </div>
                    </div>

                    <button type="submit" class="upload-submit" id="uploadBtn">Publish Content</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        const videoFile = document.getElementById('videoFile');
        const uploadZone = document.querySelector('.upload-zone');
        const fileDisplay = document.getElementById('fileDisplay');
        const uploadForm = document.getElementById('uploadForm');
        const progressSection = document.getElementById('progressSection');
        const progressFill = document.getElementById('progressFill');
        const uploadBtn = document.getElementById('uploadBtn');

        videoFile.addEventListener('change', handleFileSelect);

        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                fileDisplay.style.display = 'block';
                fileDisplay.innerHTML = `
                    <strong>Selected:</strong> ${file.name}<br>
                    <strong>Size:</strong> ${(file.size / 1024 / 1024).toFixed(2)} MB<br>
                    <strong>Type:</strong> ${file.type}
                `;
                uploadZone.style.borderColor = '#4facfe';
                uploadZone.querySelector('.upload-title').textContent = 'File Ready';
                uploadZone.querySelector('.upload-subtitle').textContent = file.name;
            }
        }

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, unhighlight, false);
        });

        function highlight() {
            uploadZone.style.background = 'rgba(79, 172, 254, 0.2)';
        }

        function unhighlight() {
            uploadZone.style.background = 'rgba(79, 172, 254, 0.05)';
        }

        uploadZone.addEventListener('drop', handleDrop, false);

        function handleDrop(e) {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                videoFile.files = files;
                handleFileSelect({ target: { files } });
            }
        }

        uploadForm.addEventListener('submit', function(e) {
            uploadBtn.textContent = 'UPLOADING...';
            uploadBtn.disabled = true;
            progressSection.style.display = 'block';

            let progress = 0;
            const interval = setInterval(() => {
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressFill.style.width = progress + '%';
            }, 500);

            setTimeout(() => {
                clearInterval(interval);
                progressFill.style.width = '100%';
            }, 4000);
        });
    </script>
</body>
</html>
'''

CONSUMER_DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VidFlow - Media Hub</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            color: #ffffff;
            line-height: 1.6;
        }

        .top-nav {
            background: rgba(26, 26, 46, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .nav-grid {
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 2rem;
            padding: 0 2rem;
        }

        .platform-logo {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .search-bar {
            position: relative;
            max-width: 500px;
            width: 100%;
        }

        .search-field {
            width: 100%;
            padding: 0.8rem 1.2rem;
            padding-right: 3rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 25px;
            color: #ffffff;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .search-field:focus {
            outline: none;
            border-color: #4facfe;
            box-shadow: 0 0 0 4px rgba(79, 172, 254, 0.1);
        }

        .search-field::placeholder {
            color: #707070;
        }

        .search-btn {
            position: absolute;
            right: 5px;
            top: 50%;
            transform: translateY(-50%);
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }

        .search-btn:hover {
            transform: translateY(-50%) scale(1.05);
        }

        .user-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .username-tag {
            padding: 0.5rem 1rem;
            background: rgba(79, 172, 254, 0.2);
            border: 1px solid #4facfe;
            border-radius: 20px;
            color: #4facfe;
            font-weight: 600;
            font-size: 0.9rem;
        }

        .exit-btn {
            padding: 0.7rem 1.2rem;
            background: rgba(239, 68, 68, 0.2);
            border: 1px solid #ef4444;
            color: #ef4444;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }

        .exit-btn:hover {
            background: #ef4444;
            color: #ffffff;
        }

        .main-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 3rem 2rem;
        }

        .page-title {
            font-size: 2.5rem;
            font-weight: 700;
            text-align: center;
            margin-bottom: 3rem;
            background: linear-gradient(45deg, #ffffff, #a0a0a0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .content-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 3rem;
        }

        .content-card {
            background: rgba(26, 26, 46, 0.8);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 20px;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .content-card:hover {
            transform: translateY(-8px);
            border-color: #4facfe;
            box-shadow: 0 20px 60px rgba(79, 172, 254, 0.2);
        }

        .card-title {
            background: linear-gradient(135deg, rgba(79, 172, 254, 0.2), rgba(0, 242, 254, 0.1));
            padding: 1.5rem;
            font-weight: 700;
            font-size: 1.2rem;
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
        }

        .content-info {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            padding: 1.5rem;
            background: rgba(15, 15, 35, 0.5);
            border-bottom: 1px solid rgba(79, 172, 254, 0.1);
        }

        .info-item {
            font-size: 0.9rem;
        }

        .info-key {
            color: #4facfe;
            font-weight: 600;
            display: block;
            margin-bottom: 0.2rem;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
        }

        .info-value {
            color: #ffffff;
        }

        .media-player {
            width: 100%;
            height: 300px;
            background: #000;
        }

        .engagement-area {
            padding: 2rem;
        }

        .rating-section {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(79, 172, 254, 0.2);
        }

        .star-group {
            display: flex;
            gap: 0.2rem;
        }

        .rating-star {
            font-size: 1.4rem;
            color: rgba(79, 172, 254, 0.3);
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .rating-star:hover,
        .rating-star.filled {
            color: #4facfe;
            transform: scale(1.1);
        }

        .rating-display {
            color: #a0a0a0;
            font-size: 0.9rem;
            font-weight: 500;
        }

        .comment-area textarea {
            width: 100%;
            padding: 1rem;
            background: rgba(15, 15, 35, 0.8);
            border: 2px solid rgba(79, 172, 254, 0.2);
            border-radius: 12px;
            color: #ffffff;
            font-family: inherit;
            font-size: 0.95rem;
            resize: vertical;
            min-height: 80px;
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        }

        .comment-area textarea:focus {
            outline: none;
            border-color: #4facfe;
            box-shadow: 0 0 0 4px rgba(79, 172, 254, 0.1);
        }

        .comment-area textarea::placeholder {
            color: #707070;
        }

        .comment-btn {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: #0f0f23;
            border: none;
            padding: 0.7rem 1.5rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }

        .comment-btn:hover {
            transform: translateY(-1px);
        }

        .comments-container {
            margin-top: 2rem;
            max-height: 300px;
            overflow-y: auto;
        }

        .comment-item {
            padding: 1.2rem 0;
            border-bottom: 1px solid rgba(79, 172, 254, 0.1);
        }

        .comment-item:last-child {
            border-bottom: none;
        }

        .comment-user {
            font-weight: 600;
            color: #4facfe;
            margin-bottom: 0.5rem;
        }

        .comment-content {
            color: #ffffff;
            margin-bottom: 0.8rem;
            line-height: 1.5;
        }

        .comment-details {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: #707070;
        }

        .mood-tag {
            padding: 0.2rem 0.6rem;
            border-radius: 10px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .mood-positive {
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }

        .mood-negative {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }

        .mood-neutral {
            background: rgba(156, 163, 175, 0.2);
            color: #9ca3af;
        }

        .no-content {
            text-align: center;
            padding: 4rem 2rem;
            background: rgba(26, 26, 46, 0.8);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 20px;
            margin-top: 2rem;
        }

        .no-content h3 {
            font-size: 1.8rem;
            color: #4facfe;
            margin-bottom: 1rem;
            font-weight: 600;
        }

        .no-content p {
            color: #a0a0a0;
            font-size: 1.1rem;
        }

        @media (max-width: 768px) {
            .nav-grid {
                grid-template-columns: 1fr;
                gap: 1rem;
                text-align: center;
            }

            .main-content {
                padding: 2rem 1rem;
            }

            .page-title {
                font-size: 2rem;
            }

            .content-grid {
                grid-template-columns: 1fr;
                gap: 2rem;
            }

            .content-info {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <nav class="top-nav">
        <div class="nav-grid">
            <div class="platform-logo">VidFlow</div>
            <div class="search-bar">
                <input type="text" class="search-field" id="searchField" placeholder="Discover amazing content...">
                <button class="search-btn" onclick="performSearch()">Go</button>
            </div>
            <div class="user-section">
                <span class="username-tag">{{ current_user.username }}</span>
                <a href="{{ url_for('logout') }}" class="exit-btn">Exit</a>
            </div>
        </div>
    </nav>

    <div class="main-content">
        <h1 class="page-title">Media Hub</h1>

        <div class="content-grid" id="contentGrid">
            {% if videos %}
                {% for video in videos %}
                <div class="content-card">
                    <div class="card-title">{{ video[1] }}</div>

                    <div class="content-info">
                        <div class="info-item">
                            <span class="info-key">Publisher</span>
                            <span class="info-value">{{ video[2] }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Producer</span>
                            <span class="info-value">{{ video[3] }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Genre</span>
                            <span class="info-value">{{ video[4] }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Rating</span>
                            <span class="info-value">{{ video[5] }}</span>
                        </div>
                    </div>

                    <video class="media-player" controls>
                        <source src="{{ video[6] }}" type="video/mp4">
                        Video not supported
                    </video>

                    <div class="engagement-area">
                        <div class="rating-section">
                            <div class="star-group" data-video-id="{{ video[0] }}">
                                {% set user_rating = user_ratings.get(video[0], 0) %}
                                {% for i in range(1, 6) %}
                                <span class="rating-star {% if i <= user_rating %}filled{% endif %}" data-rating="{{ i }}">★</span>
                                {% endfor %}
                            </div>
                            <div class="rating-display">
                                {% if video[7] %}
                                    Avg: {{ "%.1f"|format(video[7]) }}/5
                                {% else %}
                                    No ratings yet
                                {% endif %}
                            </div>
                        </div>

                        <div class="comment-area">
                            <textarea placeholder="Share your thoughts..." data-video-id="{{ video[0] }}"></textarea>
                            <button class="comment-btn" onclick="submitComment({{ video[0] }})">Post</button>

                            <div class="comments-container">
                                {% if comments[video[0]] %}
                                    {% for comment in comments[video[0]] %}
                                    <div class="comment-item">
                                        <div class="comment-user">{{ comment.username }}</div>
                                        <div class="comment-content">{{ comment.comment }}</div>
                                        <div class="comment-details">
                                            <span>{{ comment.created_at }}</span>
                                            <span class="mood-tag mood-{{ comment.sentiment }}">
                                                {{ comment.sentiment }}
                                            </span>
                                        </div>
                                    </div>
                                    {% endfor %}
                                {% else %}
                                    <div class="comment-item">
                                        <div class="comment-content">No comments yet. Start the conversation!</div>
                                    </div>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="no-content">
                    <h3>No Content Available</h3>
                    <p>Check back soon for fresh content from our creators.</p>
                </div>
            {% endif %}
        </div>
    </div>

    <script>
        // Rating functionality
        document.querySelectorAll('.star-group').forEach(group => {
            const stars = group.querySelectorAll('.rating-star');
            const videoId = group.dataset.videoId;

            stars.forEach((star, index) => {
                star.addEventListener('click', () => {
                    const rating = index + 1;

                    fetch('/rate-video', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ video_id: videoId, rating: rating })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            stars.forEach((s, i) => {
                                s.classList.toggle('filled', i < rating);
                            });

                            const ratingDisplay = group.parentElement.querySelector('.rating-display');
                            if (data.avg_rating) {
                                ratingDisplay.textContent = `Avg: ${data.avg_rating.toFixed(1)}/5`;
                            }
                        }
                    });
                });

                star.addEventListener('mouseenter', () => {
                    stars.forEach((s, i) => {
                        if (i <= index) {
                            s.style.color = '#4facfe';
                        } else {
                            s.style.color = 'rgba(79, 172, 254, 0.3)';
                        }
                    });
                });

                group.addEventListener('mouseleave', () => {
                    stars.forEach(s => {
                        if (s.classList.contains('filled')) {
                            s.style.color = '#4facfe';
                        } else {
                            s.style.color = 'rgba(79, 172, 254, 0.3)';
                        }
                    });
                });
            });
        });

        // Comment functionality
        function submitComment(videoId) {
            const textarea = document.querySelector(`textarea[data-video-id="${videoId}"]`);
            const comment = textarea.value.trim();

            if (!comment) return;

            fetch('/add-comment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_id: videoId, comment: comment })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const container = textarea.closest('.comment-area').querySelector('.comments-container');

                    const newComment = document.createElement('div');
                    newComment.className = 'comment-item';
                    newComment.innerHTML = `
                        <div class="comment-user">${data.comment.username}</div>
                        <div class="comment-content">${data.comment.comment}</div>
                        <div class="comment-details">
                            <span>${data.comment.created_at}</span>
                            <span class="mood-tag mood-${data.comment.sentiment}">
                                ${data.comment.sentiment}
                            </span>
                        </div>`;
                    
                    container.insertBefore(newComment, container.firstChild);
                    textarea.value = '';
                }
            });
        }

        // Search functionality
        function performSearch() {
            const query = document.getElementById('searchField').value.trim();
            const contentGrid = document.getElementById('contentGrid');
            
            if (!query) {
                location.reload();
                return;
            }

            fetch(`/search-videos?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(videos => {
                    renderSearchResults(videos);
                });
        }

        function renderSearchResults(videos) {
            const contentGrid = document.getElementById('contentGrid');
            
            if (videos.length === 0) {
                contentGrid.innerHTML = `
                    <div class="no-content">
                        <h3>No Results Found</h3>
                        <p>Try different keywords or explore our full library.</p>
                    </div>
                `;
                return;
            }

            contentGrid.innerHTML = videos.map(video => `
                <div class="content-card">
                    <div class="card-title">${video.title}</div>

                    <div class="content-info">
                        <div class="info-item">
                            <span class="info-key">Publisher</span>
                            <span class="info-value">${video.publisher}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Producer</span>
                            <span class="info-value">${video.producer}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Genre</span>
                            <span class="info-value">${video.category}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-key">Rating</span>
                            <span class="info-value">${video.age_rating}</span>
                        </div>
                    </div>

                    <video class="media-player" controls>
                        <source src="${video.video_url}" type="video/mp4">
                        Video not supported
                    </video>

                    <div class="engagement-area">
                        <div class="rating-section">
                            <div class="star-group" data-video-id="${video.id}">
                                ${[1,2,3,4,5].map(i => 
                                    `<span class="rating-star ${i <= (video.user_rating || 0) ? 'filled' : ''}" data-rating="${i}">★</span>`
                                ).join('')}
                            </div>
                            <div class="rating-display">
                                ${video.avg_rating ? `Avg: ${video.avg_rating.toFixed(1)}/5` : 'No ratings yet'}
                            </div>
                        </div>

                        <div class="comment-area">
                            <textarea placeholder="Share your thoughts..." data-video-id="${video.id}"></textarea>
                            <button class="comment-btn" onclick="submitComment(${video.id})">Post</button>

                            <div class="comments-container">
                                ${video.comments.map(comment => `
                                    <div class="comment-item">
                                        <div class="comment-user">${comment.username}</div>
                                        <div class="comment-content">${comment.comment}</div>
                                        <div class="comment-details">
                                            <span>${comment.created_at}</span>
                                            <span class="mood-tag mood-${comment.sentiment}">
                                                ${comment.sentiment}
                                            </span>
                                        </div>
                                    </div>
                                `).join('') || '<div class="comment-item"><div class="comment-content">No comments yet. Start the conversation!</div></div>'}
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');

            // Re-initialize event listeners
            initializeInteractions();
        }

        function initializeInteractions() {
            document.querySelectorAll('.star-group').forEach(group => {
                const stars = group.querySelectorAll('.rating-star');
                const videoId = group.dataset.videoId;

                stars.forEach((star, index) => {
                    star.addEventListener('click', () => {
                        const rating = index + 1;
                        
                        fetch('/rate-video', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ video_id: videoId, rating: rating })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                stars.forEach((s, i) => {
                                    s.classList.toggle('filled', i < rating);
                                });
                                
                                const ratingDisplay = group.parentElement.querySelector('.rating-display');
                                if (data.avg_rating) {
                                    ratingDisplay.textContent = `Avg: ${data.avg_rating.toFixed(1)}/5`;
                                }
                            }
                        });
                    });
                });
            });
        }

        // Search on Enter key
        document.getElementById('searchField').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    </script>
</body>
</html>
'''
init_db()
if __name__ == '__main__':

    app.run(debug=True, host='0.0.0.0', port=5000)