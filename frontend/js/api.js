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

        let token = this.getToken();
        // If no token exists and not hitting auth endpoints, perform transparent developer sign-in
        if (!token && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/register')) {
            try {
                const autoResp = await fetch(`${this.baseUrl}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: 'developer@problempilot.ai', password: 'ProblemPilot123!' }),
                });
                if (autoResp.ok) {
                    const autoData = await autoResp.json();
                    token = autoData.access_token || autoData.token;
                    if (token) {
                        this.setToken(token);
                        this.setUser(autoData.user);
                    }
                }
            } catch (e) {
                // Ignore background auto-login errors and proceed
            }
        }

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            ...options,
            headers,
        };

        try {
            let resp = await fetch(url, config);
            
            // Handle 401 Unauthorized: attempt one automatic session restoration before failing
            if (resp.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/register')) {
                try {
                    const retryResp = await fetch(`${this.baseUrl}/api/auth/login`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: 'developer@problempilot.ai', password: 'ProblemPilot123!' }),
                    });
                    if (retryResp.ok) {
                        const retryData = await retryResp.json();
                        token = retryData.access_token || retryData.token;
                        if (token) {
                            this.setToken(token);
                            this.setUser(retryData.user);
                            headers['Authorization'] = `Bearer ${token}`;
                            resp = await fetch(url, { ...options, headers });
                        }
                    }
                } catch {
                    // Fall through to 401 handler below
                }
            }

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
        const token = data.access_token || data.token;
        if (token) {
            this.setToken(token);
            this.setUser(data.user);
        }
        return data;
    },

    async register(name, username, email, password) {
        const data = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({
                name,
                full_name: name,
                username,
                email,
                password,
            }),
        });
        const token = data.access_token || data.token;
        if (token) {
            this.setToken(token);
            this.setUser(data.user);
        }
        return data;
    },

    async getMe() {
        const data = await this.request('/api/auth/me');
        return data.user || data;
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
        const data = await this.request('/api/research/sessions');
        return Array.isArray(data) ? data : (data.sessions || []);
    },

    async getResearchSession(sessionId) {
        const data = await this.request(`/api/research/sessions/${encodeURIComponent(sessionId)}`);
        if (data && data.session) {
            return {
                ...data.session,
                sources: data.sources || [],
                problems: data.problems || [],
            };
        }
        return data;
    },

    async getProblems(sessionId) {
        const data = await this.request(`/api/research/sessions/${encodeURIComponent(sessionId)}/problems`);
        return Array.isArray(data) ? data : (data.problems || []);
    },

    // ── Projects ───────────────────────────────────────────────────────────
    async listProjects() {
        const data = await this.request('/api/projects');
        return Array.isArray(data) ? data : (data.projects || []);
    },

    async getProject(projectId) {
        const data = await this.request(`/api/projects/${encodeURIComponent(projectId)}`);
        if (data && data.project) {
            return {
                ...data.project,
                files: data.files || [],
            };
        }
        return data;
    },

    async createProject(title, description, problemCandidateId = null, repositoryName = '') {
        return await this.request('/api/projects', {
            method: 'POST',
            body: JSON.stringify({
                name: title,
                title: title,
                description: description || '',
                problem_id: problemCandidateId || '',
                problem_candidate_id: problemCandidateId || '',
                repository_name: repositoryName || '',
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
        const data = await this.request(`/api/approvals${query}`);
        return Array.isArray(data) ? data : (data.approvals || []);
    },

    async respondApproval(approvalId, decision, feedback = '') {
        return await this.request(`/api/approvals/${encodeURIComponent(approvalId)}/decide`, {
            method: 'POST',
            body: JSON.stringify({
                decision,
                reason: feedback,
                feedback,
            }),
        });
    },

    // ── Master Orchestrator (Prompt → Research → Build → Deploy) ────────────
    async startPromptJourney(prompt) {
        return await this.request('/api/orchestrator/prompt', {
            method: 'POST',
            body: JSON.stringify({ prompt }),
        });
    },

    async generateProjectBlueprint(projectId) {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/blueprint`, {
            method: 'POST',
        });
    },

    async buildWorkspace(projectId) {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/build`, {
            method: 'POST',
        });
    },

    async testWorkspace(projectId) {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/test`, {
            method: 'POST',
        });
    },

    async teachConcept(projectId, topic, level = 'intermediate') {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/teach`, {
            method: 'POST',
            body: JSON.stringify({ topic, level }),
        });
    },

    async syncGitHub(projectId, token, repositoryName = '', isPrivate = true) {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/github`, {
            method: 'POST',
            body: JSON.stringify({
                token,
                repository_name: repositoryName,
                private: isPrivate,
            }),
        });
    },

    async deployCloud(projectId, provider = 'vercel', verifyUrl = '') {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/deploy`, {
            method: 'POST',
            body: JSON.stringify({
                provider,
                verify_url: verifyUrl,
            }),
        });
    },

    async getWorkspaceFiles(projectId) {
        return await this.request(`/api/orchestrator/projects/${encodeURIComponent(projectId)}/files`);
    },

    // ── Integrations ──────────────────────────────────────────────────────
    async getIntegrationsStatus() {
        return await this.request('/api/integrations/status');
    },

    async authorizeGitHub() {
        return await this.request('/api/integrations/github/authorize');
    },

    async testGitHubConnection() {
        return await this.request('/api/integrations/github/test');
    },

    async disconnectGitHub() {
        return await this.request('/api/integrations/github', {
            method: 'DELETE',
        });
    },

    async verifyVercelConnection() {
        return await this.request('/api/integrations/vercel/verify');
    },

    async verifyRenderConnection() {
        return await this.request('/api/integrations/render/verify');
    },

    async getDeployments(projectId = '') {
        const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
        return await this.request(`/api/integrations/deployments${query}`);
    },

    // ── Health & System ────────────────────────────────────────────────────
    async getHealth() {
        return await this.request('/api/health');
    },
};

window.API = API;
