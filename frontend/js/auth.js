/**
 * Problem2Project AI — Auth Manager
 * Manages user sessions, authentication modal, and operating modes.
 */

const Auth = {
    currentUser: null,

    async init() {
        this.setupEventListeners();
        return await this.checkExistingSession();
    },

    setupEventListeners() {
        // Tab switching (Sign In vs Create Account)
        const tabs = document.querySelectorAll('.auth-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const target = e.target.dataset.tab;
                this.switchTab(target);
            });
        });

        // Login form submit
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleLogin();
            });
        }

        // Register form submit
        const regForm = document.getElementById('register-form');
        if (regForm) {
            regForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleRegister();
            });
        }

        // Logout button
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                this.logout();
            });
        }

        // Operating mode buttons
        const modeButtons = document.querySelectorAll('.mode-btn');
        modeButtons.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const mode = e.currentTarget.dataset.mode;
                await this.setOperatingMode(mode);
            });
        });

        // Listen for session expiration
        window.addEventListener('auth:expired', () => {
            this.showModal('login');
            this.showError('Session expired. Please log in again.');
        });
    },

    switchTab(tab) {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.auth-tab[data-tab="${tab}"]`);
        if (activeTab) activeTab.classList.add('active');

        const loginForm = document.getElementById('login-form');
        const regForm = document.getElementById('register-form');
        const authError = document.getElementById('auth-error');
        if (authError) authError.classList.add('hidden');

        if (tab === 'login') {
            loginForm.classList.remove('hidden');
            regForm.classList.add('hidden');
        } else {
            loginForm.classList.add('hidden');
            regForm.classList.remove('hidden');
        }
    },

    showModal(tab = 'login') {
        const modal = document.getElementById('auth-modal');
        if (modal) {
            modal.classList.remove('hidden');
            this.switchTab(tab);
        }
    },

    hideModal() {
        const modal = document.getElementById('auth-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    },

    showError(message) {
        const errEl = document.getElementById('auth-error');
        if (errEl) {
            errEl.textContent = message;
            errEl.classList.remove('hidden');
        }
    },

    clearError() {
        const errEl = document.getElementById('auth-error');
        if (errEl) {
            errEl.textContent = '';
            errEl.classList.add('hidden');
        }
    },

    async checkExistingSession() {
        const token = API.getToken();
        if (!token) {
            // Auto login default developer account for zero-friction access
            try {
                const res = await API.login("developer@problempilot.ai", "ProblemPilot123!");
                this.currentUser = res.user;
                this.updateUserUI(res.user);
                this.hideModal();
                window.dispatchEvent(new CustomEvent('auth:ready', { detail: res.user }));
                return;
            } catch (err) {
                this.showModal('login');
                return;
            }
        }

        try {
            const user = await API.getMe();
            this.currentUser = user;
            API.setUser(user);
            this.updateUserUI(user);
            this.hideModal();
            window.dispatchEvent(new CustomEvent('auth:ready', { detail: user }));
        } catch (err) {
            console.warn('Existing session invalid:', err);
            try {
                const res = await API.login("developer@problempilot.ai", "ProblemPilot123!");
                this.currentUser = res.user;
                this.updateUserUI(res.user);
                this.hideModal();
                window.dispatchEvent(new CustomEvent('auth:ready', { detail: res.user }));
            } catch {
                this.showModal('login');
            }
        }
    },

    async handleLogin() {
        this.clearError();
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const btn = document.getElementById('login-submit');

        if (!email || !password) {
            this.showError('Please fill in both email and password.');
            return;
        }

        this.setLoading(btn, true);
        try {
            const res = await API.login(email, password);
            this.currentUser = res.user;
            this.updateUserUI(res.user);
            this.hideModal();
            if (window.App) {
                App.showToast(`Welcome back, ${res.user.name || res.user.username}!`, 'success');
                App.refreshCurrentPage();
            }
        } catch (err) {
            this.showError(err.message || 'Login failed. Please check your credentials.');
        } finally {
            this.setLoading(btn, false);
        }
    },

    async handleRegister() {
        this.clearError();
        const name = document.getElementById('reg-name').value.trim();
        const username = document.getElementById('reg-username').value.trim();
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const btn = document.getElementById('register-submit');

        if (!username || !email || !password) {
            this.showError('Username, email, and password are required.');
            return;
        }

        this.setLoading(btn, true);
        try {
            const res = await API.register(name, username, email, password);
            this.currentUser = res.user;
            this.updateUserUI(res.user);
            this.hideModal();
            if (window.App) {
                App.showToast('Account created successfully!', 'success');
                App.refreshCurrentPage();
            }
        } catch (err) {
            this.showError(err.message || 'Registration failed.');
        } finally {
            this.setLoading(btn, false);
        }
    },

    logout() {
        API.setToken(null);
        API.setUser(null);
        this.currentUser = null;
        const userInfo = document.getElementById('user-info');
        if (userInfo) userInfo.classList.add('hidden');
        this.showModal('login');
        if (window.App) {
            App.showToast('Signed out', 'info');
        }
    },

    async setOperatingMode(mode) {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        const activeBtn = document.querySelector(`.mode-btn[data-mode="${mode}"]`);
        if (activeBtn) activeBtn.classList.add('active');

        const modeDisplay = document.getElementById('user-mode');
        if (modeDisplay) {
            modeDisplay.textContent = `${mode.charAt(0).toUpperCase() + mode.slice(1)} Mode`;
        }

        try {
            if (this.currentUser) {
                await API.updateSettings({ operating_mode: mode });
                this.currentUser.operating_mode = mode;
                API.setUser(this.currentUser);
                if (window.App) {
                    App.showToast(`Operating mode set to ${mode.toUpperCase()}`, 'info');
                }
            }
        } catch (err) {
            console.error('Failed to update mode:', err);
        }
    },

    updateUserUI(user) {
        const userInfo = document.getElementById('user-info');
        const userAvatar = document.getElementById('user-avatar');
        const userName = document.getElementById('user-name');
        const userMode = document.getElementById('user-mode');

        if (userInfo && user) {
            userInfo.classList.remove('hidden');
            const initial = (user.name || user.username || 'U').charAt(0).toUpperCase();
            if (userAvatar) userAvatar.textContent = initial;
            if (userName) userName.textContent = user.name || user.username;
            
            const mode = user.operating_mode || 'hybrid';
            if (userMode) userMode.textContent = `${mode.charAt(0).toUpperCase() + mode.slice(1)} Mode`;

            // Update mode button active state
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            const activeBtn = document.querySelector(`.mode-btn[data-mode="${mode}"]`);
            if (activeBtn) activeBtn.classList.add('active');
        }
    },

    setLoading(btn, isLoading) {
        if (!btn) return;
        const textSpan = btn.querySelector('span');
        const loader = btn.querySelector('.btn-loader');
        if (isLoading) {
            btn.disabled = true;
            if (textSpan) textSpan.classList.add('opacity-0');
            if (loader) loader.classList.remove('hidden');
        } else {
            btn.disabled = false;
            if (textSpan) textSpan.classList.remove('opacity-0');
            if (loader) loader.classList.add('hidden');
        }
    }
};

window.Auth = Auth;
