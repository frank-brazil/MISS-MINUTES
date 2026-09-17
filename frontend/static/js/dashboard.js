/* MISSMINUTES — Dashboard */

(async function() {
    try {
        const status = await MissMinutesAPI.status();
        if (status) {
            document.getElementById('stat-tasks').textContent = status.request_count || 0;
            const uptime = Math.floor(status.uptime_seconds || 0);
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('stat-uptime').textContent = h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
            document.getElementById('stat-agents').textContent = Object.keys(status.capabilities || {}).filter(k => status.capabilities[k]).length;

            const caps = status.capabilities || {};
            const subs = [
                { name: 'Backend', status: status.ready ? 'ready' : 'disabled', label: status.ready ? 'READY' : 'DOWN' },
                { name: 'Orchestrator', status: 'ready', label: 'READY' },
                { name: 'Memory', status: caps.memory ? 'ready' : 'not-configured', label: caps.memory ? 'ACTIVE' : 'NOT CONFIGURED' },
                { name: 'Agents', status: caps.agents ? 'ready' : 'not-configured', label: caps.agents ? 'ACTIVE' : 'NOT CONFIGURED' },
                { name: 'Research', status: caps.research ? 'ready' : 'local', label: caps.research ? 'READY' : 'LOCAL/FAKE' },
                { name: 'Browser', status: caps.browser ? 'ready' : 'local', label: caps.browser ? 'READY' : 'LOCAL' },
                { name: 'Voice', status: caps.voice ? 'ready' : 'local', label: caps.voice ? 'READY' : 'LOCAL' },
                { name: 'Avatar', status: caps.avatar ? 'ready' : 'local', label: caps.avatar ? 'READY' : 'LOCAL' },
                { name: 'Vision', status: caps.vision ? 'ready' : 'local', label: caps.vision ? 'READY' : 'LOCAL' },
                { name: 'Distributed', status: caps.distributed ? 'ready' : 'local', label: caps.distributed ? 'READY' : 'LOCAL' },
                { name: 'OpenRouter', status: 'not-configured', label: 'NOT CONFIGURED' },
                { name: 'Gemini', status: 'not-configured', label: 'NOT CONFIGURED' },
                { name: 'Groq', status: 'not-configured', label: 'NOT CONFIGURED' },
                { name: 'ElevenLabs', status: 'not-configured', label: 'NOT CONFIGURED' },
                { name: 'Brave Search', status: 'not-configured', label: 'NOT CONFIGURED' },
                { name: 'OpenAI', status: 'not-configured', label: 'NOT CONFIGURED' },
            ];
            const grid = document.getElementById('subsystems-grid');
            grid.innerHTML = subs.map(s =>
                `<div class="subsystem-card"><span class="subsystem-name">${s.name}</span><span class="subsystem-badge ${s.status}">${s.label}</span></div>`
            ).join('');
        }
    } catch (e) {
        console.error('Dashboard load failed:', e);
    }
})();
