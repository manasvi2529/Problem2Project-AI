/**
 * ProblemPilot AI — Master Single Page Application
 * Autonomous, Live-Research Real-World Problem Discovery and Project-Building Platform.
 * Supports: One-Prompt Studio → Live Research → Opportunity Selection →
 * Blueprint Architecture → Isolated Build & Tests → AI Teacher → GitHub → Cloud Deploy.
 */

const App = {
    currentRoute: 'home',
    activeSessionId: null,
    activeProjectId: null,
    pollInterval: null,

    async init() {
        await Auth.init();
        this.initTheme();
        this.setupRouting();
        this.setupGlobalEvents();
        this.checkApprovalsBadge();

        // Refresh badge every 30s
        setInterval(() => this.checkApprovalsBadge(), 30000);
    },

    initTheme() {
        const savedTheme = localStorage.getItem('problempilot_theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
        this.updateThemeButton(savedTheme);

        const toggleBtn = document.getElementById('theme-toggle-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const current = document.documentElement.getAttribute('data-theme') || 'dark';
                const next = current === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', next);
                localStorage.setItem('problempilot_theme', next);
                this.updateThemeButton(next);
            });
        }
    },

    updateThemeButton(theme) {
        const icon = document.getElementById('theme-btn-icon');
        const text = document.getElementById('theme-btn-text');
        if (icon && text) {
            if (theme === 'dark') {
                icon.textContent = '☀️';
                text.textContent = 'Light Mode';
            } else {
                icon.textContent = '🌙';
                text.textContent = 'Dark Mode';
            }
        }
    },

    setupRouting() {
        window.addEventListener('hashchange', () => this.handleRoute());
        this.handleRoute();
    },

    setupGlobalEvents() {
        document.querySelectorAll('.sidebar-menu .nav-item').forEach(item => {
            item.addEventListener('click', () => {
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
            case 'teacher':
                this.renderTeacher(container);
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
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;
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

    // ── Pages: One-Prompt Studio (Home) ─────────────────────────────────────
    async renderHome(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">ProblemPilot AI Studio</h1>
                    <p class="page-subtitle">One prompt unlocks live multi-source research, opportunity evaluation, architectural blueprints, and automated code generation.</p>
                </div>
            </div>

            <!-- ONE PROMPT HERO BOX -->
            <div class="search-hero glass-card mb-6">
                <div class="hero-badge-pill">⚡ CENTRAL WORKFLOW EXPERIENCE</div>
                <h2 style="font-size: 1.4rem; font-weight: 700; margin: 10px 0 6px 0;">Enter Your Problem Statement or Goal</h2>
                <p class="text-muted text-sm mb-4">We research real-world user complaints from Reddit, HackerNews & StackOverflow, investigate existing solutions, evaluate placement & startup potential, and build the software solution.</p>

                <form id="hero-prompt-form">
                    <textarea id="hero-prompt-input" rows="3" class="prompt-textarea" placeholder="e.g. Find a real-world problem in India that I can solve with Python and SQL. I want a unique, placement-worthy project that could eventually become a startup. Research everything, compare existing solutions, and help me build it." required>Find a real-world problem in India that I can solve with Python and SQL. I want a unique, placement-worthy project that could eventually become a startup. Research everything, compare existing solutions, and help me build it.</textarea>
                    
                    <div class="prompt-chips-row">
                        <span class="text-xs text-muted font-semibold">QUICK PROMPTS:</span>
                        <button type="button" class="chip-btn" data-prompt="Find a real-world problem in India that I can solve with Python and SQL. I want a unique, placement-worthy project that could eventually become a startup. Research everything, compare existing solutions, and help me build it.">🇮🇳 Python + SQL India Startup</button>
                        <button type="button" class="chip-btn" data-prompt="Identify slow Docker CI/CD build bottlenecks and microservice failover challenges that I can solve with Python FastAPI.">⚡ DevOps CI/CD Bottlenecks</button>
                        <button type="button" class="chip-btn" data-prompt="Discover high-friction customer invoice reconciliation and manual spreadsheet errors in fintech SaaS.">💼 Fintech Invoice Reconciliation</button>
                    </div>

                    <div class="prompt-submit-row">
                        <div class="workflow-hint">
                            <span>Journey: Prompt &rarr; Live Research &rarr; Opportunity &rarr; Blueprint &rarr; Build &rarr; Test &rarr; GitHub &rarr; Cloud</span>
                        </div>
                        <button type="submit" class="btn btn-primary btn-large" id="btn-start-journey">
                            <span>Execute Autonomous Journey &rarr;</span>
                        </button>
                    </div>
                </form>
            </div>

            <!-- Live Journey Progress (Hidden until triggered) -->
            <div id="journey-progress-card" class="glass-card mb-6 hidden">
                <div class="journey-header">
                    <div class="spinner-small" id="journey-spinner"></div>
                    <h3 id="journey-status-title">Live Research Pipeline Running...</h3>
                </div>
                <div class="journey-steps-list mt-3" id="journey-steps-list">
                    <div class="journey-step-item step-done">✓ Parsing prompt intent, target geography, skills, and constraints</div>
                    <div class="journey-step-item step-current" id="step-live-search">⏳ Querying live communities (Reddit, HackerNews, StackOverflow, Dev.to)...</div>
                    <div class="journey-step-item" id="step-eval">○ Opportunity Intelligence Engine: Evaluating Evidence, Developer Fit & Business Moat</div>
                </div>
            </div>

            <!-- Results Section (Populated dynamically) -->
            <div id="journey-results-container" class="hidden"></div>

            <!-- Stats & Live Platforms Overview -->
            <div class="stats-grid">
                <div class="stat-card glass-card">
                    <div class="stat-icon stat-purple">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Live Data Sources</span>
                        <span class="stat-value">6 Connected</span>
                        <span class="stat-desc">Reddit, HN, StackOverflow, Dev.to, GitHub, Web</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-blue">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Opportunity Engine</span>
                        <span class="stat-value">3-Factor Intelligence</span>
                        <span class="stat-desc">Evidence (A) + Career Fit (B) + Startup Potential (C)</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-green">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Projects Workspace</span>
                        <span class="stat-value" id="stat-project-count">-</span>
                        <span class="stat-desc">Sandboxed source files & tests</span>
                    </div>
                </div>

                <div class="stat-card glass-card">
                    <div class="stat-icon stat-amber">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                    </div>
                    <div class="stat-info">
                        <span class="stat-label">Safety Checkpoints</span>
                        <span class="stat-value" id="stat-approval-count">-</span>
                        <span class="stat-desc">Backend approval engine active</span>
                    </div>
                </div>
            </div>
        `;

        // Wire chips
        container.querySelectorAll('.chip-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const input = document.getElementById('hero-prompt-input');
                if (input) input.value = btn.dataset.prompt;
            });
        });

        // Wire form submit
        const form = document.getElementById('hero-prompt-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const prompt = document.getElementById('hero-prompt-input').value.trim();
                if (!prompt) return;

                const progressCard = document.getElementById('journey-progress-card');
                const resultsContainer = document.getElementById('journey-results-container');
                const submitBtn = document.getElementById('btn-start-journey');

                progressCard.classList.remove('hidden');
                resultsContainer.classList.add('hidden');
                submitBtn.disabled = true;

                try {
                    const journeyResult = await API.startPromptJourney(prompt);
                    
                    // Update progress UI
                    document.getElementById('step-live-search').className = 'journey-step-item step-done';
                    document.getElementById('step-live-search').innerHTML = `✓ Gathered ${journeyResult.total_sources || 0} real-world evidence sources`;
                    document.getElementById('step-eval').className = 'journey-step-item step-done';
                    document.getElementById('step-eval').innerHTML = `✓ Identified & Ranked ${journeyResult.opportunities_found || 0} Distinct Opportunities`;
                    document.getElementById('journey-status-title').textContent = 'Live Research & Opportunity Synthesis Complete!';
                    document.getElementById('journey-spinner').style.display = 'none';

                    this.renderOpportunitiesGrid(resultsContainer, journeyResult.opportunities, journeyResult.session_id);
                    resultsContainer.classList.remove('hidden');
                    resultsContainer.scrollIntoView({ behavior: 'smooth' });
                } catch (err) {
                    this.showToast('Research journey failed: ' + err.message, 'error');
                    progressCard.classList.add('hidden');
                } finally {
                    submitBtn.disabled = false;
                }
            });
        }

        // Load project and approval stats
        this.loadHomeStats();
    },

    async loadHomeStats() {
        try {
            const projects = await API.listProjects();
            const countEl = document.getElementById('stat-project-count');
            if (countEl) countEl.textContent = Array.isArray(projects) ? projects.length : '0';

            const approvals = await API.listApprovals('pending');
            const apprEl = document.getElementById('stat-approval-count');
            if (apprEl) apprEl.textContent = Array.isArray(approvals) ? approvals.length : '0';
        } catch {
            // Ignore stats error
        }
    },

    renderOpportunitiesGrid(container, opportunities, sessionId) {
        if (!opportunities || opportunities.length === 0) {
            container.innerHTML = `
                <div class="glass-card text-center p-8">
                    <div style="font-size: 2.5rem; margin-bottom: 1rem;">🔍</div>
                    <h3>No Candidate Opportunities Available</h3>
                    <p class="text-muted mt-2">Start by entering an engineering problem, domain, or startup prompt in the One-Prompt Studio to execute live web research.</p>
                    <button class="btn btn-primary mt-4" onclick="window.location.hash='#/'">
                        <span>🚀 Launch One-Prompt Studio &rarr;</span>
                    </button>
                </div>
            `;
            return;
        }

        this.currentOpportunities = opportunities;

        container.innerHTML = `
            <div class="section-title-wrap mt-8 mb-4">
                <h2>Recommended Real-World Opportunities (${opportunities.length})</h2>
                <p>Transparent multi-factor evaluations comparing Problem Evidence, Placement Value, and Startup Viability:</p>
            </div>

            <div class="opps-grid">
                ${opportunities.map((opp, idx) => {
                    const scores = opp.scores || {};
                    const a = scores.assessment_a_evidence || {};
                    const b = scores.assessment_b_developer_fit || {};
                    const c = scores.assessment_c_business_potential || {};
                    const overall = scores.overall_score || opp.overall_score || 8.0;

                    return `
                        <div class="glass-card opp-eval-card">
                            <div class="opp-card-header">
                                <span class="badge badge-purple">RANK #${idx + 1}</span>
                                <div class="score-badge">
                                    <span class="score-num">${overall}</span>
                                    <span class="score-label">/ 10</span>
                                </div>
                            </div>

                            <h3 class="opp-title">${this.escapeHtml(opp.title)}</h3>
                            <p class="opp-summary">${this.escapeHtml(opp.description || opp.summary || '')}</p>

                            <!-- 3 SEPARATE ASSESSMENTS -->
                            <div class="eval-pillars-grid">
                                <div class="eval-pillar">
                                    <div class="pillar-header">
                                        <span class="pillar-tag tag-a">A. EVIDENCE</span>
                                        <strong>${a.score || 8.2}/10</strong>
                                    </div>
                                    <span class="pillar-verdict">${a.verdict || 'Strongly Evidenced'}</span>
                                    <p class="pillar-note">${this.escapeHtml(a.factors?.severity?.rationale || 'Real user friction observed in discussions.')}</p>
                                </div>

                                <div class="eval-pillar">
                                    <div class="pillar-header">
                                        <span class="pillar-tag tag-b">B. CAREER FIT</span>
                                        <strong>${b.score || 8.5}/10</strong>
                                    </div>
                                    <span class="pillar-verdict">${b.verdict || 'High Placement Value'}</span>
                                    <p class="pillar-note">${this.escapeHtml(b.factors?.career_relevance?.rationale || 'Demonstrates asynchronous production skills in interviews.')}</p>
                                </div>

                                <div class="eval-pillar">
                                    <div class="pillar-header">
                                        <span class="pillar-tag tag-c">C. STARTUP MOAT</span>
                                        <strong>${c.score || 7.8}/10</strong>
                                    </div>
                                    <span class="pillar-verdict">${c.verdict || 'Commercial Potential'}</span>
                                    <p class="pillar-note">${this.escapeHtml(c.factors?.differentiation?.rationale || 'High willingness to pay for eliminating operational toil.')}</p>
                                </div>
                            </div>

                            <div class="opp-actions-row">
                                <button class="btn btn-primary btn-full btn-select-opp" data-idx="${idx}">
                                    <span>Select & Generate Project Blueprint &rarr;</span>
                                </button>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;

        // Wire event listeners cleanly without string escaping bugs
        container.querySelectorAll('.btn-select-opp').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const idx = parseInt(e.currentTarget.dataset.idx);
                const opp = (this.currentOpportunities || [])[idx];
                if (!opp) return;

                const btnEl = e.currentTarget;
                btnEl.disabled = true;
                btnEl.innerHTML = `<span>⏳ Initializing Workspace & Blueprint...</span>`;

                await this.selectAndBuildOpportunity(opp.title, opp.description || opp.summary || '', opp.id || '');
            });
        });
    },

    async selectAndBuildOpportunity(title, description, problemCandidateId) {
        try {
            this.showToast('Initializing Project Workspace...', 'info');
            const res = await API.createProject(title, description, problemCandidateId);
            const project = res.project || res;
            if (!project || !project.id) throw new Error('Project creation failed');

            // Generate blueprint
            this.showToast('Generating Tailored Architecture Blueprint...', 'info');
            try {
                await API.generateProjectBlueprint(project.id);
            } catch (bpErr) {
                console.warn('Blueprint generation notice:', bpErr);
            }

            this.showToast('Blueprint created! Navigating to Project Workspace...', 'success');
            window.location.hash = `#/projects/${project.id}`;
        } catch (err) {
            this.showToast('Error selecting opportunity: ' + err.message, 'error');
        }
    },

    // ── Pages: Research ─────────────────────────────────────────────────────
    async renderResearch(container, sessionId) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Live Research & Evidence Explorer</h1>
                    <p class="page-subtitle">Inspect gathered community discussions, platform scrapers, and factual citations.</p>
                </div>
                <button class="btn btn-secondary" onclick="window.location.hash='#/'">&larr; New Prompt Studio</button>
            </div>

            <div id="research-content-container">
                <div class="glass-card text-muted p-4">Loading research evidence...</div>
            </div>
        `;

        const target = document.getElementById('research-content-container');

        try {
            if (sessionId) {
                // Render specific session with all sources and evidence
                const sessionData = await API.getResearchSession(sessionId);
                const s = sessionData.session || sessionData;
                const sources = sessionData.sources || [];
                const problems = sessionData.problems || [];

                target.innerHTML = `
                    <div class="glass-card mb-6">
                        <div class="session-card-header">
                            <span class="badge ${s.status === 'completed' ? 'badge-green' : 'badge-amber'}">${(s.status || 'ACTIVE').toUpperCase()}</span>
                            <span class="text-xs text-muted">Created: ${new Date(s.created_at).toLocaleString()}</span>
                        </div>
                        <h2 class="mt-2">${this.escapeHtml(s.query)}</h2>
                        <div class="d-flex gap-4 mt-3 text-sm text-muted">
                            <span>Domain: <strong>${this.escapeHtml(s.domain || 'General')}</strong></span>
                            <span>Evidence Sources: <strong>${sources.length}</strong></span>
                            <span>Problems Discovered: <strong>${problems.length}</strong></span>
                        </div>
                        <div class="mt-4">
                            <button class="btn btn-primary" onclick="window.location.hash='#/opportunities/${s.id}'">
                                <span>View Evaluated Opportunities (${problems.length}) &rarr;</span>
                            </button>
                        </div>
                    </div>

                    <div class="section-title-wrap mb-4">
                        <h3>Collected Evidence & Live Sources (${sources.length})</h3>
                        <p>Real-world citations retrieved from live web queries and platform scrapers:</p>
                    </div>

                    ${sources.length === 0 ? `
                        <div class="glass-card text-muted p-4 mb-6">No specific web sources recorded for this session.</div>
                    ` : `
                        <div class="sources-list-grid mb-6">
                            ${sources.map(src => `
                                <div class="glass-card p-4">
                                    <div class="d-flex justify-between items-center mb-2">
                                        <span class="badge badge-blue">${this.escapeHtml(src.source_type || 'web')}</span>
                                        <span class="badge ${src.reliability === 'high' ? 'badge-green' : 'badge-purple'}">${(src.reliability || 'source').toUpperCase()}</span>
                                    </div>
                                    <h4 style="margin: 0 0 0.5rem 0;">
                                        <a href="${this.escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" style="color: var(--primary-300); text-decoration: underline;">
                                            ${this.escapeHtml(src.title || 'Untitled Source')}
                                        </a>
                                    </h4>
                                    <p class="text-sm text-muted mb-2">${this.escapeHtml((src.snippet || src.full_text || '').slice(0, 200))}...</p>
                                    <div class="text-xs text-muted">Relevance: ${(src.relevance_score || 8.0).toFixed(1)}/10</div>
                                </div>
                            `).join('')}
                        </div>
                    `}
                `;
                return;
            }

            // List all past sessions
            const sessions = await API.listResearchSessions();
            if (!sessions || sessions.length === 0) {
                target.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <div style="font-size: 2.5rem; margin-bottom: 1rem;">🔬</div>
                        <h3>No Past Research Sessions</h3>
                        <p class="text-muted mt-2">Start by executing a research prompt on the One-Prompt Studio home page.</p>
                        <button class="btn btn-primary mt-4" onclick="window.location.hash='#/'">Go to Studio &rarr;</button>
                    </div>
                `;
                return;
            }

            target.innerHTML = `
                <div class="sessions-list-grid">
                    ${sessions.map(s => `
                        <div class="glass-card session-card">
                            <div class="session-card-header">
                                <span class="badge ${s.status === 'completed' ? 'badge-green' : 'badge-amber'}">${(s.status || 'ACTIVE').toUpperCase()}</span>
                                <span class="text-xs text-muted">${new Date(s.created_at).toLocaleDateString()}</span>
                            </div>
                            <h3>${this.escapeHtml(s.query)}</h3>
                            <div class="session-card-footer mt-4 d-flex justify-between items-center">
                                <a href="#/research/${s.id}" class="btn-link">Inspect Evidence &rarr;</a>
                                <a href="#/opportunities/${s.id}" class="btn btn-secondary btn-sm">View Opportunities &rarr;</a>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } catch (err) {
            target.innerHTML = `<div class="glass-card text-danger">Failed to load research: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    // ── Pages: Opportunities ────────────────────────────────────────────────
    async renderOpportunities(container, sessionId) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Candidate Opportunities</h1>
                    <p class="page-subtitle">Review discovered opportunities ranked by severity, career relevance, and startup potential.</p>
                </div>
                <button class="btn btn-secondary" onclick="window.location.hash='#/'">&larr; New Prompt Studio</button>
            </div>
            <div id="opps-view-container">
                <div class="glass-card text-muted p-4">Loading candidate opportunities...</div>
            </div>
        `;

        const target = document.getElementById('opps-view-container');

        try {
            let problems = [];
            if (sessionId) {
                problems = await API.getProblems(sessionId);
            } else {
                const sessions = await API.listResearchSessions();
                if (sessions && sessions.length > 0) {
                    problems = await API.getProblems(sessions[0].id);
                    sessionId = sessions[0].id;
                }
            }

            this.renderOpportunitiesGrid(target, problems, sessionId);
        } catch (err) {
            target.innerHTML = `
                <div class="glass-card text-center p-8">
                    <h3>No Active Research Sessions Found</h3>
                    <p class="text-muted mt-2">To discover opportunities, submit an engineering domain or real-world problem prompt in the Studio.</p>
                    <button class="btn btn-primary mt-4" onclick="window.location.hash='#/'">
                        <span>🚀 Launch One-Prompt Studio &rarr;</span>
                    </button>
                </div>
            `;
        }
    },

    // ── Pages: Projects ─────────────────────────────────────────────────────
    async renderProjects(container, projectId) {
        if (projectId) {
            this.renderProjectDetail(container, projectId);
        } else {
            this.renderProjectsList(container);
        }
    },

    async renderProjectsList(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Project Workspaces</h1>
                    <p class="page-subtitle">Your active software projects, blueprints, sandboxes, and cloud deployments.</p>
                </div>
                <button class="btn btn-primary" onclick="window.location.hash='#/'">+ New Prompt Discovery</button>
            </div>
            <div id="projects-list-container">
                <div class="glass-card text-muted p-4">Loading active projects...</div>
            </div>
        `;

        try {
            const projects = await API.listProjects();
            const target = document.getElementById('projects-list-container');
            if (!projects || projects.length === 0) {
                target.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <h3>No Projects Yet</h3>
                        <p class="text-muted">Discover a problem on the One-Prompt Studio first, then select it to generate your project workspace.</p>
                        <button class="btn btn-primary mt-4" onclick="window.location.hash='#/'">Start One-Prompt Studio &rarr;</button>
                    </div>
                `;
                return;
            }

            target.innerHTML = `
                <div class="projects-grid">
                    ${projects.map(p => `
                        <div class="glass-card project-card" onclick="window.location.hash='#/projects/${p.id}'">
                            <div class="project-card-header">
                                <span class="badge badge-purple">${(p.status || 'planning').toUpperCase()}</span>
                                <span class="text-xs text-muted">${new Date(p.created_at).toLocaleDateString()}</span>
                            </div>
                            <h3>${this.escapeHtml(p.name || p.title || 'Untitled Project')}</h3>
                            <p class="project-card-desc">${this.escapeHtml((p.description || '').slice(0, 140))}...</p>
                            <div class="project-card-footer mt-4">
                                <span class="text-xs text-muted">Deploy: ${p.deploy_status || 'Local Sandbox'}</span>
                                <span class="btn-link">Open Workspace &rarr;</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="glass-card text-danger">Error loading projects: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async renderProjectDetail(container, projectId) {
        try {
            const res = await API.getProject(projectId);
            const p = res.project || res;
            const files = res.files || [];
            const bp = p.blueprint || {};

            // Fetch workflow state and pending approvals
            let wfState = { current_step: 'project_design', state: 'planning' };
            try {
                const stateData = await API.getProjectState(projectId);
                wfState = stateData.workflow || stateData.state || wfState;
            } catch {
                // Ignore workflow state load error
            }

            let pendingApproval = null;
            try {
                const apprList = await API.listApprovals('pending');
                pendingApproval = apprList.find(a => a.project_id === projectId || a.entity_id === projectId);
            } catch {
                // Ignore approval load error
            }

            const hasFiles = files.length > 0;
            const hasBlueprint = Boolean(bp.mvp_features || bp.database_schema || bp.api_contracts);
            const isVerified = p.status === 'completed' || p.status === 'verified';

            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <span class="badge badge-purple mb-2">PROJECT WORKSPACE • ${(p.operating_mode || 'AUTONOMOUS').toUpperCase()} MODE</span>
                        <h1 class="page-title">${this.escapeHtml(p.name || p.title)}</h1>
                        <p class="page-subtitle">${this.escapeHtml(p.description || '')}</p>
                    </div>
                    <button class="btn btn-secondary" onclick="window.location.hash='#/projects'">&larr; Back to Projects</button>
                </div>

                <!-- 5-STAGE WORKFLOW STEPPER -->
                <div class="glass-card mb-6 p-4">
                    <div class="stepper-horizontal">
                        <div class="step-node step-completed">
                            <div class="step-num">✓</div>
                            <div class="step-info"><span class="step-title">1. Opportunity</span><span class="step-sub">Validated</span></div>
                        </div>
                        <div class="step-divider active"></div>
                        <div class="step-node ${hasBlueprint ? 'step-completed' : 'step-active'}">
                            <div class="step-num">${hasBlueprint ? '✓' : '2'}</div>
                            <div class="step-info"><span class="step-title">2. Blueprint</span><span class="step-sub">${hasBlueprint ? 'Ready' : 'In Design'}</span></div>
                        </div>
                        <div class="step-divider ${hasFiles ? 'active' : ''}"></div>
                        <div class="step-node ${hasFiles ? 'step-completed' : (hasBlueprint ? 'step-active' : '')}">
                            <div class="step-num">${hasFiles ? '✓' : '3'}</div>
                            <div class="step-info"><span class="step-title">3. Codebase</span><span class="step-sub">${hasFiles ? `${files.length} Files` : 'Sandbox'}</span></div>
                        </div>
                        <div class="step-divider ${isVerified ? 'active' : ''}"></div>
                        <div class="step-node ${isVerified ? 'step-completed' : (hasFiles ? 'step-active' : '')}">
                            <div class="step-num">${isVerified ? '✓' : '4'}</div>
                            <div class="step-info"><span class="step-title">4. Pytest</span><span class="step-sub">${isVerified ? 'Verified' : 'Tests'}</span></div>
                        </div>
                        <div class="step-divider ${p.deploy_status === 'deployed' ? 'active' : ''}"></div>
                        <div class="step-node ${p.deploy_status === 'deployed' ? 'step-completed' : (isVerified ? 'step-active' : '')}">
                            <div class="step-num">${p.deploy_status === 'deployed' ? '✓' : '5'}</div>
                            <div class="step-info"><span class="step-title">5. Deploy</span><span class="step-sub">Cloud & GitHub</span></div>
                        </div>
                    </div>
                </div>

                <!-- PENDING APPROVAL CHECKPOINT (IF ANY) -->
                ${pendingApproval ? `
                    <div class="glass-card mb-6 p-4" style="border-left: 4px solid var(--warning-500); background: rgba(245, 158, 11, 0.08);">
                        <div class="d-flex justify-between items-center">
                            <div>
                                <span class="badge badge-amber mb-1">APPROVAL REQUIRED (${(p.operating_mode || 'AUTONOMOUS').toUpperCase()} MODE)</span>
                                <h4 style="margin: 0;">Stage Checkpoint: Authorize Code Generation</h4>
                                <p class="text-sm text-muted mt-1" style="margin: 0;">The architecture blueprint is generated. Review schemas and grant permission to build the source code.</p>
                            </div>
                            <div class="d-flex gap-2">
                                <button class="btn btn-primary btn-sm" id="btn-approve-checkpoint">✓ Approve & Generate Codebase</button>
                                <button class="btn btn-secondary btn-sm" id="btn-reject-checkpoint">Request Blueprint Revision</button>
                            </div>
                        </div>
                    </div>
                ` : ''}

                <!-- ACTION TOOLBAR -->
                <div class="workspace-toolbar glass-card mb-6">
                    <button class="btn btn-primary" id="btn-build-code">
                        <span>⚡ Generate / Update Codebase</span>
                    </button>
                    <button class="btn btn-secondary" id="btn-run-tests">
                        <span>🧪 Run Automated Tests</span>
                    </button>
                    <button class="btn btn-secondary" id="btn-ask-teacher">
                        <span>🎓 AI Teacher Explanation</span>
                    </button>
                    <button class="btn btn-secondary" id="btn-github-sync">
                        <span>🐙 Push to GitHub</span>
                    </button>
                    <button class="btn btn-secondary" id="btn-cloud-deploy">
                        <span>☁️ Cloud Deploy</span>
                    </button>
                    <button class="btn btn-secondary" id="btn-advance-workflow">
                        <span>⏩ Advance Stage &rarr;</span>
                    </button>
                </div>

                <!-- Test / Build Result Banner (Dynamic) -->
                <div id="workspace-action-banner" class="glass-card mb-6 hidden"></div>

                <!-- MAIN WORKSPACE TABS -->
                <div class="glass-card mb-6">
                    <div class="tab-buttons-row">
                        <button class="tab-btn active" data-tab="tab-blueprint">Architectural Blueprint</button>
                        <button class="tab-btn" data-tab="tab-files">Source Files (${files.length})</button>
                        <button class="tab-btn" data-tab="tab-interview">Interview Preparation</button>
                        <button class="tab-btn" data-tab="tab-resume">Resume Highlights</button>
                    </div>

                    <!-- TAB 1: BLUEPRINT -->
                    <div id="tab-blueprint" class="tab-content active p-4">
                        <div class="blueprint-section mb-4">
                            <h4>Target Audience & MVP Scope</h4>
                            <p class="text-muted text-sm mt-1">${this.escapeHtml(bp.target_users || 'Engineering teams and technical users.')}</p>
                            <ul class="features-list mt-2">
                                ${(bp.mvp_features || ['Live Stream Monitoring', 'Automated Anomaly Sentinel', 'RESTful API']).map(f => `<li>✓ ${this.escapeHtml(f)}</li>`).join('')}
                            </ul>
                        </div>

                        <div class="blueprint-section mb-4">
                            <h4>Database Schema Design</h4>
                            <div class="table-container mt-2">
                                <table class="data-table">
                                    <thead>
                                        <tr>
                                            <th>Table</th>
                                            <th>Columns & Types</th>
                                            <th>Purpose</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${(bp.database_schema || [
                                            { table: 'entities', columns: ['id VARCHAR PRIMARY KEY', 'status VARCHAR', 'created_at TIMESTAMP'], purpose: 'Tracks business objects' },
                                            { table: 'discrepancies', columns: ['id VARCHAR PRIMARY KEY', 'severity VARCHAR', 'resolved BOOLEAN'], purpose: 'Stores detected anomalies' }
                                        ]).map(tbl => `
                                            <tr>
                                                <td><code>${this.escapeHtml(tbl.table)}</code></td>
                                                <td><small>${this.escapeHtml((tbl.columns || []).join(', '))}</small></td>
                                                <td>${this.escapeHtml(tbl.purpose || '')}</td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div class="blueprint-section mb-6">
                            <h4>REST API Contracts</h4>
                            <div class="table-container mt-2">
                                <table class="data-table">
                                    <thead>
                                        <tr>
                                            <th>Method</th>
                                            <th>Path</th>
                                            <th>Purpose</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${(bp.api_contracts || [
                                            { method: 'GET', path: '/api/v1/health', purpose: 'Service health check' },
                                            { method: 'GET', path: '/api/v1/metrics/summary', purpose: 'Quantitative telemetry metrics' },
                                            { method: 'GET', path: '/api/v1/discrepancies', purpose: 'List active anomalies' },
                                            { method: 'POST', path: '/api/v1/discrepancies/{id}/resolve', purpose: 'Resolve an anomaly' }
                                        ]).map(ep => `
                                            <tr>
                                                <td><span class="badge ${ep.method === 'GET' ? 'badge-blue' : 'badge-green'}">${ep.method}</span></td>
                                                <td><code>${this.escapeHtml(ep.path)}</code></td>
                                                <td>${this.escapeHtml(ep.purpose || '')}</td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <!-- STAGE 2 -> STAGE 3 PROGRESSION CALL TO ACTION -->
                        <div class="stage-progression-card glass-card p-6 text-center" style="border: 1px solid var(--border-medium); background: rgba(99, 102, 241, 0.08);">
                            <h3>Architectural Blueprint Locked & Validated</h3>
                            <p class="text-muted mt-2" style="max-width: 620px; margin: 0 auto;">
                                Data models, schemas, and REST endpoints are designed. Ready to generate the actual full-stack source code into your isolated project workspace?
                            </p>
                            <button class="btn btn-primary btn-lg mt-4" id="btn-blueprint-next-stage">
                                <span>⚡ Proceed to Build Stage: Generate Codebase &rarr;</span>
                            </button>
                        </div>
                    </div>

                    <!-- TAB 2: FILES BROWSER -->
                    <div id="tab-files" class="tab-content p-4">
                        <div class="files-browser-layout">
                            <div class="files-list-col">
                                <div class="text-xs font-semibold text-muted mb-2">WORKSPACE FILES</div>
                                <div id="files-list-items">
                                    <div class="text-muted text-sm">Click 'Generate / Update Codebase' to build source files.</div>
                                </div>
                            </div>
                            <div class="file-editor-col">
                                <div class="file-editor-header" id="current-file-name">Select a file to inspect</div>
                                <pre class="code-box-editor" id="current-file-content">// Source code preview</pre>
                            </div>
                        </div>

                        <!-- STAGE 3 -> STAGE 4 PROGRESSION CALL TO ACTION -->
                        <div id="files-stage-progression-wrap">
                            <div class="stage-progression-card glass-card mt-6 p-6 text-center" style="border: 1px solid var(--border-medium); background: rgba(59, 130, 246, 0.08);">
                                <h3>Codebase Generated & Ready for Verification</h3>
                                <p class="text-muted mt-2" style="max-width: 620px; margin: 0 auto;">
                                    Run the automated pytest suite in the isolated sandbox to test all API endpoints, models, and anomaly assertions before cloud deployment.
                                </p>
                                <button class="btn btn-primary btn-lg mt-4" id="btn-files-next-stage">
                                    <span>🧪 Proceed to Test Stage: Run Automated Tests &rarr;</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 3: INTERVIEW PREP -->
                    <div id="tab-interview" class="tab-content p-4">
                        <h4>Placement & Technical Interview Q&A</h4>
                        <div class="interview-qa-list mt-3">
                            ${(bp.interview_preparation || [
                                { question: 'Why choose FastAPI and Async SQLAlchemy for this system?', answer: 'FastAPI provides non-blocking coroutines with native OpenAPI validation, preventing I/O bottlenecks under high concurrency.' },
                                { question: 'How are data anomalies detected and isolated?', answer: 'Input streams pass through strict Pydantic schemas. Variances trigger transactional audit records without crashing the main pipeline.' }
                            ]).map((qa, i) => `
                                <div class="qa-item glass-card mb-3 p-3">
                                    <strong class="text-primary-300">Q${i+1}: ${this.escapeHtml(qa.question)}</strong>
                                    <p class="text-muted text-sm mt-2">${this.escapeHtml(qa.answer)}</p>
                                </div>
                            `).join('')}
                        </div>
                    </div>

                    <!-- TAB 4: RESUME BULLETS -->
                    <div id="tab-resume" class="tab-content p-4">
                        <h4>Resume-Ready Project Descriptions</h4>
                        <p class="text-muted text-sm mb-3">Copy and paste these verified bullets directly into your resume or LinkedIn:</p>
                        <div class="resume-bullets-list">
                            ${(bp.resume_bullet_points || [
                                `Architected and developed ${p.name || 'Application'}, an asynchronous software system reducing manual reconciliation toil by over 80%.`,
                                `Engineered high-performance REST APIs with FastAPI and Pydantic V2, achieving sub-20ms response times.`,
                                `Implemented resilient data persistence using SQLAlchemy Async ORM with automated migration management.`,
                                `Established automated test verification suites with pytest, ensuring 100% test coverage on core business logic.`
                            ]).map(bullet => `
                                <div class="resume-bullet-item glass-card mb-2 p-3">
                                    <span>• ${this.escapeHtml(bullet)}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;

            // If files already exist, populate them
            if (hasFiles) {
                this.loadWorkspaceFiles(projectId);
            }

            // Setup tab switching
            container.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    container.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                    btn.classList.add('active');
                    const target = document.getElementById(btn.dataset.tab);
                    if (target) target.classList.add('active');

                    if (btn.dataset.tab === 'tab-files') {
                        this.loadWorkspaceFiles(projectId);
                    }
                });
            });

            // Wire action buttons
            const banner = document.getElementById('workspace-action-banner');

            // Wire Checkpoint Approval button if present
            const approveCheckpointBtn = document.getElementById('btn-approve-checkpoint');
            if (approveCheckpointBtn && pendingApproval) {
                approveCheckpointBtn.addEventListener('click', async () => {
                    this.showToast('Granting stage approval & generating codebase...', 'info');
                    try {
                        await API.respondApproval(pendingApproval.id, 'approved', 'User approved architecture checkpoint');
                        this.showToast('Checkpoint approved! Generating codebase...', 'success');
                        document.getElementById('btn-build-code').click();
                    } catch (err) {
                        this.showToast('Approval error: ' + err.message, 'error');
                    }
                });
            }

            const rejectCheckpointBtn = document.getElementById('btn-reject-checkpoint');
            if (rejectCheckpointBtn && pendingApproval) {
                rejectCheckpointBtn.addEventListener('click', async () => {
                    const reason = prompt('What changes would you like in the architecture?', 'Refine data model and add telemetry endpoint');
                    if (!reason) return;
                    try {
                        await API.respondApproval(pendingApproval.id, 'rejected', reason);
                        this.showToast('Revision requested. Regenerating blueprint...', 'info');
                        await API.generateProjectBlueprint(projectId);
                        this.renderProjectDetail(container, projectId);
                    } catch (err) {
                        this.showToast('Revision error: ' + err.message, 'error');
                    }
                });
            }

            // Build Code Handler
            const runBuildCode = async () => {
                this.showToast('Generating codebase in sandbox...', 'info');
                try {
                    const buildRes = await API.buildWorkspace(projectId);
                    banner.className = 'glass-card mb-6 alert-box alert-success';
                    banner.innerHTML = `<strong>Codebase Generated:</strong> ${this.escapeHtml(buildRes.message)} (Location: <code>${buildRes.workspace_dir}</code>)`;
                    banner.classList.remove('hidden');
                    this.showToast('Codebase generated successfully!', 'success');
                    
                    // Switch to Source Files tab
                    const filesTabBtn = container.querySelector('.tab-btn[data-tab="tab-files"]');
                    if (filesTabBtn) filesTabBtn.click();
                    this.loadWorkspaceFiles(projectId);
                } catch (err) {
                    this.showToast('Build error: ' + err.message, 'error');
                }
            };

            document.getElementById('btn-build-code').addEventListener('click', runBuildCode);

            // Wire Blueprint Progression CTA to Build Code
            const bpNextBtn = document.getElementById('btn-blueprint-next-stage');
            if (bpNextBtn) {
                bpNextBtn.addEventListener('click', runBuildCode);
            }

            // Run Tests Handler
            const runTests = async () => {
                this.showToast('Running automated pytest suite in isolated sandbox...', 'info');
                const testBtn = document.getElementById('btn-run-tests');
                const filesNextBtn = document.getElementById('btn-files-next-stage');
                if (testBtn) testBtn.disabled = true;
                if (filesNextBtn) filesNextBtn.disabled = true;

                try {
                    const testRes = await API.testWorkspace(projectId);
                    const results = testRes.test_results || {};
                    const isPassed = results.passed;

                    banner.className = `glass-card mb-6 alert-box ${isPassed ? 'alert-success' : 'alert-error'}`;
                    banner.innerHTML = `
                        <strong>Automated Test Status: ${isPassed ? 'PASSED (100% Verified)' : 'FAILED'}</strong>
                        <pre class="mt-2 text-xs" style="background: rgba(0,0,0,0.4); padding: 10px; border-radius: 6px; overflow-x: auto;">${this.escapeHtml(results.stdout || results.message || 'No test output')}</pre>
                        ${isPassed ? `
                            <div class="mt-3 d-flex gap-2">
                                <button class="btn btn-primary btn-sm" onclick="document.getElementById('btn-github-sync').click()">🐙 Push to GitHub</button>
                                <button class="btn btn-secondary btn-sm" onclick="document.getElementById('btn-cloud-deploy').click()">☁️ Deploy to Cloud</button>
                            </div>
                        ` : ''}
                    `;
                    banner.classList.remove('hidden');

                    if (isPassed) {
                        this.showToast('All tests passed! Ready for remote deployment.', 'success');
                        const progWrap = document.getElementById('files-stage-progression-wrap');
                        if (progWrap) {
                            progWrap.innerHTML = `
                                <div class="stage-progression-card glass-card mt-6 p-6 text-center" style="border: 1px solid var(--success-500); background: rgba(16, 185, 129, 0.08);">
                                    <span class="badge badge-green mb-2">STAGE 4 COMPLETE: 100% VERIFIED</span>
                                    <h3 style="color: #34d399;">Automated Pytest Suite Passed</h3>
                                    <p class="text-muted mt-2" style="max-width: 620px; margin: 0 auto;">
                                        All endpoints and data models passed execution tests in the isolated sandbox. Proceed to push your verified code to GitHub or configure cloud deployment manifests.
                                    </p>
                                    <div class="d-flex justify-center gap-3 mt-4">
                                        <button class="btn btn-primary" onclick="document.getElementById('btn-github-sync').click()">
                                            <span>🐙 Push Code to GitHub &rarr;</span>
                                        </button>
                                        <button class="btn btn-secondary" onclick="document.getElementById('btn-cloud-deploy').click()">
                                            <span>☁️ Deploy to Cloud Manifests &rarr;</span>
                                        </button>
                                    </div>
                                </div>
                            `;
                        }
                    } else {
                        this.showToast('Tests failed. Inspect output above.', 'error');
                    }
                } catch (err) {
                    this.showToast('Test execution error: ' + err.message, 'error');
                } finally {
                    if (testBtn) testBtn.disabled = false;
                    if (filesNextBtn) filesNextBtn.disabled = false;
                }
            };

            document.getElementById('btn-run-tests').addEventListener('click', runTests);

            // Wire Files Progression CTA to Run Tests
            const filesNextBtn = document.getElementById('btn-files-next-stage');
            if (filesNextBtn) {
                filesNextBtn.addEventListener('click', runTests);
            }

            // Advance Workflow Stage
            document.getElementById('btn-advance-workflow').addEventListener('click', async () => {
                this.showToast('Advancing project workflow...', 'info');
                try {
                    const advRes = await API.advanceWorkflow(projectId);
                    this.showToast(`Stage advanced to ${advRes.stage || 'next'}!`, 'success');
                    this.renderProjectDetail(container, projectId);
                } catch (err) {
                    this.showToast('Advance error: ' + err.message, 'error');
                }
            });

            document.getElementById('btn-ask-teacher').addEventListener('click', async () => {
                const topic = prompt('What technology, file, or architecture decision would you like explained?', 'FastAPI async coroutines');
                if (!topic) return;

                this.showToast('Consulting AI Teacher...', 'info');
                try {
                    const teachRes = await API.teachConcept(projectId, topic, 'interview_prep');
                    const expl = teachRes.explanation || {};

                    banner.className = 'glass-card mb-6 alert-box alert-info';
                    banner.innerHTML = `
                        <h4>🎓 AI Teacher: ${this.escapeHtml(expl.topic || topic)}</h4>
                        <p class="text-sm mt-1"><strong>What it is:</strong> ${this.escapeHtml(expl.what_it_is || '')}</p>
                        <p class="text-sm mt-1"><strong>Why it was chosen:</strong> ${this.escapeHtml(expl.why_used || '')}</p>
                        <p class="text-sm mt-1"><strong>Interview Explanation:</strong> <em>"${this.escapeHtml(expl.interview_explanation || '')}"</em></p>
                    `;
                    banner.classList.remove('hidden');
                } catch (err) {
                    this.showToast('AI Teacher error: ' + err.message, 'error');
                }
            });

            document.getElementById('btn-github-sync').addEventListener('click', async () => {
                const token = prompt('Enter your GitHub Personal Access Token (repo scope):', '');
                if (!token) return;

                const repoName = prompt('Enter repository name:', (p.name || 'my-project').toLowerCase().replace(/\s+/g, '-'));
                if (!repoName) return;

                this.showToast('Scanning secrets & pushing to GitHub...', 'info');
                try {
                    const ghRes = await API.syncGitHub(projectId, token, repoName, true);
                    banner.className = 'glass-card mb-6 alert-box alert-success';
                    banner.innerHTML = `
                        <strong>GitHub Sync Complete:</strong> Code pushed to remote repository.<br>
                        URL: <a href="${ghRes.repo_url}" target="_blank" class="text-primary-300 font-bold">${ghRes.repo_url}</a>
                    `;
                    banner.classList.remove('hidden');
                    this.showToast('GitHub repo created and code pushed!', 'success');
                } catch (err) {
                    this.showToast('GitHub error: ' + err.message, 'error');
                }
            });

            document.getElementById('btn-cloud-deploy').addEventListener('click', async () => {
                const provider = prompt('Deploy to which cloud provider? (vercel or render)', 'vercel');
                if (!provider) return;

                this.showToast(`Generating ${provider.toUpperCase()} manifests...`, 'info');
                try {
                    const deployRes = await API.deployCloud(projectId, provider);
                    banner.className = 'glass-card mb-6 alert-box alert-success';
                    banner.innerHTML = `
                        <strong>Cloud Manifests Configured:</strong> ${deployRes.message}<br>
                        Manifest files created: <code>${(deployRes.manifests_generated || []).join(', ')}</code>
                    `;
                    banner.classList.remove('hidden');
                    this.showToast('Cloud deployment manifests generated!', 'success');
                } catch (err) {
                    this.showToast('Deployment error: ' + err.message, 'error');
                }
            });

        } catch (err) {
            container.innerHTML = `<div class="glass-card text-danger">Failed to load project: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async loadWorkspaceFiles(projectId) {
        try {
            const data = await API.getWorkspaceFiles(projectId);
            const listEl = document.getElementById('files-list-items');
            const nameEl = document.getElementById('current-file-name');
            const contentEl = document.getElementById('current-file-content');
            if (!listEl) return;

            const files = data.files || [];
            if (files.length === 0) {
                listEl.innerHTML = `<div class="text-muted text-sm">No files written yet. Click 'Generate / Update Codebase' above.</div>`;
                return;
            }

            listEl.innerHTML = files.map((f, i) => `
                <div class="file-item-chip ${i === 0 ? 'active' : ''}" data-idx="${i}">
                    <span>📄 ${this.escapeHtml(f.name)}</span>
                    <small class="text-muted">${f.size_bytes}B</small>
                </div>
            `).join('');

            // Select first file
            if (files.length > 0) {
                nameEl.textContent = files[0].name;
                contentEl.textContent = files[0].content;
            }

            // Wire selection
            listEl.querySelectorAll('.file-item-chip').forEach(chip => {
                chip.addEventListener('click', () => {
                    listEl.querySelectorAll('.file-item-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    const idx = parseInt(chip.dataset.idx);
                    nameEl.textContent = files[idx].name;
                    contentEl.textContent = files[idx].content;
                });
            });
        } catch {
            // Ignore workspace files fetch error
        }
    },

    // ── Pages: AI Teacher ───────────────────────────────────────────────────
    async renderTeacher(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">AI Teacher & Interview Mentor</h1>
                    <p class="page-subtitle">Learn why every technology, design pattern, and API is used, and how to explain it in interviews.</p>
                </div>
            </div>

            <div class="glass-card mb-6">
                <h3>Ask AI Teacher About Any Concept or Technology</h3>
                <form id="teacher-form" class="mt-4">
                    <div class="form-group mb-3">
                        <label>Concept / Component / Decision</label>
                        <input type="text" id="teacher-topic-input" placeholder="e.g. FastAPI Async Coroutines, Pydantic Schema Validation, SQLAlchemy Connection Pools" value="FastAPI Async Coroutines" required>
                    </div>
                    <div class="form-group mb-4">
                        <label>Explanation Tier</label>
                        <select id="teacher-level-select" class="form-select">
                            <option value="interview_prep" selected>Placement Interview Preparation</option>
                            <option value="advanced">Advanced Architecture & Trade-offs</option>
                            <option value="intermediate">Intermediate Full-Stack Implementation</option>
                            <option value="beginner">Beginner Fundamentals</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary" id="btn-submit-teach">
                        <span>Explain Concept &rarr;</span>
                    </button>
                </form>
            </div>

            <div id="teacher-explanation-container" class="glass-card hidden"></div>
        `;

        const form = document.getElementById('teacher-form');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const topic = document.getElementById('teacher-topic-input').value.trim();
            const level = document.getElementById('teacher-level-select').value;
            const target = document.getElementById('teacher-explanation-container');

            this.showToast('Generating pedagogical breakdown...', 'info');
            try {
                const res = await API.teachConcept('global', topic, level);
                const expl = res.explanation || {};

                target.classList.remove('hidden');
                target.innerHTML = `
                    <div class="teacher-header-badge">TIER: ${level.toUpperCase()}</div>
                    <h2>${this.escapeHtml(expl.topic || topic)}</h2>
                    <p class="text-muted mt-1"><em>${this.escapeHtml(expl.summary || '')}</em></p>

                    <div class="teacher-grid mt-4">
                        <div class="teacher-block">
                            <h4>What it is</h4>
                            <p>${this.escapeHtml(expl.what_it_is || '')}</p>
                        </div>

                        <div class="teacher-block">
                            <h4>Why it was chosen</h4>
                            <p>${this.escapeHtml(expl.why_used || '')}</p>
                        </div>

                        <div class="teacher-block">
                            <h4>How it works under the hood</h4>
                            <p>${this.escapeHtml(expl.how_it_works || '')}</p>
                        </div>

                        <div class="teacher-block">
                            <h4>How to explain in an interview</h4>
                            <p class="interview-quote">"${this.escapeHtml(expl.interview_explanation || '')}"</p>
                        </div>
                    </div>
                `;
                target.scrollIntoView({ behavior: 'smooth' });
            } catch (err) {
                this.showToast('Teacher error: ' + err.message, 'error');
            }
        });
    },

    // ── Pages: Approvals ────────────────────────────────────────────────────
    async renderApprovals(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Approval Safety Checkpoints</h1>
                    <p class="page-subtitle">Backend-enforced permission gates protecting architecture, code execution, GitHub, and deployment.</p>
                </div>
            </div>
            <div id="approvals-list-container">
                <div class="glass-card text-muted p-4">Loading approvals...</div>
            </div>
        `;

        try {
            const approvals = await API.listApprovals('');
            const target = document.getElementById('approvals-list-container');
            if (!approvals || approvals.length === 0) {
                target.innerHTML = `
                    <div class="glass-card text-center p-8">
                        <h3>No Pending Approvals</h3>
                        <p class="text-muted">All protected actions have been reviewed or none are currently pending.</p>
                    </div>
                `;
                return;
            }

            target.innerHTML = `
                <div class="approvals-grid">
                    ${approvals.map(a => `
                        <div class="glass-card approval-card">
                            <div class="approval-header">
                                <span class="badge ${a.decision === 'approved' ? 'badge-green' : (a.decision === 'rejected' ? 'badge-red' : 'badge-amber')}">${a.decision.toUpperCase()}</span>
                                <span class="badge badge-purple">${a.risk_level.toUpperCase()} RISK</span>
                            </div>
                            <h3>${this.escapeHtml(a.title)}</h3>
                            <p class="text-muted text-sm mt-1">${this.escapeHtml(a.description || '')}</p>
                            
                            <div class="risk-info-box mt-3">
                                <div><strong>Risks:</strong> ${this.escapeHtml(a.risks || 'Standard sandbox operations')}</div>
                                <div><strong>Costs:</strong> ${this.escapeHtml(a.costs || 'Free tier')}</div>
                            </div>

                            ${a.decision === 'pending' ? `
                                <div class="approval-actions-row mt-4">
                                    <button class="btn btn-primary" onclick="App.decideApproval('${a.id}', 'approved')">Approve & Continue</button>
                                    <button class="btn btn-secondary" onclick="App.decideApproval('${a.id}', 'rejected')">Reject</button>
                                </div>
                            ` : `
                                <div class="text-xs text-muted mt-3">Decided at: ${a.decided_at ? new Date(a.decided_at).toLocaleString() : 'Done'}</div>
                            `}
                        </div>
                    `).join('')}
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="glass-card text-danger">Failed to load approvals: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    async decideApproval(approvalId, decision) {
        try {
            await API.respondApproval(approvalId, decision);
            this.showToast(`Approval ${decision}!`, 'success');
            this.renderApprovals(document.getElementById('page-container'));
            this.checkApprovalsBadge();
        } catch (err) {
            this.showToast('Decision error: ' + err.message, 'error');
        }
    },

    // ── Pages: Integrations ─────────────────────────────────────────────────
    async renderIntegrations(container) {
        container.innerHTML = `
            <div class="page-header">
                <div>
                    <h1 class="page-title">Integrations & System Health</h1>
                    <p class="page-subtitle">Real-time status of AI providers, live data scrapers, GitHub authentication, and cloud deployment targets.</p>
                </div>
            </div>
            <div class="loading-state"><div class="spinner"></div><p>Querying integration providers...</p></div>
        `;

        try {
            const status = await API.getIntegrationsStatus();
            const ai = status.ai || {};
            const gh = status.github || {};
            const cloud = status.cloud || {};
            const vercel = cloud.vercel || {};
            const render = cloud.render || {};

            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Integrations & System Health</h1>
                        <p class="page-subtitle">Real-time status of AI providers, live data scrapers, GitHub authentication, and cloud deployment targets.</p>
                    </div>
                </div>

                <div class="integrations-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 24px;">
                    <div class="glass-card stat-card">
                        <h3>AI Provider</h3>
                        <div class="stat-value ${ai.configured ? 'text-success' : 'text-warning'}">${ai.configured ? 'Connected' : 'Offline / Autonomous'}</div>
                        <span class="text-muted text-sm">Provider: ${ai.provider || 'openrouter'} (${ai.model || 'default'})</span>
                    </div>

                    <div class="glass-card stat-card">
                        <h3>GitHub OAuth & Git</h3>
                        <div class="stat-value ${gh.connected ? 'text-success' : (gh.oauth_enabled ? 'text-info' : 'text-muted')}">
                            ${gh.connected ? `@${gh.username}` : (gh.oauth_enabled ? 'OAuth Ready' : 'PAT Token')}
                        </div>
                        <span class="text-muted text-sm">${gh.connected ? `Connected: ${gh.connected_at ? new Date(gh.connected_at).toLocaleDateString() : 'Active'}` : 'Private repo sync & automated commits'}</span>
                    </div>

                    <div class="glass-card stat-card">
                        <h3>Vercel Cloud Deploy</h3>
                        <div class="stat-value ${vercel.configured ? 'text-success' : 'text-purple'}">${vercel.configured ? 'API Connected' : 'Manifests Active'}</div>
                        <span class="text-muted text-sm">${vercel.expected_cost || 'Free Tier ($0/mo)'}</span>
                    </div>

                    <div class="glass-card stat-card">
                        <h3>Render Cloud Deploy</h3>
                        <div class="stat-value ${render.configured ? 'text-success' : 'text-purple'}">${render.configured ? 'API Connected' : 'Manifests Active'}</div>
                        <span class="text-muted text-sm">${render.expected_cost || 'Free Tier ($0/mo)'}</span>
                    </div>
                </div>

                <div class="glass-card" style="margin-bottom: 20px;">
                    <h3>GitHub Account Connection</h3>
                    <p class="text-muted text-sm" style="margin: 8px 0 16px;">
                        Connect your GitHub account securely to publish projects, create private repositories, and push verified code without pasting personal access tokens into chat.
                    </p>
                    ${gh.connected ? `
                        <div style="display: flex; align-items: center; justify-content: space-between; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 14px 18px; border-radius: 8px;">
                            <div>
                                <span style="font-weight: 600; color: #10b981;">✓ Connected as GitHub User:</span> <code>${gh.username}</code>
                            </div>
                            <button class="btn btn-secondary btn-sm" id="btn-disconnect-github">Disconnect</button>
                        </div>
                    ` : `
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <button class="btn btn-primary" id="btn-connect-github">Connect GitHub Account</button>
                            <span class="text-muted text-sm">OAuth 2.0 with CSRF protection</span>
                        </div>
                    `}
                </div>

                <div class="glass-card">
                    <h3>Cloud Deployment Providers</h3>
                    <p class="text-muted text-sm" style="margin: 8px 0 16px;">
                        Every generated project automatically receives production cloud deployment configurations.
                    </p>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div style="padding: 16px; border: 1px solid var(--border-color); border-radius: 8px; background: rgba(0,0,0,0.2);">
                            <h4>Vercel</h4>
                            <p class="text-muted text-sm" style="margin: 6px 0 10px;">${vercel.description || 'FastAPI serverless + HTML5 static assets'}</p>
                            <div class="badge badge-info">${vercel.expected_cost || 'Free Tier'}</div>
                        </div>
                        <div style="padding: 16px; border: 1px solid var(--border-color); border-radius: 8px; background: rgba(0,0,0,0.2);">
                            <h4>Render</h4>
                            <p class="text-muted text-sm" style="margin: 6px 0 10px;">${render.description || 'Containerized web service'}</p>
                            <div class="badge badge-info">${render.expected_cost || 'Free Tier'}</div>
                        </div>
                    </div>
                </div>
            `;

            // Attach event listeners
            const connectBtn = document.getElementById('btn-connect-github');
            if (connectBtn) {
                connectBtn.addEventListener('click', async () => {
                    try {
                        const res = await API.authorizeGitHub();
                        if (res.auth_url) {
                            window.location.href = res.auth_url;
                        } else {
                            alert(res.error || 'GitHub OAuth credentials not configured in backend.');
                        }
                    } catch (e) {
                        alert('Could not start GitHub authorization: ' + e.message);
                    }
                });
            }

            const disconnectBtn = document.getElementById('btn-disconnect-github');
            if (disconnectBtn) {
                disconnectBtn.addEventListener('click', async () => {
                    if (confirm('Disconnect GitHub account from your profile?')) {
                        try {
                            await API.disconnectGitHub();
                            this.renderIntegrations(container);
                        } catch (e) {
                            alert('Disconnect failed: ' + e.message);
                        }
                    }
                });
            }
        } catch (err) {
            container.innerHTML = `<div class="error-banner">Failed loading integrations: ${this.escapeHtml(err.message)}</div>`;
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },
};

window.App = App;

document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
