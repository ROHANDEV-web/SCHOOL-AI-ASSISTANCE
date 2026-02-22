// Theme Logic
window.toggleTheme = function () {
    const isLight = document.documentElement.classList.toggle('light');
    localStorage.theme = isLight ? 'light' : 'dark';
};

// Tab Logic
window.switchTab = function (tab) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active', 'border-blue-500', 'text-white'));
    document.querySelectorAll('[id^="tab-content-"]').forEach(content => content.classList.add('hidden'));

    document.getElementById(`tab-btn-${tab}`).classList.add('active', 'border-blue-500', 'text-white');
    document.getElementById(`tab-content-${tab}`).classList.remove('hidden');

    if (tab === 'analytics') loadAnalytics();
    if (tab === 'leaderboard') loadLeaderboard();
};

// Voice Recognition
window.startVoiceRecognition = function () {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Your browser does not support voice recognition.");
        return;
    }
    const recognition = new SpeechRecognition();
    const btn = document.getElementById('voice-btn');
    recognition.onstart = () => btn.classList.add('text-red-500', 'animate-pulse');
    recognition.onend = () => btn.classList.remove('text-red-500', 'animate-pulse');
    recognition.onresult = (e) => document.getElementById('user-input').value = e.results[0][0].transcript;
    recognition.start();
};

document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-container');
    const askForm = document.getElementById('ask-form');
    const userInput = document.getElementById('user-input');

    askForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const question = userInput.value.trim();
        const subject = document.getElementById('subject-select').value;
        if (!question) return;

        appendMessage('User', question);
        userInput.value = '';
        const loadingId = appendLoading();

        try {
            const res = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, subject })
            });
            const data = await res.json();
            document.getElementById(loadingId).remove();
            if (res.ok) {
                appendMessage('AI', data.answer);
                updateCredits(data.questions_left);
            } else {
                appendMessage('System', data.error || 'Limit Reached');
                if (data.limit_reached) handleLimitReached();
            }
        } catch (err) { appendMessage('System', 'Network Error'); }
    });

    function appendMessage(sender, text) {
        const div = document.createElement('div');
        div.className = 'flex gap-4 animate-fade-in';
        const isUser = sender === 'User';
        const align = isUser ? 'flex-row-reverse' : 'flex-row';
        div.innerHTML = `
            <div class="${align} flex gap-4 w-full">
                <div class="w-8 h-8 rounded-full ${isUser ? 'bg-purple-600' : 'bg-blue-500'} flex-shrink-0 flex items-center justify-center text-xs text-white font-bold">${isUser ? 'U' : 'AI'}</div>
                <div class="${isUser ? 'bg-blue-600/20' : 'glass-panel'} rounded-2xl p-4 max-w-[85%] border border-white/5 text-gray-200">
                    <div class="prose prose-invert prose-sm">${marked.parse(text)}</div>
                </div>
            </div>`;
        chatContainer.appendChild(div);
        div.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendLoading() {
        const id = 'loading-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'flex gap-4 animate-fade-in';
        div.innerHTML = `<div class="w-8 h-8 rounded-full bg-blue-500 flex-shrink-0 flex items-center justify-center text-xs font-bold text-white">AI</div><div class="glass-panel p-4 text-gray-400">Thinking...</div>`;
        chatContainer.appendChild(div);
        return id;
    }
});

let currentTool = null;
let currentQuizData = null;
let currentQuizTopic = "";
let userAnswers = {};

window.openToolModal = function (tool) {
    currentTool = tool;
    const modal = document.getElementById('tool-modal');
    ['topic-container', 'vision-file-container', 'pdf-file-container'].forEach(c => document.getElementById(c).classList.add('hidden'));
    document.getElementById('modal-form-content').classList.remove('hidden');
    document.getElementById('modal-result-content').classList.add('hidden');

    if (tool === 'notes' || tool === 'quiz') document.getElementById('topic-container').classList.remove('hidden');
    else if (tool === 'vision') document.getElementById('vision-file-container').classList.remove('hidden');
    else if (tool === 'pdf') {
        document.getElementById('topic-container').classList.remove('hidden');
        document.getElementById('pdf-file-container').classList.remove('hidden');
    }
    modal.classList.remove('hidden');
};

window.closeToolModal = function () { document.getElementById('tool-modal').classList.add('hidden'); };

