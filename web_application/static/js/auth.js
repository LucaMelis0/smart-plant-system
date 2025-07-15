/**
 * LeaFi - Authentication JS code
 * Handles user authentication, JWT token management, and secure login process
 */

class AuthManager {
     // Initialize the authentication system, sets up login form handling and validates existing authentication
    constructor() {
        this.init();
    }

    // Initialize authentication manager, check for existing valid sessions and sets up event handlers
    init() {
        this.checkExistingAuth();
        this.bindEvents();
    }

     // Check if user is already authenticated with valid token (redirects to dashboard if valid)
    async checkExistingAuth() {
        const token = localStorage.getItem('access_token');
        if (token && await this.isValidToken(token)) {
            window.location.href = '/';
        }
    }

    /**
     * Validate JWT token by checking with backend
     * @param {string} token - JWT access token to validate
     * @returns {boolean} - True if token is valid and not expired
     */
    async isValidToken(token) {
        try {
            const response = await fetch('/LeaFi/health', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            return response.ok;
        } catch {
            // Remove invalid token and return false
            localStorage.removeItem('access_token');
            return false;
        }
    }

    // Bind event handlers for login form and user interactions
    bindEvents() {
        const form = document.getElementById('loginForm');
        const inputs = form.querySelectorAll('input');

        // Handle form submission
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });

        // Clear messages on input to improve UX
        inputs.forEach(input => {
            input.addEventListener('input', () => this.hideMessage());
        });
    }

    // Handle user login process (validate credentials, send auth request, manage user session)
    async handleLogin() {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        // Basic client-side validation
        if (!username || !password) {
            this.showMessage('Please fill in all fields', 'error');
            return;
        }

        const button = document.getElementById('loginButton');
        button.disabled = true;

        try {
            // Send authentication request to backend
            const response = await fetch('/LeaFi/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok) {
                // Store JWT token and redirect to dashboard
                localStorage.setItem('access_token', data.access_token);
                this.showMessage('Login successful', 'success');
                setTimeout(() => window.location.href = '/', 1000);
            } else {
                // Handle authentication failure
                this.showMessage(data.detail || 'Invalid credentials', 'error');
                document.getElementById('username').focus();
            }
        } catch (error) {
            console.error('Login error:', error);
            this.showMessage('Connection error - please try again', 'error');
        } finally {
            button.disabled = false;
        }
    }

    /**
     * Display user feedback message
     * @param {string} text - Message text to display
     * @param {string} type - Message type: 'success', 'error', 'info'
     */
    showMessage(text, type) {
        const message = document.getElementById('message');
        message.textContent = text;
        message.className = `message ${type}`;
        message.style.display = 'block';

        // Auto-hide success messages
        if (type === 'success') {
            setTimeout(() => this.hideMessage(), 3000);
        }
    }

    // Hide user feedback message
    hideMessage() {
        document.getElementById('message').style.display = 'none';
    }
}

// Initialize authentication manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new AuthManager();
});