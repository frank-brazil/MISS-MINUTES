/* MISSMINUTES — Avatar Asset Loader & Expression Overlay */
/* Preloads expression PNGs and swaps overlays based on avatar state */

const MissMinutesAvatarAssets = (() => {
    const EXPRESSION_MAP = {
        idle: 'neutral',
        listening: 'neutral',
        thinking: 'thinking',
        working: 'neutral',
        speaking: 'happy',
        success: 'happy',
        error: 'sad',
        concerned: 'sad',
        warning: 'neutral',
    };

    const EXPRESSION_PATHS = {
        neutral: '/assets/character/neutral.png',
        happy: '/assets/character/happy.png',
        sad: '/assets/character/sad.png',
        surprised: '/assets/character/surprise.png',
        thinking: '/assets/character/thinking%26confuse.png',
        confused: '/assets/character/thinking%26confuse.png',
        angry: '/assets/character/angry.png',
    };

    const _images = {};
    let _overlayEl = null;
    let _currentExpression = null;
    let _loaded = false;

    function preload() {
        return new Promise((resolve) => {
            let loaded = 0;
            const total = Object.keys(EXPRESSION_PATHS).length;
            if (total === 0) { resolve(); return; }

            function checkDone() {
                loaded++;
                if (loaded >= total) {
                    _loaded = true;
                    resolve();
                }
            }

            Object.entries(EXPRESSION_PATHS).forEach(([name, path]) => {
                const img = new Image();
                img.onload = checkDone;
                img.onerror = checkDone;
                img.src = path;
                _images[name] = img;
            });
        });
    }

    function init() {
        _overlayEl = document.getElementById('avatar-expression-overlay');
        preload();
    }

    function applyExpression(expressionName) {
        if (!_overlayEl) return;
        if (_currentExpression === expressionName) return;
        _currentExpression = expressionName;

        const img = _images[expressionName];
        if (img && img.complete && img.naturalWidth > 0) {
            _overlayEl.src = img.src;
            _overlayEl.style.opacity = '1';
        } else {
            _overlayEl.src = '';
            _overlayEl.style.opacity = '0';
        }
    }

    function applyState(state) {
        const expr = EXPRESSION_MAP[state] || 'neutral';
        applyExpression(expr);
    }

    function isLoaded() { return _loaded; }

    return { init, preload, applyExpression, applyState, isLoaded, EXPRESSION_PATHS };
})();
