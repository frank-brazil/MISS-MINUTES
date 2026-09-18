/* MISSMINUTES — Task Visualization */

const MissMinutesTaskViz = (() => {
    const STAGES = ['stage-understand', 'stage-plan', 'stage-agent', 'stage-tool', 'stage-verify', 'stage-respond'];
    let _currentStage = -1;
    let _autoTimer = null;

    function reset() {
        _currentStage = -1;
        _clearAll();
        if (_autoTimer) { clearTimeout(_autoTimer); _autoTimer = null; }
    }

    function _clearAll() {
        STAGES.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.classList.remove('active', 'completed');
            }
        });
    }

    function setStage(index) {
        _currentStage = index;
        _clearAll();
        for (let i = 0; i < index && i < STAGES.length; i++) {
            const el = document.getElementById(STAGES[i]);
            if (el) el.classList.add('completed');
        }
        if (index >= 0 && index < STAGES.length) {
            const el = document.getElementById(STAGES[index]);
            if (el) el.classList.add('active');
        }
    }

    function simulateProgress(callback) {
        reset();
        let i = 0;
        _autoTimer = setInterval(() => {
            if (i >= STAGES.length) {
                clearInterval(_autoTimer);
                _autoTimer = null;
                if (callback) callback();
                return;
            }
            setStage(i);
            i++;
        }, 400);
    }

    function complete() {
        _clearAll();
        STAGES.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.add('completed');
        });
        setTimeout(reset, 2000);
    }

    return { reset, setStage, simulateProgress, complete };
})();
