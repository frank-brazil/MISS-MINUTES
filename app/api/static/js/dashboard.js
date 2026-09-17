/* MISSMINUTES — Dashboard page */
document.addEventListener('DOMContentLoaded', async () => {
    const statsGrid = document.getElementById('stats-grid');
    const subsysGrid = document.getElementById('subsystems-grid');
    if (!statsGrid || !subsysGrid) return;

    try {
        const status = await MissMinutesAPI.status();
        if (!status) { statsGrid.innerHTML = '<p style="color:var(--text-muted)">Unable to load status</p>'; return; }

        const caps = status.capabilities || {};
        statsGrid.innerHTML = `
            <div class="stat-card accent"><div class="label">Status</div><div class="value">${status.ready ? 'ONLINE' : 'OFFLINE'}</div></div>
            <div class="stat-card blue"><div class="label">Uptime</div><div class="value">${Math.floor(status.uptime_seconds / 60)}m</div><div class="sub">${Math.floor(status.uptime_seconds)}s total</div></div>
            <div class="stat-card green"><div class="label">Requests</div><div class="value">${status.request_count}</div></div>
        `;

        const subsystems = [
            { name: 'Backend', ready: status.ready },
            { name: 'Memory', ready: caps.memory },
            { name: 'Agents', ready: caps.agents },
            { name: 'Research', ready: caps.research },
            { name: 'Browser', ready: caps.browser },
            { name: 'Voice', ready: caps.voice },
            { name: 'Avatar', ready: caps.avatar },
        ];

        subsysGrid.innerHTML = subsystems.map(s =>
            `<div class="subsystem-card"><span class="subsystem-name">${s.name}</span><span class="subsystem-badge ${s.ready ? 'ready' : 'local'}">${s.ready ? 'READY' : 'LOCAL'}</span></div>`
        ).join('');
    } catch (e) {
        statsGrid.innerHTML = '<p style="color:var(--accent-red)">Error loading dashboard</p>';
    }
});
