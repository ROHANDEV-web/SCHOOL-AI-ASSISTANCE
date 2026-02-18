document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-container');
    const askForm = document.getElementById('ask-form');
    const userInput = document.getElementById('user-input');
    const creditCount = document.getElementById('credit-count');
    const dashCredit = document.getElementById('dash-credits');

    // Auto-resize textarea
    userInput?.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if(this.value === '') this.style.height = 'auto';
    });

    // Handle Enter key to submit
    userInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            askForm.dispatchEvent(new Event('submit'));
        }
    });

    askForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const question = userInput.value.trim();
        const subject = document.getElementById('subject-select').value;
        
        if (!question) return;

        // Add User Message
        appendMessage('User', question);
        userInput.value = '';
        userInput.style.height = 'auto';

        // Show loading state
        const loadingId = appendLoading();

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, subject })
            });

            const data = await response.json();
            
            // Remove loading
            document.getElementById(loadingId).remove();

            if (response.ok) {
                appendMessage('AI', data.answer);
                // Update credits
                if (data.questions_left !== undefined) {
                    if(creditCount) creditCount.textContent = data.questions_left;
                    if(dashCredit) dashCredit.textContent = data.questions_left;
                }
            } else {
                if (data.limit_reached) {
                    appendMessage('System', '⚠️ Daily limit reached! Watch an ad to get more questions.');
                } else {
                    appendMessage('System', 'Error: ' + (data.error || 'Something went wrong'));
                }
            }
        } catch (err) {
            document.getElementById(loadingId).remove();
            appendMessage('System', 'Network Error. Please try again.');
        }
    });

    function appendMessage(sender, text) {
        const div = document.createElement('div');
        div.className = 'flex gap-4 animate-fade-in';
        
        const isUser = sender === 'User';
        const isSystem = sender === 'System';
        
        const avatarColor = isUser ? 'bg-purple-600' : (isSystem ? 'bg-red-500' : 'bg-blue-500');
        const contentBg = isUser ? 'bg-blue-600/20 border-blue-600/30' : (isSystem ? 'bg-red-900/20 border-red-500/30' : 'glass-panel');
        const align = isUser ? 'flex-row-reverse' : 'flex-row';
        
        div.innerHTML = `
            <div class="${align} flex gap-4 w-full">
                <div class="w-8 h-8 rounded-full ${avatarColor} flex-shrink-0 flex items-center justify-center text-xs text-white font-bold">
                    ${isUser ? 'U' : 'AI'}
                </div>
                <div class="${contentBg} rounded-2xl p-4 max-w-[85%] border border-white/5 text-gray-200 overflow-hidden">
                    <div class="prose prose-invert prose-sm max-w-none">
                        ${isSystem ? text : marked.parse(text)}
                    </div>
                </div>
            </div>
        `;
        
        chatContainer.appendChild(div);
        
        // Highlight code blocks
        div.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendLoading() {
        const id = 'loading-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'flex gap-4 animate-fade-in';
        div.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-blue-500 flex-shrink-0 flex items-center justify-center text-xs text-white font-bold">AI</div>
            <div class="glass-panel rounded-2xl rounded-tl-none p-4 text-gray-400 flex items-center gap-2">
                <span class="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></span>
                <span class="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
                <span class="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
            </div>
        `;
        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return id;
    }
});

// Ad Watch Logic (Global Scope)
window.watchAd = function() {
    const modal = document.getElementById('ad-modal');
    const progress = document.getElementById('ad-progress');
    
    modal.classList.remove('hidden');
    let width = 0;
    
    // Simulate Ad Duration
    const interval = setInterval(() => {
        width += 2; // 50 steps * ~100ms = 5s
        progress.style.width = width + '%';
        
        if (width >= 100) {
            clearInterval(interval);
            completeAd();
        }
    }, 100);
    
    function completeAd() {
        fetch('/api/watch-ad', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    modal.classList.add('hidden');
                    alert('Reward Earned! You have 1 extra question.');
                    location.reload(); // Reload to update counters
                }
            });
    }
};
