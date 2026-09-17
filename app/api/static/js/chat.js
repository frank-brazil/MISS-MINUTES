/* MISSMINUTES — Chat UI */

const MissMinutesChat = (() => {
    let _conversation = null;
    let _input = null;
    let _sendBtn = null;
    let _micBtn = null;
    let _clearBtn = null;
    let _thinkingIndicator = null;
    let _welcomeScreen = null;
    let _messages = [];
    let _isProcessing = false;

    function init() {
        _conversation = document.getElementById('conversation');
        _input = document.getElementById('chat-input');
        _sendBtn = document.getElementById('btn-send');
        _micBtn = document.getElementById('btn-mic');
        _clearBtn = document.getElementById('btn-clear');
        _thinkingIndicator = document.getElementById('thinking-indicator');
        _welcomeScreen = document.getElementById('welcome-screen');

        _sendBtn.addEventListener('click', _send);
        _clearBtn.addEventListener('click', _clear);
        _micBtn.addEventListener('click', _mockMic);
        _input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                _send();
            }
        });

        document.getElementById('btn-toggle-sidebar').addEventListener('click', MissMinutesSidebar.toggleSidebar);

        MissMinutesAvatar.init();
        MissMinutesSidebar.log('System initialized', 'info');
        MissMinutesSidebar.log('Backend connected', 'success');
        MissMinutesSidebar.refreshStatus();
        setInterval(() => MissMinutesSidebar.refreshStatus(), 15000);

        _input.focus();
    }

    async function _send() {
        if (_isProcessing) return;
        const text = _input.value.trim();
        if (!text) return;

        _input.value = '';
        _hideWelcome();
        _addMessage('user', text);
        _setProcessing(true);
        _showThinking(true);

        MissMinutesAvatar.setState('listening');
        MissMinutesSidebar.log('User message received', 'info');

        setTimeout(() => {
            MissMinutesAvatar.setState('thinking');
            MissMinutesSidebar.log('Task created', 'info');
            MissMinutesTaskViz.setStage(0);
        }, 300);

        try {
            MissMinutesTaskViz.setStage(1);
            setTimeout(() => MissMinutesTaskViz.setStage(2), 300);
            setTimeout(() => MissMinutesTaskViz.setStage(3), 500);

            const response = await MissMinutesAPI.chat(text);

            MissMinutesTaskViz.setStage(4);
            setTimeout(() => MissMinutesTaskViz.setStage(5), 200);

            _showThinking(false);

            if (response.status === 'success') {
                MissMinutesAvatar.setState('speaking');
                _addMessage('assistant', response.message);
                MissMinutesSidebar.log('Response generated', 'success');
                MissMinutesTaskViz.complete();

                setTimeout(() => {
                    MissMinutesAvatar.setState('idle');
                }, 3000);
            } else {
                MissMinutesAvatar.setState('error');
                _addMessage('system', 'Error: ' + (response.message || 'Request failed'));
                MissMinutesSidebar.log('Error: ' + (response.message || 'Request failed'), 'error');
                MissMinutesTaskViz.reset();
                setTimeout(() => MissMinutesAvatar.setState('idle'), 2000);
            }
        } catch (err) {
            _showThinking(false);
            MissMinutesAvatar.setState('error');
            _addMessage('system', 'Connection error: ' + err.message);
            MissMinutesSidebar.log('Connection error', 'error');
            MissMinutesTaskViz.reset();
            setTimeout(() => MissMinutesAvatar.setState('idle'), 2000);
        }

        _setProcessing(false);
    }

    function _addMessage(role, content) {
        const msg = document.createElement('div');
        msg.className = `message ${role}`;
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
        if (role === 'user') {
            msg.innerHTML = `<div class="message-avatar">U</div><div><div class="message-content">${_escapeHtml(content)}</div><div class="message-time">${timeStr}</div></div>`;
        } else if (role === 'assistant') {
            msg.innerHTML = `<div class="message-avatar">M</div><div><div class="message-content">${_escapeHtml(content)}</div><div class="message-time">${timeStr}</div></div>`;
        } else {
            msg.innerHTML = `<div class="message-content">${_escapeHtml(content)}</div>`;
        }
        _conversation.insertBefore(msg, _thinkingIndicator);
        _conversation.scrollTop = _conversation.scrollHeight;
        _messages.push({ role, content, time: now });
    }

    function _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function _showThinking(show) {
        if (_thinkingIndicator) {
            _thinkingIndicator.classList.toggle('active', show);
        }
    }

    function _hideWelcome() {
        if (_welcomeScreen) {
            _welcomeScreen.style.display = 'none';
        }
    }

    function _setProcessing(processing) {
        _isProcessing = processing;
        if (_sendBtn) _sendBtn.disabled = processing;
        if (_input) _input.disabled = processing;
        if (_input && !processing) _input.focus();
    }

    function _clear() {
        const msgs = _conversation.querySelectorAll('.message');
        msgs.forEach(m => m.remove());
        _messages = [];
        if (_welcomeScreen) _welcomeScreen.style.display = '';
        MissMinutesTaskViz.reset();
        MissMinutesAvatar.setState('idle');
        MissMinutesSidebar.log('Conversation cleared', 'info');
    }

    function _mockMic() {
        _addMessage('system', 'Voice input is not connected yet. Configure a speech-to-text provider to enable voice.');
        MissMinutesSidebar.log('Voice input requested (not connected)', 'warning');
    }

    return { init };
})();

document.addEventListener('DOMContentLoaded', MissMinutesChat.init);
