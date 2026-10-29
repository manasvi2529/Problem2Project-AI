/**
 * Problem2Project AI — Main Single Page Application
 * Handles routing, pages, live data science research, project creation, and approvals.
 */

const App = {
    currentRoute: 'home',
    activeSessionId: null,
    pollInterval: null,

    init() {
        Auth.init();
        this.setupRouting();
        this.setupGlobalEvents();
        this.checkApprovalsBadge();

        // Refresh badge every 30s
        setInterval(() => this.checkApprovalsBadge(), 30000);
    },

    setupRouting() {
        window.addEventListener('hashchange', () => this.handleRoute());
        this.handleRoute();
    },

    setupGlobalEvents() {
        document.querySelectorAll('.sidebar-menu .nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                document.querySelectorAll('.sidebar-menu .nav-item').forEach(n => n.classList.remove('active'));
                item.classList.add('active');
            });
        });
    },

    handleRoute() {
        const hash = window.location.hash.slice(1) || '/';
        const [path, param] = hash.split('/').filter(Boolean);
        const route = path || 'home';
        this.currentRoute = route;

        // Update nav active
        document.querySelectorAll('.sidebar-menu .nav-item').forEach(n => {
            const page = n.dataset.page;
            if (page === route) {
                n.classList.add('active');
            } else {
                n.classList.remove('active');
            }
        });

        // Clear active polling if navigating away
        if (this.pollInterval && route !== 'research') {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }

        // Render page
        const container = document.getElementById('page-container');
        if (!container) return;

        switch (route) {
            case 'home':
                this.renderHome(container);
                break;
            case 'research':
                this.renderResearch(container, param);
                break;
            case 'opportunities':
                this.renderOpportunities(container, param);
                break;
            case 'projects':
                this.renderProjects(container, param);
                break;
            case 'approvals':
                this.renderApprovals(container);
                break;
            case 'integrations':
                this.renderIntegrations(container);
                break;
            default:
                this.renderHome(container);
        }
    },

    refreshCurrentPage() {
        this.handleRoute();
        this.checkApprovalsBadge();
    },

    // ── Notifications ───────────────────────────────────────────────────────
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-msg">${this.escapeHtml(message)}</span>
            </div>
            <button class="toast-close">&times;</button>
        `;

        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });

        container.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('toast-fade');
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    },

    async checkApprovalsBadge() {
        if (!API.getToken()) return;
        try {
            const approvals = await API.listApprovals('pending');
            const badge = document.getElementById('approval-badge');
            if (badge) {
                if (approvals && approvals.length > 0) {
                    badge.textContent = approvals.length;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }
            }
        } catch {
            // Ignore badge fetch error
        }
    },

    // ── Pages: Home ─────────────────────────────────────────────────────────
    async renderHome(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Discover Real-World Problems</h1>
                    <p class="page-subtitle">Scrape live user pain points from Reddit, HackerNews & StackOverflow, analyze with Data Science, and build verified software solutions.</p>
                </div>
            </div>

            <div class="search-hero glass-card">
                <form id="hero-search-form" class="search-form">
                    <div class="search-input-group">
                        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                        <input type="text" id="hero-query" placeholder="e.g. data pipelines, customer onboarding, invoice reconciliation, devops bugs..." required>
                        <button type="submit" class="btn btn-primary" id="hero-search-btn">
                            <span>Discover Problems</span>
                        </button>
                    </div>

                    <div class="platform-selection">
                        <span class="platform-label">Data Sources:</span>
                        <label class="platform-check">
                            <input type="checkbox" name="platform" value="reddit" checked>
                            <span class="pill">Reddit</span>
                        </label>
                        <label class="platform-check">
                            <input type="checkbox" name="platform" value="hackernews" checked>
                            <span class="pill">Hacker News</span>
                        </label>
                        <label class="platform-check">
                            <input type="checkbox" name="platform" value="stackoverflow" checked>
                            <span class="pill">Stack Overflow</span>
                        </label>
                        <label class="platform-check">
                            <input type="checkbox" name="platform" value="devto" checked>
                            <span class="pill">Dev.to</span>
                        </label>
                        <label class="platform-check">
                            <input type="checkbox" name="platform" value="github_trending">
                            <span class="pill">GitHub Trending</span>
                        </label>
                    </div>
                </form>
            </div>

            <!-- Stats & Quick Actions -->
            <div class="stats-grid">
                <div class="stat-card glass-card">
                    <div class="stat-icon stat-purple">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Data Platforms</span>
                        <span class="stat-value">5 Live</span>
                        <span class="stat-desc">Reddit, HN, SO, Dev.to, GitHub</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-blue">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Data Science Pipeline</span>
                        <span class="stat-value">Pandas + NLP</span>
                        <span class="stat-desc">Pain Index & TF-IDF Clustering</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-green">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Active Projects</span>
                        <span class="stat-value" id="stat-project-count">-</span>
                        <span class="stat-desc">Opportunity to software</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-amber">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Pending Approvals</span>
                        <span class="stat-value" id="stat-approval-count">-</span>
                        <span class="stat-desc">Human-in-the-loop safety</span>
                    </div>
                </div>
            </div>

            <!-- Instant Platform Check Demo -->
            <div class="section-title-wrap">
                <h2>Quick Live Platform Probe</h2>
                <p>Instantly fetch real complaints and discussions from any community:</p>
            </div>

            <div class="platform-probe-grid">
                <button class="probe-card glass-card" data-platform="reddit" data-query="saas pain points">
                    <div class="probe-header">
                        <span class="badge badge-reddit">Reddit</span>
                        <span class="probe-arrow">&rarr;</span>
                    </div>
                    <h3>r/startups & r/SaaS</h3>
                    <p>Scrape real founder and user frustrations</p>
                </button>

                <button class="probe-card glass-card" data-platform="hackernews" data-query="ask hn frustrating">
                    <div class="probe-header">
                        <span class="badge badge-hn">Hacker News</span>
                        <span class="probe-arrow">&rarr;</span>
                    </div>
                    <h3>Ask HN Discussions</h3>
                    <p>Developer tooling gaps & workflows</p>
                </button>

                <button class="probe-card glass-card" data-platform="stackoverflow" data-query="memory leak python">
                    <div class="probe-header">
                        <span class="badge badge-so">Stack Overflow</span>
                        <span class="probe-arrow">&rarr;</span>
                    </div>
                    <h3>Developer Obstacles</h3>
                    <p>Unsolved engineering challenges</p>
                </button>

                <button class="probe-card glass-card" data-platform="github_trending" data-query="">
                    <div class="probe-header">
                        <span class="badge badge-github">GitHub</span>
                        <span class="probe-arrow">&rarr;</span>
                    </div>
                    <h3>Trending Repos</h3>
                    <p>See high-growth ecosystems</p>
                </button>
            </div>

            <div id="quick-probe-results" class="quick-probe-results hidden">
                <!-- Live probe results show here -->
            </div>
        `;

        // Load stat numbers
        this.loadHomeStats();

        // Bind form
        const form = document.getElementById('hero-search-form');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = document.getElementById('hero-query').value.trim();
            const checkedPlatforms = Array.from(document.querySelectorAll('input[name="platform"]:checked')).map(i => i.value);
            if (!query) return;

            if (!API.getToken()) {
                Auth.showModal('login');
                return;
            }

            try {
                this.showToast('Launching multi-platform discovery...', 'info');
                const res = await API.startDiscovery(query, checkedPlatforms);
                window.location.hash = `#/research/${res.session.id}`;
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        // Bind quick probe buttons
        document.querySelectorAll('.probe-card').forEach(card => {
            card.addEventListener('click', async () => {
                const platform = card.dataset.platform;
                const query = card.dataset.query || 'software tools';
                await this.runQuickProbe(platform, query);
            });
        });
    },

    async loadHomeStats() {
        if (!API.getToken()) return;
        try {
            const projects = await API.listProjects();
            const projectEl = document.getElementById('stat-project-count');
            if (projectEl) projectEl.textContent = (projects && projects.length) || 0;

            const approvals = await API.listApprovals('pending');
            const approvalEl = document.getElementById('stat-approval-count');
            if (approvalEl) approvalEl.textContent = (approvals && approvals.length) || 0;
        } catch {
            // Ignore
        }
    },

    async runQuickProbe(platform, query) {
        if (!API.getToken()) {
            Auth.showModal('login');
            return;
        }

        const resContainer = document.getElementById('quick-probe-results');
        if (!resContainer) return;

        resContainer.classList.remove('hidden');
        resContainer.innerHTML = `
            <div class="glass-card loading-card">
                <div class="btn-loader"></div>
                <p>Scraping live data from <strong>${platform}</strong> for "<em>${query}</em>"...</p>
            </div>
        `;

        try {
            const data = await API.quickSearch(platform, query);
            const items = data.results || [];
            const opps = data.data_science_ranked_opportunities || [];

            let html = `
                <div class="probe-results-header">
                    <h3>Live Probe Results: ${this.escapeHtml(platform)} (${items.length} posts found)</h3>
                    <button class="btn btn-sm btn-secondary" onclick="document.getElementById('quick-probe-results').classList.add('hidden')">Close</button>
                </div>
            `;

            if (opps.length > 0) {
                html += `
                    <div class="ds-pill-bar">
                        <span class="badge badge-purple">Data Science Opportunity Ranking</span>
                        <span>Top pain-weighted problem: <strong>${this.escapeHtml(opps[0].title)}</strong> (Pain: ${opps[0].metrics.pain_intensity}/10)</span>
                    </div>
                `;
            }

            html += `<div class="probe-items-grid">`;
            items.slice(0, 6).forEach(item => {
                html += `
                    <div class="glass-card probe-item-card">
                        <div class="probe-item-meta">
                            <span class="badge">${this.escapeHtml(item.platform)}</span>
                            <span class="text-muted">Score: ${item.score || 0}</span>
                            ${item.subreddit ? `<span class="text-muted">r/${this.escapeHtml(item.subreddit)}</span>` : ''}
                        </div>
                        <h4><a href="${item.url}" target="_blank" rel="noopener">${this.escapeHtml(item.title)}</a></h4>
                        <p class="probe-item-snippet">${this.escapeHtml((item.content || '').slice(0, 180))}...</p>
                    </div>
                `;
            });
            html += `</div>`;

            resContainer.innerHTML = html;
        } catch (err) {
            resContainer.innerHTML = `
                <div class="glass-card error-card">
                    <p>Failed to probe ${platform}: ${this.escapeHtml(err.message)}</p>
                </div>
            `;
        }
    },

    // ── Pages: Research / Discover ──────────────────────────────────────────
    async renderResearch(container, sessionId) {
        if (!API.getToken()) {
            container.innerHTML = `
                <div class="glass-card text-center p-8">
                    <h2>Sign in to run Research</h2>
                    <p class="text-muted">Access live scrapers, Data Science problem discovery, and research sessions.</p>
                    <button class="btn btn-primary mt-4" onclick="Auth.showModal('login')">Sign In</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Research & Platform Discovery</h1>
                    <p class="page-subtitle">Real-time scraper pipeline across Reddit, HackerNews, StackOverflow, and Dev communities.</p>
                </div>
                <div class="header-actions">
                    <button class="btn btn-secondary" id="btn-toggle-new-search">+ New Discovery</button>
                </div>
            </div>

            <!-- New Search Panel (Collapsible) -->
            <div id="new-search-panel" class="glass-card mb-6 ${sessionId ? 'hidden' : ''}">
                <h3>Start New Discovery Session</h3>
                <form id="research-search-form" class="mt-4">
                    <div class="form-group">
                        <label>Target Domain or Problem Area</label>
                        <input type="text" id="research-query" placeholder="e.g. data warehouse sync, slow tests, pdf extraction, api rate limits" required>
                    </div>
                    <div class="form-row">
                        <div class="form-group flex-1">
                            <label>Target Subreddits (comma separated, optional)</label>
                            <input type="text" id="research-subs" placeholder="e.g. startups, SaaS, webdev, datascience">
                        </div>
                    </div>
                    <div class="platform-selection mb-4">
                        <span class="platform-label">Platforms:</span>
                        <label class="platform-check"><input type="checkbox" name="r-plat" value="reddit" checked><span class="pill">Reddit</span></label>
                        <label class="platform-check"><input type="checkbox" name="r-plat" value="hackernews" checked><span class="pill">Hacker News</span></label>
                        <label class="platform-check"><input type="checkbox" name="r-plat" value="stackoverflow" checked><span class="pill">Stack Overflow</span></label>
                        <label class="platform-check"><input type="checkbox" name="r-plat" value="devto" checked><span class="pill">Dev.to</span></label>
                        <label class="platform-check"><input type="checkbox" name="r-plat" value="github_trending"><span class="pill">GitHub Trending</span></label>
                    </div>
                    <button type="submit" class="btn btn-primary" id="btn-start-research">
                        <span>Run Platform Scrapers & Data Science Analysis</span>
                    </button>
                </form>
            </div>

            <div id="session-detail-view" class="${sessionId ? '' : 'hidden'}">
                <div id="session-loading" class="glass-card text-center p-6">
                    <div class="btn-loader"></div>
                    <p class="mt-2">Connecting to research session...</p>
                </div>
                <div id="session-content" class="hidden"></div>
            </div>

            <div class="section-title-wrap mt-8">
                <h2>Past Research Sessions</h2>
                <p>Retained problem datasets and discovery logs</p>
            </div>
            <div id="sessions-list" class="sessions-list-grid">
                <div class="text-muted">Loading past sessions...</div>
            </div>
        `;

        // Toggle search panel
        const toggleBtn = document.getElementById('btn-toggle-new-search');
        const panel = document.getElementById('new-search-panel');
        if (toggleBtn && panel) {
            toggleBtn.addEventListener('click', () => {
                panel.classList.toggle('hidden');
            });
        }

        // Search submit
        const form = document.getElementById('research-search-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const q = document.getElementById('research-query').value.trim();
                const subsInput = document.getElementById('research-subs').value.trim();
                const subs = subsInput ? subsInput.split(',').map(s => s.trim().replace(/^r\//, '')) : [];
                const plats = Array.from(document.querySelectorAll('input[name="r-plat"]:checked')).map(i => i.value);

                if (!q) return;

                try {
                    const btn = document.getElementById('btn-start-research');
                    btn.disabled = true;
                    this.showToast('Starting multi-platform scraping...', 'info');
                    const res = await API.startDiscovery(q, plats, subs);
                    window.location.hash = `#/research/${res.session.id}`;
                } catch (err) {
                    this.showToast(err.message, 'error');
                }
            });
        }

        // Load past sessions
        this.loadSessionsList();

        // If specific session requested, load it
        if (sessionId) {
            this.activeSessionId = sessionId;
            this.loadSessionDetails(sessionId);
        }
    },

    async loadSessionsList() {
        const listEl = document.getElementById('sessions-list');
        if (!listEl) return;

        try {
            const sessions = await API.listResearchSessions();
            if (!sessions || sessions.length === 0) {
                listEl.innerHTML = `<div class="glass-card text-muted p-4">No past research sessions found. Run your first discovery above!</div>`;
                return;
            }

            listEl.innerHTML = sessions.map(s => `
                <div class="glass-card session-card ${this.activeSessionId === s.id ? 'session-card-active' : ''}" onclick="window.location.hash='#/research/${s.id}'">
                    <div class="session-card-header">
                        <span class="badge ${s.status === 'completed' ? 'badge-green' : (s.status === 'failed' ? 'badge-red' : 'badge-amber')}">${s.status}</span>
                        <span class="text-muted text-sm">${new Date(s.created_at).toLocaleDateString()}</span>
                    </div>
                    <h3 class="session-card-title">${this.escapeHtml(s.query)}</h3>
                    <div class="session-card-footer">
                        <span>${s.sources_count || 0} sources scraped</span>
                        <span>${s.problems_count || 0} problems extracted</span>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            listEl.innerHTML = `<div class="text-danger">Failed to load sessions: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async loadSessionDetails(sessionId) {
        const loadingEl = document.getElementById('session-loading');
        const contentEl = document.getElementById('session-content');
        const detailView = document.getElementById('session-detail-view');

        if (detailView) detailView.classList.remove('hidden');
        if (loadingEl) loadingEl.classList.remove('hidden');
        if (contentEl) contentEl.classList.add('hidden');

        const fetchDetails = async () => {
            try {
                const session = await API.getResearchSession(sessionId);
                const problems = await API.getProblems(sessionId);

                // Fetch data science analytics
                let analytics = null;
                try {
                    analytics = await API.getAnalytics(sessionId);
                } catch {
                    // Analytics might not be ready if session is still pending
                }

                if (loadingEl) loadingEl.classList.add('hidden');
                if (contentEl) contentEl.classList.remove('hidden');

                this.renderSessionContent(contentEl, session, problems, analytics);

                // If still running, poll
                if (session.status === 'pending' || session.status === 'searching' || session.status === 'analyzing') {
                    if (!this.pollInterval) {
                        this.pollInterval = setInterval(fetchDetails, 3000);
                    }
                } else {
                    if (this.pollInterval) {
                        clearInterval(this.pollInterval);
                        this.pollInterval = null;
                    }
                }
            } catch (err) {
                if (loadingEl) loadingEl.innerHTML = `<div class="text-danger">Error: ${this.escapeHtml(err.message)}</div>`;
            }
        };

        await fetchDetails();
    },

    renderSessionContent(container, session, problems, analytics) {
        const isRunning = session.status === 'pending' || session.status === 'searching' || session.status === 'analyzing';
        const stats = analytics?.statistics;

        let html = `
            <div class="glass-card mb-6">
                <div class="session-hero">
                    <div class="session-hero-left">
                        <span class="badge ${session.status === 'completed' ? 'badge-green' : (session.status === 'failed' ? 'badge-red' : 'badge-amber')}">
                            ${session.status.toUpperCase()}
                        </span>
                        <h2>Discovery: "${this.escapeHtml(session.query)}"</h2>
                        <p class="text-muted">Retained in SQLite Database &bull; Query ID: <code>${session.id.slice(0, 8)}</code></p>
                    </div>
                    <div class="session-hero-actions">
                        <a href="/api/discover/export/csv/${session.id}" class="btn btn-secondary btn-sm" download>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            <span>Export CSV</span>
                        </a>
                        <button class="btn btn-primary btn-sm" onclick="window.location.hash='#/opportunities/${session.id}'">
                            <span>View Evaluated Problems (${problems.length}) &rarr;</span>
                        </button>
                    </div>
                </div>

                ${isRunning ? `
                    <div class="progress-bar-wrap mt-4">
                        <div class="progress-bar progress-animated"></div>
                        <span class="text-sm text-muted mt-1 block">Live pipeline running: Scraping communities, computing pain metrics, and clustering problems...</span>
                    </div>
                ` : ''}

                <!-- Data Science Analytics Overview -->
                ${stats ? `
                    <div class="ds-metrics-panel mt-6">
                        <h4>Data Science Problem Analysis (Pandas & NLP)</h4>
                        <div class="ds-stats-row">
                            <div class="ds-stat-box">
                                <span class="ds-stat-label">Total Retained Sources</span>
                                <span class="ds-stat-num">${stats.total_items}</span>
                            </div>
                            <div class="ds-stat-box">
                                <span class="ds-stat-label">Avg Pain Intensity</span>
                                <span class="ds-stat-num text-danger">${stats.avg_pain_score}/10</span>
                            </div>
                            <div class="ds-stat-box">
                                <span class="ds-stat-label">Avg Urgency</span>
                                <span class="ds-stat-num text-warning">${stats.avg_urgency_score}/10</span>
                            </div>
                            <div class="ds-stat-box">
                                <span class="ds-stat-label">Max Priority Index</span>
                                <span class="ds-stat-num text-purple">${stats.highest_priority_score}/100</span>
                            </div>
                        </div>

                        ${stats.platforms ? `
                            <div class="platform-tags-row mt-3">
                                <strong>Platforms Queried:</strong>
                                ${Object.entries(stats.platforms).map(([plat, count]) => `
                                    <span class="badge">${plat}: ${count} posts</span>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                ` : ''}
            </div>

            <!-- Scraped Sources Stream -->
            <div class="section-title-wrap">
                <h3>Scraped Community Discussions & Evidence (${session.sources?.length || 0})</h3>
                <p>Authentic real-world user posts extracted from platforms</p>
            </div>

            <div class="sources-stream-grid">
                ${(session.sources || []).map(s => `
                    <div class="glass-card source-item-card">
                        <div class="source-item-meta">
                            <span class="badge badge-platform">${this.escapeHtml(s.source_type)}</span>
                            <span class="text-muted text-sm">${this.escapeHtml(s.publisher || '')}</span>
                            ${s.relevance_score ? `<span class="badge badge-sm">Score: ${s.relevance_score}</span>` : ''}
                        </div>
                        <h4><a href="${s.url}" target="_blank" rel="noopener">${this.escapeHtml(s.title || 'Community Thread')}</a></h4>
                        <p class="source-snippet">${this.escapeHtml(s.snippet || '')}</p>
                    </div>
                `).join('')}
            </div>
        `;

        container.innerHTML = html;
    },

    // ── Pages: Opportunities ────────────────────────────────────────────────
    async renderOpportunities(container, sessionId) {
        if (!API.getToken()) {
            container.innerHTML = `
                <div class="glass-card text-center p-8">
                    <h2>Sign in to view Opportunities</h2>
                    <button class="btn btn-primary mt-4" onclick="Auth.showModal('login')">Sign In</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Ranked Problem Opportunities</h1>
                    <p class="page-subtitle">Real-world issues validated through user discussions, ranked by viability, pain intensity, and feasibility.</p>
                </div>
            </div>

            <div id="opportunities-content">
                <div class="glass-card text-center p-6">
                    <div class="btn-loader"></div>
                    <p class="mt-2">Loading evaluated problems...</p>
                </div>
            </div>
        `;

        const contentEl = document.getElementById('opportunities-content');

        try {
            let problems = [];
            if (sessionId) {
                problems = await API.getProblems(sessionId);
            } else {
                // If no specific session, fetch from latest completed session
                const sessions = await API.listResearchSessions();
                const completed = sessions.find(s => s.status === 'completed');
                if (completed) {
                    problems = await API.getProblems(completed.id);
                }
            }

            if (!problems || problems.length === 0) {
                contentEl.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <h3>No Evaluated Problems Yet</h3>
                        <p class="text-muted">Start a Discovery session on Reddit, HackerNews, or StackOverflow to extract real problems.</p>
                        <button class="btn btn-primary mt-4" onclick="window.location.hash='#/research'">Go to Research & Discovery &rarr;</button>
                    </div>
                `;
                return;
            }

            // Render problem cards
            contentEl.innerHTML = `
                <div class="opportunities-grid">
                    ${problems.map(p => this.renderProblemCard(p)).join('')}
                </div>
            `;

            // Bind "Create Project" buttons
            document.querySelectorAll('.btn-create-project').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const probId = e.currentTarget.dataset.id;
                    const title = e.currentTarget.dataset.title;
                    const desc = e.currentTarget.dataset.desc;
                    await this.promptCreateProject(probId, title, desc);
                });
            });

        } catch (err) {
            contentEl.innerHTML = `<div class="glass-card text-danger">Failed to load opportunities: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    renderProblemCard(p) {
        const scores = p.scores || {};
        const overall = p.overall_score || 0;
        const painScore = scores.severity?.score || 7;
        const urgencyScore = scores.urgency?.score || 6;
        const feasibilityScore = scores.feasibility?.score || 8;

        return `
            <div class="glass-card opportunity-card">
                <div class="opp-card-header">
                    <div class="opp-rank-pill">#${p.rank || 1} &bull; Score ${overall}/10</div>
                    <span class="badge ${p.claim_type === 'source_backed' ? 'badge-green' : 'badge-blue'}">
                        ${p.claim_type === 'source_backed' ? 'Real Source-Backed' : 'Inference'}
                    </span>
                </div>

                <h3 class="opp-card-title">${this.escapeHtml(p.title)}</h3>
                <p class="opp-card-desc">${this.escapeHtml(p.description || '')}</p>

                <div class="opp-meta-grid">
                    <div class="opp-meta-item">
                        <span class="opp-meta-label">Target Users</span>
                        <span class="opp-meta-val">${this.escapeHtml(p.affected_users || 'Developers & Teams')}</span>
                    </div>
                    <div class="opp-meta-item">
                        <span class="opp-meta-label">Existing Gaps</span>
                        <span class="opp-meta-val">${this.escapeHtml(p.solution_gaps || 'Lack of specialized automation')}</span>
                    </div>
                </div>

                <!-- Scores Breakdown -->
                <div class="opp-scores-bar">
                    <div class="opp-score-col">
                        <span class="text-xs text-muted">Pain Severity</span>
                        <div class="score-meter"><div class="score-fill fill-red" style="width: ${painScore * 10}%"></div></div>
                        <span class="text-xs font-bold">${painScore}/10</span>
                    </div>
                    <div class="opp-score-col">
                        <span class="text-xs text-muted">Urgency</span>
                        <div class="score-meter"><div class="score-fill fill-amber" style="width: ${urgencyScore * 10}%"></div></div>
                        <span class="text-xs font-bold">${urgencyScore}/10</span>
                    </div>
                    <div class="opp-score-col">
                        <span class="text-xs text-muted">Feasibility</span>
                        <div class="score-meter"><div class="score-fill fill-green" style="width: ${feasibilityScore * 10}%"></div></div>
                        <span class="text-xs font-bold">${feasibilityScore}/10</span>
                    </div>
                </div>

                ${p.evidence_summary ? `
                    <div class="opp-evidence-box">
                        <span class="text-xs font-semibold text-muted">Community Evidence:</span>
                        <p class="text-xs text-muted">${this.escapeHtml(p.evidence_summary)}</p>
                    </div>
                ` : ''}

                <div class="opp-card-actions">
                    <button class="btn btn-primary btn-full btn-create-project" data-id="${p.id}" data-title="${this.escapeHtml(p.title)}" data-desc="${this.escapeHtml(p.description || '')}">
                        <span>Transform into Software Project &rarr;</span>
                    </button>
                </div>
            </div>
        `;
    },

    async promptCreateProject(probId, defaultTitle, defaultDesc) {
        const title = prompt('Enter a name for your software project:', defaultTitle);
        if (!title) return;

        try {
            this.showToast('Initializing software project workspace...', 'info');
            const res = await API.createProject(title, defaultDesc, probId);
            this.showToast('Project created successfully!', 'success');
            window.location.hash = `#/projects/${res.project.id}`;
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    // ── Pages: Projects ─────────────────────────────────────────────────────
    async renderProjects(container, projectId) {
        if (!API.getToken()) {
            container.innerHTML = `
                <div class="glass-card text-center p-8">
                    <h2>Sign in to view Projects</h2>
                    <button class="btn btn-primary mt-4" onclick="Auth.showModal('login')">Sign In</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Software Projects & Workflows</h1>
                    <p class="page-subtitle">Transform validated problem opportunities into real software repositories with AI execution.</p>
                </div>
                <div class="header-actions">
                    <button class="btn btn-primary" id="btn-new-project">+ New Project</button>
                </div>
            </div>

            <div id="projects-container">
                <div class="glass-card text-center p-6">
                    <div class="btn-loader"></div>
                    <p class="mt-2">Loading projects...</p>
                </div>
            </div>
        `;

        const btnNew = document.getElementById('btn-new-project');
        if (btnNew) {
            btnNew.addEventListener('click', () => {
                const title = prompt('Project Name:');
                if (!title) return;
                const desc = prompt('Brief description:');
                API.createProject(title, desc || '').then(res => {
                    this.showToast('Project created!', 'success');
                    window.location.hash = `#/projects/${res.project.id}`;
                }).catch(err => this.showToast(err.message, 'error'));
            });
        }

        const pContainer = document.getElementById('projects-container');

        if (projectId) {
            this.renderProjectDetail(pContainer, projectId);
        } else {
            this.renderProjectsList(pContainer);
        }
    },

    async renderProjectsList(container) {
        try {
            const projects = await API.listProjects();
            if (!projects || projects.length === 0) {
                container.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <h3>No Projects Yet</h3>
                        <p class="text-muted">Discover a problem on Reddit/HackerNews first, then transform it into a software project.</p>
                        <button class="btn btn-primary mt-4" onclick="window.location.hash='#/research'">Discover Problems &rarr;</button>
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div class="projects-grid">
                    ${projects.map(p => `
                        <div class="glass-card project-card" onclick="window.location.hash='#/projects/${p.id}'">
                            <div class="project-card-header">
                                <span class="badge badge-purple">${(p.current_stage || 'opportunity').toUpperCase()}</span>
                                <span class="badge ${p.status === 'active' ? 'badge-green' : 'badge-amber'}">${p.status}</span>
                            </div>
                            <h3>${this.escapeHtml(p.title)}</h3>
                            <p class="project-card-desc">${this.escapeHtml((p.description || '').slice(0, 140))}...</p>
                            <div class="project-card-footer">
                                <span>Mode: ${(p.operating_mode || 'hybrid').toUpperCase()}</span>
                                <span class="btn-link">Open Workspace &rarr;</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="glass-card text-danger">Failed to load projects: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async renderProjectDetail(container, projectId) {
        try {
            const res = await API.getProject(projectId);
            const p = res.project;
            const stages = ['opportunity', 'architecture', 'plan', 'execution', 'review'];
            const currentIdx = stages.indexOf(p.current_stage || 'opportunity');

            container.innerHTML = `
                <div class="glass-card mb-6">
                    <div class="project-detail-header">
                        <div>
                            <span class="badge badge-purple mb-2">PROJECT WORKSPACE</span>
                            <h2>${this.escapeHtml(p.title)}</h2>
                            <p class="text-muted">${this.escapeHtml(p.description || '')}</p>
                        </div>
                        <div class="project-header-actions">
                            <button class="btn btn-primary" id="btn-advance-workflow">
                                <span>Advance Workflow &rarr;</span>
                            </button>
                        </div>
                    </div>

                    <!-- Stage Progress Stepper -->
                    <div class="workflow-stepper mt-6">
                        ${stages.map((stage, idx) => `
                            <div class="step-item ${idx < currentIdx ? 'step-completed' : (idx === currentIdx ? 'step-active' : '')}">
                                <div class="step-circle">${idx < currentIdx ? '&#10003;' : (idx + 1)}</div>
                                <span class="step-label">${stage.toUpperCase()}</span>
                            </div>
                        `).join('<div class="step-line"></div>')}
                    </div>
                </div>

                <div class="project-workspace-grid">
                    <!-- Left: Architecture & Artifacts -->
                    <div class="glass-card">
                        <h3>Architecture & Solution Plan</h3>
                        <div class="mt-4">
                            <label class="text-xs font-semibold text-muted">Architecture Blueprint</label>
                            <pre class="code-box mt-1">${this.escapeHtml(p.architecture_spec || 'Architecture blueprint will be generated as you advance stages.')}</pre>
                        </div>
                    </div>

                    <!-- Right: Execution & Safety -->
                    <div class="glass-card">
                        <h3>Operating Mode & Approvals</h3>
                        <p class="text-muted text-sm mt-1">Current Mode: <strong>${(p.operating_mode || 'hybrid').toUpperCase()}</strong></p>
                        <div class="alert-box alert-info mt-4">
                            <strong>Safety Checkpoint Enabled:</strong> High-impact file writes and external integrations require explicit human approval.
                        </div>

                        <div class="mt-6">
                            <h4>Workflow State</h4>
                            <p class="text-sm text-muted">Status: ${p.status}</p>
                            <p class="text-sm text-muted">Repository: ${p.repository_name || 'Local AI Workspace'}</p>
                        </div>
                    </div>
                </div>
            `;

            // Bind advance button
            const advBtn = document.getElementById('btn-advance-workflow');
            if (advBtn) {
                advBtn.addEventListener('click', async () => {
                    try {
                        advBtn.disabled = true;
                        this.showToast('Advancing project workflow stage...', 'info');
                        const result = await API.advanceWorkflow(projectId);
                        this.showToast(`Advanced to ${result.project.current_stage.toUpperCase()}`, 'success');
                        this.renderProjectDetail(container, projectId);
                    } catch (err) {
                        this.showToast(err.message, 'error');
                        advBtn.disabled = false;
                    }
                });
            }

        } catch (err) {
            container.innerHTML = `<div class="glass-card text-danger">Failed to load project: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    // ── Pages: Approvals ────────────────────────────────────────────────────
    async renderApprovals(container) {
        if (!API.getToken()) {
            container.innerHTML = `
                <div class="glass-card text-center p-8">
                    <h2>Sign in to view Approvals</h2>
                    <button class="btn btn-primary mt-4" onclick="Auth.showModal('login')">Sign In</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Safety & Approvals Queue</h1>
                    <p class="page-subtitle">Human-in-the-loop checkpoints: Review and authorize AI actions before execution.</p>
                </div>
            </div>

            <div id="approvals-container">
                <div class="glass-card text-center p-6">
                    <div class="btn-loader"></div>
                    <p class="mt-2">Loading approvals...</p>
                </div>
            </div>
        `;

        const aContainer = document.getElementById('approvals-container');

        try {
            const approvals = await API.listApprovals('pending');
            if (!approvals || approvals.length === 0) {
                aContainer.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <div class="icon-circle icon-circle-green mb-3">&#10003;</div>
                        <h3>All Clear! No Pending Approvals</h3>
                        <p class="text-muted">The AI agent is running smoothly within authorized boundaries.</p>
                    </div>
                `;
                return;
            }

            aContainer.innerHTML = `
                <div class="approvals-grid">
                    ${approvals.map(a => `
                        <div class="glass-card approval-card" id="approval-${a.id}">
                            <div class="approval-card-header">
                                <span class="badge ${a.risk_level === 'high' ? 'badge-red' : (a.risk_level === 'medium' ? 'badge-amber' : 'badge-blue')}">
                                    ${(a.risk_level || 'medium').toUpperCase()} RISK
                                </span>
                                <span class="badge">${a.action_type}</span>
                            </div>
                            <h3>${this.escapeHtml(a.title || 'Action Request')}</h3>
                            <p class="approval-desc">${this.escapeHtml(a.description || '')}</p>
                            
                            ${a.blast_radius ? `
                                <div class="blast-radius-box">
                                    <span class="text-xs font-semibold">Blast Radius / Impact:</span>
                                    <p class="text-xs text-muted">${this.escapeHtml(a.blast_radius)}</p>
                                </div>
                            ` : ''}

                            <div class="approval-actions mt-4">
                                <button class="btn btn-primary btn-approve" data-id="${a.id}">Approve</button>
                                <button class="btn btn-secondary btn-reject" data-id="${a.id}">Reject</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;

            // Bind actions
            document.querySelectorAll('.btn-approve').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.currentTarget.dataset.id;
                    await this.respondApproval(id, 'approved');
                });
            });

            document.querySelectorAll('.btn-reject').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.currentTarget.dataset.id;
                    const reason = prompt('Reason for rejection (optional):') || '';
                    await this.respondApproval(id, 'rejected', reason);
                });
            });

        } catch (err) {
            aContainer.innerHTML = `<div class="glass-card text-danger">Failed to load approvals: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async respondApproval(id, decision, feedback = '') {
        try {
            await API.respondApproval(id, decision, feedback);
            this.showToast(`Request ${decision.toUpperCase()}`, decision === 'approved' ? 'success' : 'info');
            this.checkApprovalsBadge();
            this.renderApprovals(document.getElementById('page-container'));
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    // ── Pages: Integrations ─────────────────────────────────────────────────
    async renderIntegrations(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Integrations & System Health</h1>
                    <p class="page-subtitle">Multi-provider connections, scraper status, and Data Science runtime.</p>
                </div>
            </div>

            <div id="health-container">
                <div class="glass-card text-center p-6">
                    <div class="btn-loader"></div>
                    <p class="mt-2">Checking integration health...</p>
                </div>
            </div>
        `;

        const hContainer = document.getElementById('health-container');

        try {
            const health = await API.getHealth();
            const platforms = await API.getPlatforms();

            hContainer.innerHTML = `
                <div class="integrations-grid">
                    <!-- System Health Card -->
                    <div class="glass-card">
                        <h3>Core System Health</h3>
                        <div class="status-row mt-4">
                            <span>Service Status</span>
                            <span class="badge badge-green">${health.status.toUpperCase()}</span>
                        </div>
                        <div class="status-row">
                            <span>AI Provider</span>
                            <span class="badge ${health.integrations.ai.configured ? 'badge-green' : 'badge-amber'}">
                                ${health.integrations.ai.configured ? health.integrations.ai.provider : 'Not Configured (Using Data Science Engine)'}
                            </span>
                        </div>
                        <div class="status-row">
                            <span>Data Science Pipeline</span>
                            <span class="badge badge-green">PANDAS + SCIKIT-LEARN READY</span>
                        </div>
                        <div class="status-row">
                            <span>GitHub Integration</span>
                            <span class="badge ${health.integrations.github.configured ? 'badge-green' : 'badge-blue'}">
                                ${health.integrations.github.configured ? 'CONNECTED' : 'LOCAL WORKSPACE MODE'}
                            </span>
                        </div>
                    </div>

                    <!-- Scrapers Status Card -->
                    <div class="glass-card">
                        <h3>Platform Scrapers (No API Keys Required)</h3>
                        <div class="platforms-status-list mt-3">
                            ${(platforms.platforms || []).map(p => `
                                <div class="platform-status-item">
                                    <div>
                                        <strong>${this.escapeHtml(p.name)}</strong>
                                        <p class="text-xs text-muted">${this.escapeHtml(p.description)}</p>
                                    </div>
                                    <span class="badge badge-green">READY</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        } catch (err) {
            hContainer.innerHTML = `<div class="glass-card text-danger">Failed to check health: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    // ── Utilities ───────────────────────────────────────────────────────────
    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
};

window.App = App;

// Bootstrap once DOM ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
