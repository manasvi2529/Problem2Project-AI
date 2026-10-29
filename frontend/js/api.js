/**
 * Problem2Project AI — API Client
 * Clean, robust wrapper for all backend endpoints.
 */

const API = {
    baseUrl: '',
    tokenKey: 'p2p_token',
    userKey: 'p2p_user',

    getToken() {
        return localStorage.getItem(this.tokenKey);
    },

    setToken(token) {
        if (token) {
            localStorage.setItem(this.tokenKey, token);
        } else {
            localStorage.removeItem(this.tokenKey);
        }
    },

    getUser() {
        const raw = localStorage.getItem(this.userKey);
        try {
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    },

    setUser(user) {
        if (user) {
            localStorage.setItem(this.userKey, JSON.stringify(user));
        } else {
            localStorage.removeItem(this.userKey);
        }
    },

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = options.headers || {};

        if (!options.isFormData && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }

        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            ...options,
            headers,
        };

        try {
            const resp = await fetch(url, config);
            
            // Handle 401 Unauthorized
            if (resp.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/register')) {
                this.setToken(null);
                this.setUser(null);
                window.dispatchEvent(new CustomEvent('auth:expired'));
                throw new Error('Session expired. Please sign in again.');
            }

            if (!resp.ok) {
                let errorMsg = `Request failed (${resp.status})`;
                try {
                    const errData = await resp.json();
                    errorMsg = errData.detail || errData.message || errorMsg;
                } catch {
                    // Ignore JSON parse errors on failure
                }
                throw new Error(errorMsg);
            }

            // Return json or blob based on response
            const contentType = resp.headers.get('content-type') || '';
            if (contentType.includes('text/csv')) {
                return await resp.text();
            }
            if (contentType.includes('application/json')) {
                return await resp.json();
            }
            return await resp.text();
        } catch (err) {
            console.error(`API Error [${endpoint}]:`, err);
            throw err;
        }
    },

    // ── Auth ────────────────────────────────────────────────────────────────
    async login(email, password) {
        const data = await this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        if (data.token) {
            this.setToken(data.token);
            this.setUser(data.user);
        }
        return data;
    },

    async register(name, username, email, password) {
        const data = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ name, username, email, password }),
        });
        if (data.token) {
            this.setToken(data.token);
            this.setUser(data.user);
        }
        return data;
    },

    async getMe() {
        return await this.request('/api/auth/me');
    },

    async updateSettings(settings) {
        return await this.request('/api/auth/settings', {
            method: 'PUT',
            body: JSON.stringify(settings),
        });
    },

    // ── Platform Discovery & Research ──────────────────────────────────────
    async getPlatforms() {
        return await this.request('/api/discover/platforms');
    },

    async quickSearch(platform, query) {
        return await this.request(`/api/discover/quick/${encodeURIComponent(platform)}?q=${encodeURIComponent(query)}`);
    },

    async startDiscovery(query, platforms = ['reddit', 'hackernews', 'stackoverflow', 'devto'], subreddits = []) {
        return await this.request('/api/discover/search', {
            method: 'POST',
            body: JSON.stringify({ query, platforms, subreddits }),
        });
    },

    async getAnalytics(sessionId) {
        return await this.request(`/api/discover/analytics/${encodeURIComponent(sessionId)}`);
    },

    async listResearchSessions() {
        return await this.request('/api/research/sessions');
    },

    async getResearchSession(sessionId) {
        return await this.request(`/api/research/sessions/${encodeURIComponent(sessionId)}`);
    },

    async getProblems(sessionId) {
        return await this.request(`/api/research/sessions/${encodeURIComponent(sessionId)}/problems`);
    },

    // ── Projects ───────────────────────────────────────────────────────────
    async listProjects() {
        return await this.request('/api/projects');
    },

    async getProject(projectId) {
        return await this.request(`/api/projects/${encodeURIComponent(projectId)}`);
    },

    async createProject(title, description, problemCandidateId = null, repositoryName = '') {
        return await this.request('/api/projects', {
            method: 'POST',
            body: JSON.stringify({
                title,
                description,
                problem_candidate_id: problemCandidateId,
                repository_name: repositoryName,
            }),
        });
    },

    async updateProject(projectId, data) {
        return await this.request(`/api/projects/${encodeURIComponent(projectId)}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    async getProjectState(projectId) {
        return await this.request(`/api/projects/${encodeURIComponent(projectId)}/state`);
    },

    async advanceWorkflow(projectId, targetStage = null) {
        return await this.request(`/api/projects/${encodeURIComponent(projectId)}/advance`, {
            method: 'POST',
            body: JSON.stringify({ target_stage: targetStage }),
        });
    },

    // ── Approvals ──────────────────────────────────────────────────────────
    async listApprovals(status = 'pending') {
        const query = status ? `?status=${encodeURIComponent(status)}` : '';
        return await this.request(`/api/approvals${query}`);
    },

    async respondApproval(approvalId, decision, feedback = '') {
        return await this.request(`/api/approvals/${encodeURIComponent(approvalId)}/respond`, {
            method: 'POST',
            body: JSON.stringify({ decision, feedback }),
        });
    },

    // ── Health & System ────────────────────────────────────────────────────
    async getHealth() {
        return await this.request('/api/health');
    },
};

window.API = API;
