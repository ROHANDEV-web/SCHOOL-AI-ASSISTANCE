from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import os
from groq import Groq
from dotenv import load_dotenv

from models import db, User, Note

load_dotenv()

app = Flask(__name__)

# =========================
# SECURITY
# =========================
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")

# =========================
# DATABASE
# =========================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# =========================
# LOGIN MANAGER
# =========================
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# =========================
# GROQ INIT
# =========================
if not os.environ.get("GROQ_API_KEY"):
    raise ValueError("GROQ_API_KEY not set in environment variables")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# =========================
# USER LOADER
# =========================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# DAILY RESET FUNCTION
# =========================
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


# -------------------------
# ABOUT PAGE
# -------------------------
@app.route('/about')
def about():
    return render_template('about.html')


# -------------------------
# PRIVACY POLICY
# -------------------------
@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


# -------------------------
# TERMS OF SERVICE
# -------------------------
@app.route('/terms')
def terms():
    return render_template('terms.html')


# -------------------------
# CONTACT PAGE
# -------------------------
@app.route('/contact')
def contact():
    return render_template('contact.html')


# -------------------------
# REGISTER
# -------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)

        new_user = User(username=username, email=email, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('dashboard'))

    return render_template('register.html')


# -------------------------
# LOGIN
# -------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')

    return render_template('login.html')


# -------------------------
# LOGOUT
# -------------------------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# -------------------------
# DASHBOARD
# -------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    check_daily_reset(current_user)
    return render_template('dashboard.html', user=current_user)


# -------------------------
# AI API
# -------------------------
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
        return jsonify({
            'answer': "I do not answer questions related to Hindi, English Literature, or Sanskrit."
        })

    system_prompt = (
        "You are a helpful AI tutor for students from Grade 1 to College. "
        "Provide clear explanations and code examples when needed."
    )

    user_prompt = f"Subject: {subject}. Question: {question}"

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1024,
        )

        answer = chat_completion.choices[0].message.content

        current_user.questions_today += 1
        db.session.commit()

        return jsonify({
            'answer': answer,
            'questions_left': current_user.daily_limit - current_user.questions_today
        })

    except Exception as e:
        print("Groq API Error:", e)
        return jsonify({'error': str(e)}), 500


# -------------------------
# WATCH AD REWARD
# -------------------------
@app.route('/api/watch-ad', methods=['POST'])
@login_required
def watch_ad_reward():
    current_user.daily_limit += 1
    db.session.commit()
    return jsonify({'success': True, 'new_limit': current_user.daily_limit})


# -------------------------
# NOTES
# -------------------------
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

    user_notes = Note.query.filter_by(user_id=current_user.id) \
        .order_by(Note.created_at.desc()).all()

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


# =========================
# RUN
# =========================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
