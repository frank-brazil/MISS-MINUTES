/* MISSMINUTES — Sidebar: System Status & Activity Log */

const MissMinutesSidebar = (() => {
    const _activities = [];
    const MAX_ACTIVITIES = 50;

    function log(text, type = 'info') {
        const now = new Date();
        const time = now.toLocaleTimeString('en-US', { hour12: false });
        _activities.unshift({ time, text, type });
        if (_activities.length > MAX_ACTIVITIES) _activities.pop();
        _renderLog();
    }

    function _renderLog() {
        const container = document.getElementById('activity-log');
        if (!container) return;
        container.innerHTML = _activities.map(a =>
            `<div class="activity-entry"><span class="activity-time">${a.time}</span><span class="activity-text ${a.type}">${a.text}</span></div>`
        ).join('');
    }

    async function refreshStatus() {
        try {
            const status = await MissMinutesAPI.status();
            if (!status) return;
            const caps = status.capabilities || {};
            _updateItem('Backend', status.ready ? 'ready' : 'disabled', status.ready ? 'READY' : 'DOWN');
            _updateItem('Orchestrator', 'ready', 'READY');
            _updateItem('Memory', caps.memory ? 'ready' : 'disabled', caps.memory ? 'LOCAL' : 'NONE');
            _updateItem('Agents', caps.agents ? 'ready' : 'disabled', caps.agents ? 'READY' : 'NONE');
            _updateItem('Research', caps.research ? 'ready' : 'local', caps.research ? 'READY' : 'LOCAL');
            _updateItem('Browser', caps.browser ? 'ready' : 'local', caps.browser ? 'READY' : 'LOCAL');
            _updateItem('Voice', caps.voice ? 'ready' : 'local', caps.voice ? 'READY' : 'LOCAL');
            _updateItem('Avatar', caps.avatar ? 'ready' : 'local', caps.avatar ? 'READY' : 'LOCAL');
        } catch (e) {
            _updateItem('Backend', 'disabled', 'DOWN');
        }
    }

    function _updateItem(label, statusClass, valueText) {
        const grid = document.getElementById('status-grid');
        if (!grid) return;
        const items = grid.querySelectorAll('.status-item');
        items.forEach(item => {
            const lbl = item.querySelector('.label');
            if (lbl && lbl.textContent === label) {
                item.className = 'status-item ' + statusClass;
                const val = item.querySelector('.value');
                if (val) val.textContent = valueText;
            }
        });
    }

    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.toggle('collapsed');
    }

    return { log, refreshStatus, toggleSidebar };
})();