window.generateToolContent = async function () {
    const topic = document.getElementById('tool-topic').value.trim();
    const subject = document.getElementById('tool-subject').value;

    document.getElementById('modal-form-content').classList.add('hidden');
    document.getElementById('modal-result-content').classList.remove('hidden');
    document.getElementById('tool-loading').classList.remove('hidden');
    document.getElementById('tool-result-data').classList.add('hidden');
    document.getElementById('tool-result-actions').classList.add('hidden');
    document.getElementById('quiz-container').classList.add('hidden');
    document.getElementById('quiz-result').classList.add('hidden');

    let endpoint = '/api/generate-notes';
    let body = JSON.stringify({ subject, topic });
    let isMultipart = false;

    if (currentTool === 'quiz') endpoint = '/api/generate-quiz';
    else if (currentTool === 'vision') {
        endpoint = '/api/vision-ask';
        const fd = new FormData(); fd.append('image', document.getElementById('vision-file').files[0]);
        body = fd; isMultipart = true;
    } else if (currentTool === 'pdf') {
        endpoint = '/api/pdf-chat';
        const fd = new FormData(); fd.append('pdf', document.getElementById('pdf-file').files[0]); fd.append('question', topic);
        body = fd; isMultipart = true;
    }

    try {
        const res = await fetch(endpoint, { method: 'POST', body, ...(isMultipart ? {} : { headers: { 'Content-Type': 'application/json' } }) });
        const data = await res.json();
        document.getElementById('tool-loading').classList.add('hidden');
        if (!res.ok) {
            if (data.limit_reached) {
                closeToolModal();
                handleLimitReached();
            } else {
                throw new Error(data.error);
            }
            return;
        }

        updateCredits(data.questions_left);
        if (currentTool === 'quiz') { currentQuizData = data.quiz; currentQuizTopic = topic; renderQuiz(); }
        else {
            const content = data.notes || data.answer;
            document.getElementById('tool-result-data').innerHTML = marked.parse(content);
            document.getElementById('tool-result-data').classList.remove('hidden');
            document.getElementById('tool-result-actions').classList.remove('hidden');
            window.latestContent = content;
        }
    } catch (err) { alert(err.message); closeToolModal(); }
};

window.downloadAsPDF = async function () {
    const res = await fetch('/api/download-pdf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: currentTool.toUpperCase(), content: window.latestContent }) });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = "study_doc.pdf"; a.click();
};

function renderQuiz() {
    const container = document.getElementById('quiz-container');
    container.innerHTML = currentQuizData.map((q, i) => `
        <div class="bg-white/5 p-6 rounded-2xl border border-white/10 space-y-4">
            <p class="text-white font-medium">${i + 1}. ${q.question}</p>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                ${q.options.map(o => `<button onclick="selectOption(this, ${i}, '${o}')" class="quiz-option p-3 rounded-xl border border-white/10 text-gray-300 hover:bg-white/10 text-left transition-all">${o}</button>`).join('')}
            </div>
        </div>`).join('') + `<button onclick="submitQuiz()" class="w-full py-4 bg-green-600 hover:bg-green-500 text-white font-bold rounded-xl mt-8">Submit Quiz</button>`;
    container.classList.remove('hidden');
}

window.selectOption = (btn, i, opt) => {
    btn.parentElement.querySelectorAll('.quiz-option').forEach(b => b.classList.remove('bg-blue-600', 'text-white'));
    btn.classList.add('bg-blue-600', 'text-white');
    userAnswers[i] = opt;
};

window.submitQuiz = async () => {
    let score = 0; currentQuizData.forEach((q, i) => { if (userAnswers[i] === q.answer) score++; });
    const res = await fetch('/api/submit-quiz-score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ score, total: currentQuizData.length, topic: currentQuizTopic }) });
    const data = await res.json();
    document.getElementById('quiz-container').classList.add('hidden');
    document.getElementById('quiz-result').classList.remove('hidden');
    document.getElementById('quiz-score').textContent = `${score}/${currentQuizData.length}`;
    document.getElementById('quiz-xp-msg').textContent = `+${data.xp_earned} XP Earned!`;
};

function updateCredits(left) {
    if (left === undefined) return;
    ['credit-count', 'dash-credits'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = left; });
}

async function loadAnalytics() {
    const res = await fetch('/api/analytics');
    const data = await res.json();
    const ctx = document.getElementById('subjectsChart').getContext('2d');
    if (window.myChart) window.myChart.destroy();
    window.myChart = new Chart(ctx, { type: 'doughnut', data: { labels: Object.keys(data.subjects), datasets: [{ data: Object.values(data.subjects), backgroundColor: ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981'] }] }, options: { plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af' } } } } });
    document.getElementById('quiz-history-list').innerHTML = data.quiz_history.map(q => `<div class="flex justify-between p-3 bg-white/5 rounded-xl"><span>${q.topic}</span><span class="font-bold">${q.score}</span></div>`).join('');
}

