/* MISSMINUTES — API Client */
const MissMinutesAPI = {
    baseUrl: '',

    async chat(message) {
        const res = await fetch(`${this.baseUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        return await res.json();
    },

    async health() {
        const res = await fetch(`${this.baseUrl}/health`);
        return await res.json();
    },

    async status() {
        const res = await fetch(`${this.baseUrl}/runtime/status`);
        if (!res.ok) return null;
        return await res.json();
    },

    async avatarState() {
        const res = await fetch(`${this.baseUrl}/api/avatar/state`);
        if (!res.ok) return null;
        return await res.json();
    },

    async avatarSignal(signal) {
        const res = await fetch(`${this.baseUrl}/api/avatar/signal?signal=${encodeURIComponent(signal)}`, {
            method: 'POST',
        });
        return await res.json();
    },

    async tasks(description) {
        const res = await fetch(`${this.baseUrl}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description }),
        });
        return await res.json();
    },
};
