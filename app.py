from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
import os
import base64
import json
from groq import Groq
from dotenv import load_dotenv
from fpdf import FPDF
from pypdf import PdfReader
from io import BytesIO
from flask_compress import Compress

from models import db, User, Note, ActivityLog, QuizScore
from blog_data import blog_posts

load_dotenv()

app = Flask(__name__)
Compress(app)

# =========================
# CONFIGURATION
# =========================
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# =========================
# LOGIN MANAGER
# =========================
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =========================
# GROQ INIT
# =========================
if not os.environ.get("GROQ_API_KEY"):
    raise ValueError("GROQ_API_KEY not set in environment variables")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# =========================
# HELPERS
# =========================
def add_xp(user, amount, subject=None, action=None):
    if not user.xp: user.xp = 0
    if not user.level: user.level = 1
    user.xp += amount
    new_level = (user.xp // 100) + 1
    if new_level > user.level:
        user.level = new_level
        user.daily_limit += 1 
    log = ActivityLog(subject=subject, action=action, user_id=user.id)
    db.session.add(log)
    db.session.commit()

def check_daily_reset(user):
    if user.last_active_date != date.today():
        user.questions_today = 0
        user.daily_limit = 5
        user.last_active_date = date.today()
        db.session.commit()

# =========================
# ROUTES
# =========================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/blog')
def blog():
    return render_template('blog.html', posts=blog_posts)

@app.route('/blog/<slug>')
def blog_post(slug):
    post = blog_posts.get(slug)
    if not post:
        return redirect(url_for('blog'))
    return render_template('blog_post.html', post=post)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# -------------------------
# AUTH ROUTES
# -------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        student_class = request.form.get('student_class')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_pw, student_class=student_class)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# -------------------------
# DASHBOARD & API
# -------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    check_daily_reset(current_user)
    if current_user.account_created_at:
        delta = datetime.utcnow() - current_user.account_created_at
        account_age_days = max(delta.days, 1)
    else:
        account_age_days = 1
    usage_percent = round((current_user.questions_today / current_user.daily_limit) * 100) if current_user.daily_limit > 0 else 0
    return render_template('dashboard.html', 
                           user=current_user, 
                           account_age=account_age_days,
                           usage_percent=usage_percent,
                           remaining=current_user.daily_limit - current_user.questions_today)

@app.route('/api/ask', methods=['POST'])
@login_required
def ask_ai():
    check_daily_reset(current_user)
    if current_user.questions_today >= current_user.daily_limit:
        return jsonify({'error': 'Daily limit reached', 'limit_reached': True}), 403
    data = request.json
    question = data.get('question')
    subject = data.get('subject', 'General')
    forbidden_subjects = ['hindi', 'english literature', 'sanskrit']
    if subject.lower() in forbidden_subjects:
        return jsonify({'answer': "I do not answer questions related to Hindi, English Literature, or Sanskrit."})
    system_prompt = f"You are a helpful AI tutor for students. The student is in {current_user.student_class or 'Grade 1 to College'}. Provide clear explanations and code examples when needed."
    user_prompt = f"Subject: {subject}. Question: {question}"
    max_tokens = 400
    is_higher_ed = current_user.student_class and any(x in current_user.student_class for x in ["College", "Other"])
    if subject.lower() == "programming" and is_higher_ed:
        max_tokens = 1000
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=max_tokens,
        )
        answer = chat_completion.choices[0].message.content
        current_user.questions_today += 1
        current_user.total_questions_asked = (current_user.total_questions_asked or 0) + 1
        add_xp(current_user, 10, subject=subject, action="Asked Question")
        return jsonify({'answer': answer, 'questions_left': current_user.daily_limit - current_user.questions_today})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-notes', methods=['POST'])
@login_required
def generate_notes():
    check_daily_reset(current_user)
    if current_user.questions_today >= current_user.daily_limit:
        return jsonify({'error': 'Daily limit reached', 'limit_reached': True}), 403
    data = request.json
    topic = data.get('topic'); subject = data.get('subject', 'General')
    system_prompt = f"You are an expert educational notes generator. Create comprehensive, well-structured study notes for a student in {current_user.student_class or 'Grade 1 to College'}. Use Markdown formatting."
    user_prompt = f"Subject: {subject}. Topic: {topic}. Please generate detailed study notes."
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1000,
        )
        notes_content = chat_completion.choices[0].message.content
        current_user.questions_today += 1
        current_user.total_questions_asked = (current_user.total_questions_asked or 0) + 1
        add_xp(current_user, 20, subject=subject, action="Generated Notes")
        return jsonify({'notes': notes_content, 'questions_left': current_user.daily_limit - current_user.questions_today})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/generate-quiz', methods=['POST'])
@login_required
def generate_quiz():
    check_daily_reset(current_user)
    if current_user.questions_today >= current_user.daily_limit:
        return jsonify({'error': 'Daily limit reached', 'limit_reached': True}), 403
    data = request.json
    topic = data.get('topic'); subject = data.get('subject', 'General')
    system_prompt = f"You are an expert quiz generator. Create a 5-question multiple choice quiz for a student in {current_user.student_class or 'Grade 1 to College'}. Return ONLY a JSON object with a key 'quiz' containing an array of 5 objects. Each object must have: 'question' (string), 'options' (array of 4 strings), and 'answer' (string matching one of the options)."
    user_prompt = f"Subject: {subject}. Topic: {topic}. Generate a 5-question quiz in JSON format."
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        quiz_json = json.loads(chat_completion.choices[0].message.content)
        current_user.questions_today += 1
        current_user.total_questions_asked = (current_user.total_questions_asked or 0) + 1
        add_xp(current_user, 15, subject=subject, action="Generated Quiz")
        return jsonify({'quiz': quiz_json['quiz'], 'questions_left': current_user.daily_limit - current_user.questions_today})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/watch-ad', methods=['POST'])