async function loadLeaderboard() {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    document.getElementById('leaderboard-body').innerHTML = data.map((u, i) => `<tr><td class="px-6 py-4">#${i + 1}</td><td class="px-6 py-4">${u.username}</td><td class="px-6 py-4">${u.xp}</td><td class="px-6 py-4">Lvl ${u.level}</td></tr>`).join('');
}

// Update Class Logic
window.openUpdateClassModal = function () {
    document.getElementById('class-modal').classList.remove('hidden');
};

window.closeClassModal = function () {
    document.getElementById('class-modal').classList.add('hidden');
};

window.submitClassUpdate = async function () {
    const studentClass = document.getElementById('new-class-select').value;
    try {
        const res = await fetch('/api/update-class', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_class: studentClass })
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('current-class-display').textContent = data.new_class;
            closeClassModal();
            alert('Class updated successfully!');
        } else {
            alert(data.error || 'Failed to update class');
        }
    } catch (err) {
        alert('Network error');
    }
};
// Ad Flow Logic
let adTimerInterval = null;
window.startAdFlow = function () {
    const modal = document.getElementById('ad-modal');
    const timerEl = document.getElementById('ad-timer');
    const progressBar = document.getElementById('ad-progress-bar');
    const closeBtn = document.getElementById('close-ad-btn');
    const overlay = document.getElementById('ad-overlay-msg');

    modal.classList.remove('hidden');
    overlay.classList.remove('opacity-0');

    let timeLeft = 15;
    timerEl.textContent = timeLeft + 's';
    progressBar.style.width = '0%';
    closeBtn.disabled = true;
    closeBtn.textContent = 'Please wait...';
    closeBtn.className = 'w-full py-3 bg-gray-800 text-gray-500 rounded-xl font-bold transition-all disabled:cursor-not-allowed';

    // Hide overlay after 2 seconds to show the ad
    setTimeout(() => {
        overlay.classList.add('opacity-0');
        setTimeout(() => overlay.classList.add('hidden'), 500);
    }, 2000);

    clearInterval(adTimerInterval);
    adTimerInterval = setInterval(() => {
        timeLeft--;
        timerEl.textContent = timeLeft + 's';
        const progress = ((15 - timeLeft) / 15) * 100;
        progressBar.style.width = progress + '%';

        if (timeLeft <= 0) {
            clearInterval(adTimerInterval);
            timerEl.textContent = 'Reward Ready!';
            closeBtn.disabled = false;
            closeBtn.textContent = 'Claim Reward & Close';
            closeBtn.className = 'w-full py-3 bg-amber-600 hover:bg-amber-500 text-white rounded-xl font-bold shadow-lg shadow-amber-600/20 transition-all';
        }
    }, 1000);
};

window.closeAdFlow = async function () {
    const closeBtn = document.getElementById('close-ad-btn');
    if (closeBtn.disabled) return;

    try {
        const res = await fetch('/api/watch-ad', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            alert('Congratulations! You earned +1 question credit.');
            // Update UI
            const currentCredits = parseInt(document.getElementById('dash-credits').textContent);
            updateCredits(currentCredits + 1);
        }
    } catch (err) {
        console.error('Error claiming reward:', err);
    } finally {
        document.getElementById('ad-modal').classList.add('hidden');
        document.getElementById('ad-overlay-msg').classList.remove('hidden', 'opacity-0');
    }
};

// Auto-prompt ad when limit reached
function handleLimitReached() {
    if (confirm('You have reached your daily limit. Would you like to watch a short ad to get 1 more question?')) {
        startAdFlow();
    }
}
