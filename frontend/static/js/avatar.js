/* MISSMINUTES — SVG Avatar Renderer */
/* Clock-themed AI assistant with procedural animations */

const MissMinutesAvatar = (() => {
    let _state = 'idle';
    let _blinkInterval = null;
    let _breathInterval = null;
    let _thinkingInterval = null;
    let _speakingInterval = null;
    let _clockInterval = null;
    let _lookTimeout = null;
    let _container = null;
    let _label = null;

    const STATE_LABELS = {
        idle: 'Idle',
        listening: 'Listening',
        thinking: 'Thinking',
        working: 'Working',
        speaking: 'Speaking',
        success: 'Success',
        error: 'Error',
        concerned: 'Concerned',
        warning: 'Warning',
    };

    function init() {
        _container = document.getElementById('avatar-container');
        _label = document.getElementById('avatar-state-label');
        _startBlinking();
        _startClock();
        _startBreathing();
        _startEyeWander();
    }

    function _startBlinking() {
        if (_blinkInterval) clearInterval(_blinkInterval);
        _blinkInterval = setInterval(() => {
            if (_state === 'speaking' || _state === 'thinking') return;
            _blink();
        }, 3000 + Math.random() * 2000);
    }

    function _blink() {
        const leftLid = document.getElementById('left-eyelid');
        const rightLid = document.getElementById('right-eyelid');
        if (!leftLid || !rightLid) return;
        leftLid.setAttribute('ry', '14');
        rightLid.setAttribute('ry', '14');
        setTimeout(() => {
            leftLid.setAttribute('ry', '0');
            rightLid.setAttribute('ry', '0');
        }, 150);
    }

    function _startClock() {
        if (_clockInterval) clearInterval(_clockInterval);
        _clockInterval = setInterval(_updateClockHands, 1000);
        _updateClockHands();
    }

    function _updateClockHands() {
        const now = new Date();
        const hour = now.getHours() % 12;
        const minute = now.getMinutes();
        const second = now.getSeconds();
        const hourAngle = (hour + minute / 60) * 30;
        const minuteAngle = (minute + second / 60) * 6;
        const hourHand = document.getElementById('hour-hand');
        const minuteHand = document.getElementById('minute-hand');
        if (hourHand) hourHand.setAttribute('transform', `rotate(${hourAngle} 100 110)`);
        if (minuteHand) minuteHand.setAttribute('transform', `rotate(${minuteAngle} 100 110)`);
    }

    function _startBreathing() {
        if (_breathInterval) clearInterval(_breathInterval);
        let phase = 0;
        _breathInterval = setInterval(() => {
            if (_state !== 'idle' && _state !== 'listening') return;
            phase += 0.08;
            const bob = Math.sin(phase) * 2;
            const svg = document.getElementById('avatar-svg');
            if (svg) {
                const bodyParts = svg.querySelectorAll('.breath-group');
                bodyParts.forEach(el => {
                    el.style.transform = `translateY(${bob}px)`;
                });
            }
        }, 50);
    }

    function _startEyeWander() {
        function wander() {
            if (_state === 'thinking' || _state === 'working') return;
            const dx = (Math.random() - 0.5) * 6;
            const dy = (Math.random() - 0.5) * 4;
            _movePupils(dx, dy);
            _lookTimeout = setTimeout(wander, 2000 + Math.random() * 3000);
        }
        wander();
    }

    function _movePupils(dx, dy) {
        const lp = document.getElementById('left-pupil');
        const rp = document.getElementById('right-pupil');
        if (!lp || !rp) return;
        const clampX = Math.max(-5, Math.min(5, dx));
        const clampY = Math.max(-4, Math.min(4, dy));
        lp.setAttribute('cx', String(84 + clampX));
        lp.setAttribute('cy', String(105 + clampY));
        rp.setAttribute('cx', String(120 + clampX));
        rp.setAttribute('cy', String(105 + clampY));
    }

    function _startThinking() {
        if (_thinkingInterval) clearInterval(_thinkingInterval);
        let angle = 0;
        _thinkingInterval = setInterval(() => {
            angle += 3;
            _movePupils(Math.sin(angle * 0.05) * 3, -Math.cos(angle * 0.05) * 2);
        }, 50);
    }

    function _stopThinking() {
        if (_thinkingInterval) { clearInterval(_thinkingInterval); _thinkingInterval = null; }
    }

    function _startSpeaking() {
        if (_speakingInterval) clearInterval(_speakingInterval);
        const mouthLine = document.getElementById('mouth-line');
        const mouthOpen = document.getElementById('mouth-open');
        if (!mouthLine || !mouthOpen) return;
        _speakingInterval = setInterval(() => {
            const open = Math.random() > 0.3;
            const ry = open ? 4 + Math.random() * 6 : 0;
            mouthOpen.setAttribute('ry', String(ry));
            mouthOpen.setAttribute('opacity', open ? '1' : '0');
            mouthLine.setAttribute('opacity', open ? '0' : '1');
            if (open && Math.random() > 0.7) _blink();
        }, 100);
    }

    function _stopSpeaking() {
        if (_speakingInterval) { clearInterval(_speakingInterval); _speakingInterval = null; }
        const mouthLine = document.getElementById('mouth-line');
        const mouthOpen = document.getElementById('mouth-open');
        if (mouthLine) { mouthLine.setAttribute('opacity', '1'); }
        if (mouthOpen) { mouthOpen.setAttribute('ry', '0'); mouthOpen.setAttribute('opacity', '0'); }
    }

    function setState(newState) {
        if (_state === newState) return;
        const prev = _state;
        _state = newState;

        _stopThinking();
        _stopSpeaking();

        if (_container) {
            _container.className = 'avatar-container ' + newState;
        }
        if (_label) {
            _label.textContent = STATE_LABELS[newState] || newState;
        }

        switch (newState) {
            case 'idle':
                _movePupils(0, 0);
                break;
            case 'listening':
                _movePupils(0, 0);
                break;
            case 'thinking':
                _startThinking();
                break;
            case 'working':
                _startThinking();
                break;
            case 'speaking':
                _startSpeaking();
                break;
            case 'success':
                _blink();
                setTimeout(_blink, 300);
                break;
            case 'error':
                _movePupils(0, 2);
                break;
        }
    }

    function getState() { return _state; }

    return { init, setState, getState };
})();