@login_required
def watch_ad_reward():
    current_user.daily_limit += 1
    db.session.commit()
    return jsonify({'success': True, 'new_limit': current_user.daily_limit})

@app.route('/notes', methods=['GET', 'POST'])
@login_required
def notes():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        if title and content:
            new_note = Note(title=title, content=content, user_id=current_user.id)
            db.session.add(new_note)
            db.session.commit()
            flash('Note saved!', 'success')
        else:
            flash('Title and Content are required', 'error')
    user_notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.created_at.desc()).all()
    return render_template('notes.html', notes=user_notes)

@app.route('/notes/delete/<int:id>')
@login_required
def delete_note(id):
    note = Note.query.get_or_404(id)
    if note.user_id == current_user.id:
        db.session.delete(note)
        db.session.commit()
        flash('Note deleted', 'success')
    return redirect(url_for('notes'))

@app.route('/api/submit-quiz-score', methods=['POST'])
@login_required
def submit_quiz_score():
    data = request.json
    score = data.get('score'); total = data.get('total'); topic = data.get('topic', 'General')
    new_score = QuizScore(topic=topic, score=score, total_questions=total, user_id=current_user.id)
    db.session.add(new_score)
    xp_reward = score * 5
    add_xp(current_user, xp_reward, subject=topic, action=f"Completed Quiz (Score: {score}/{total})")
    return jsonify({'success': True, 'xp_earned': xp_reward, 'new_xp': current_user.xp, 'new_level': current_user.level})

@app.route('/api/vision-ask', methods=['POST'])
@login_required
def vision_ask():
    check_daily_reset(current_user)
    if current_user.questions_today >= current_user.daily_limit:
        return jsonify({'error': 'Daily limit reached', 'limit_reached': True}), 403
    if 'image' not in request.files: return jsonify({'error': 'No image uploaded'}), 400
    file = request.files['image']
    image_data = base64.b64encode(file.read()).decode('utf-8')
    try:
        completion = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "Solve the problem in this image."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}]}],
            max_tokens=1000,
        )
        answer = completion.choices[0].message.content
        current_user.questions_today += 1
        current_user.total_questions_asked = (current_user.total_questions_asked or 0) + 1
        add_xp(current_user, 15, subject="Image OCR", action="Asked via Image")
        return jsonify({'answer': answer, 'questions_left': current_user.daily_limit - current_user.questions_today})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/pdf-chat', methods=['POST'])
@login_required
def pdf_chat():
    check_daily_reset(current_user)
    if 'pdf' not in request.files: return jsonify({'error': 'No PDF uploaded'}), 400
    file = request.files['pdf']; question = request.form.get('question', 'Summarize')
    try:
        reader = PdfReader(file)
        text = "".join([p.extract_text() for p in reader.pages[:5]])
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": "Use context to answer."}, {"role": "user", "content": f"Context: {text[:3000]}\n\nQuestion: {question}"}],
            model="llama-3.1-8b-instant",
        )
        answer = chat_completion.choices[0].message.content
        current_user.questions_today += 1
        current_user.total_questions_asked = (current_user.total_questions_asked or 0) + 1
        add_xp(current_user, 20, subject="PDF Analysis", action="Consulted PDF")
        return jsonify({'answer': answer, 'questions_left': current_user.daily_limit - current_user.questions_today})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/analytics')
@login_required
def get_analytics():
    subjects = db.session.query(ActivityLog.subject, db.func.count(ActivityLog.id)).filter(ActivityLog.user_id == current_user.id).group_by(ActivityLog.subject).all()
    scores = QuizScore.query.filter_by(user_id=current_user.id).order_by(QuizScore.timestamp.desc()).limit(5).all()
    return jsonify({'subjects': {s: c for s, c in subjects if s}, 'quiz_history': [{'topic': s.topic, 'score': s.score} for s in scores], 'xp': current_user.xp, 'level': current_user.level})

@app.route('/api/leaderboard')
@login_required
def get_leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(5).all()
    return jsonify([{'username': u.username, 'xp': u.xp, 'level': u.level} for u in top_users])

@app.route('/api/update-class', methods=['POST'])
@login_required
def update_class():
    data = request.json
    new_class = data.get('student_class')
    if new_class:
        current_user.student_class = new_class
        db.session.commit()
        return jsonify({'success': True, 'new_class': new_class})
    return jsonify({'error': 'No class provided'}), 400

@app.route('/api/download-pdf', methods=['POST'])
@login_required
def download_pdf():
    data = request.json
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Helvetica", size=12)
    pdf.cell(200, 10, txt=data.get('title', 'Study Note'), ln=True, align='C')
    pdf.multi_cell(0, 10, txt=data.get('content', ''))
    pdf_output = BytesIO(); pdf.output(pdf_output); pdf_output.seek(0)
    return send_file(pdf_output, as_attachment=True, download_name="study_doc.pdf", mimetype='application/pdf')

@app.route('/ads.txt')
def ads_txt():
    return send_from_directory(app.root_path, 'ads.txt')

# =========================
# RUN
# =========================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)