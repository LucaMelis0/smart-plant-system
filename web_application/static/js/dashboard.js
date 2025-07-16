/**
 * LeaFi - Frontend Dashboard Controller
 *
 * This module implements the complete frontend logic for the LeaFi IoT plant monitoring
 * system dashboard. It handles real-time data visualization, user interactions,
 * plant status monitoring, and device control through REST API integration.
 */

class PlantDashboard {
    // Initialize the LeaFi Dashboard

    constructor() {
        // NFR5: Authentication and security
        this.token = localStorage.getItem('access_token');

        // FR5: Chart visualization for historical data
        this.chart = null;

        // NFR1: Update intervals for real-time monitoring
        this.refreshInterval = null;

        // FR1: Data tracking for sensor trend analysis
        this.previousData = {};
        this.activeAlerts = new Map();

        // NFR1: System performance configuration
        this.updateIntervals = {
            dashboard: 30000,    // FR6: 30-second dashboard refresh
            chartAnimation: 300  // UI animation duration
        };

        // NFR5: Redirect to login if not authenticated
        if (!this.token) {
            window.location.href = '/login';
            return;
        }

        this.init();
    }

    // Initialize the dashboard by binding events, loading initial data, and setting up intervals
    init() {
        this.bindEventHandlers();
        this.loadDashboard();
        this.startAutoRefresh();
        this.updateUserInfo();
        this.setConnectionStatus('connecting');
    }

    bindEventHandlers() {
        // FR6: Dashboard control buttons
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadDashboard());
        document.getElementById('settingsBtn').addEventListener('click', () => this.openSettings());
        document.getElementById('logoutBtn').addEventListener('click', () => this.logout());

        // FR8 and FR9: Plant watering controls
        document.getElementById('manualWaterBtn').addEventListener('click', () => this.manualWater());
        document.getElementById('autoToggleBtn').addEventListener('click', () => this.toggleAutoWatering());

        // FR5: Historical data time range selector
        document.getElementById('timeRange').addEventListener('change', (e) => {
            this.loadHistoricalData(parseInt(e.target.value));
        });

        // FR7: Settings modal controls
        document.querySelector('.close').addEventListener('click', () => this.closeSettings());
        document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());
        document.getElementById('cancelSettingsBtn').addEventListener('click', () => this.closeSettings());

        // Accessibility: Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeSettings();
            if (e.key === 'F5') {
                e.preventDefault();
                this.loadDashboard();
            }
        });

        // Close modal on background click
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target.id === 'settingsModal') this.closeSettings();
        });
    }

    // Update user information based on JWT token
    updateUserInfo() {
        try {
            const payload = JSON.parse(atob(this.token.split('.')[1]));
            const username = payload.sub || 'User';
            document.getElementById('userInfo').textContent = `Welcome, ${username}`;
        } catch (error) {
            console.warn('Failed to parse JWT token:', error);
            document.getElementById('userInfo').textContent = 'Welcome, User';
        }
    }

    /**
     * NFR2: Update connection status indicator
     * @param {string} status - Connection status: 'online', 'offline', 'connecting', 'error'
     */
    setConnectionStatus(status) {
        const statusDot = document.getElementById('connectionStatus');
        statusDot.className = `status-dot ${status}`;

        const statusText = {
            'online': 'Connected to LeaFi',
            'offline': 'Disconnected from server',
            'connecting': 'Connecting to LeaFi...',
            'error': 'Connection error - check network'
        };

        statusDot.title = statusText[status] || 'Unknown connection status';
    }

    /**
     * NFR5: Make authenticated API request with error handling
     * Implements secure communication protocol for all backend interactions.
     * @param {string} url - API endpoint URL
     * @param {Object} options - Fetch options
     * @returns {Promise<Response|null>} - API response or null if auth failure
     */
    async apiRequest(url, options = {}) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            // NFR5: Handle authentication expiration
            if (response.status === 401) {
                console.warn('Authentication expired, redirecting to login');
                this.logout();
                return null;
            }

            this.setConnectionStatus('online');
            return response;
        } catch (error) {
            console.error('API request failed:', error);
            this.setConnectionStatus('error');
            throw error;
        }
    }

    // FR6: Load complete dashboard data
    async loadDashboard() {
        try {
            this.setConnectionStatus('connecting');

            // Load all dashboard components in parallel for optimal performance
            await Promise.all([
                this.loadCurrentStatus(),           // FR1, FR2: Current sensor data and plant status
                this.loadHistoricalData(24),        // FR5: Historical trends
                this.loadWeather()                  // FR4: Weather integration
            ]);
            this.setConnectionStatus('online');
            console.log('Dashboard data loaded successfully');
        } catch (error) {
            console.error('Dashboard load failed:', error);
            this.setConnectionStatus('error');
            this.showAlert('Failed to load dashboard data - check connection', 'error');
        }
    }

    // FR4: Integrates weather forecast data to support sustainable watering practices
    async loadWeather() {
        try {
            const response = await this.apiRequest('/LeaFi/weather');
            if (!response?.ok) throw new Error('Weather API unavailable');

            const data = await response.json();
            this.updateWeatherCard(data);

        } catch (error) {
            console.warn('Weather data unavailable:', error);
            // Fallback weather display when API is not configured
            this.updateWeatherCard({
                location: "Weather unavailable",
                condition: "API not configured",
                rain_amount: "--",
                will_rain: false
            });
        }
    }

    /**
     * FR4: Update weather information display
     * @param {Object} data - Weather information object from API
     */
    updateWeatherCard(data) {
        document.getElementById('weatherLocation').textContent = data.location || "Unknown";
        document.getElementById('weatherCondition').textContent = `${data.condition}`;

        // FR4: Display rain forecast information for watering decisions
        const rainInfo = data.will_rain ?
            `${data.rain_amount}mm expected` :
            `${data.rain_amount}mm (no rain)`;
        document.getElementById('weatherRain').textContent = `Rain: ${rainInfo}`;
    }

    // FR2 & FR6: Load current plant status and sensor readings
    async loadCurrentStatus() {
        const response = await this.apiRequest('/LeaFi/current-status');
        if (!response?.ok) {
            throw new Error('Failed to fetch current plant status');
        }

        const data = await response.json();
        this.updateDashboard(data);
    }

    /**
     * Update all dashboard components with current data
     * Synchronizes the digital twin interface with the physical plant system state.
     * @param {Object} data - Current system status data from backend
     */
    updateDashboard(data) {
        this.updatePlantStatus(data);  // FR2: Plant health evaluation
        this.updateSensorData(data);   // FR1: Environmental sensor readings
        this.updateControls(data);     // FR8: Watering system controls
        this.checkAlerts(data);        // FR3: User notifications

        // FR8: Update pump status
        if (data.pump_status && typeof data.pump_status.status === 'string') {
            this.updatePumpStatus(data.pump_status.status === "on");
        }
    }

    /**
     * FR2: Update plant status display and recommendations
     * @param {Object} data - Plant status data from backend evaluation
     */
    updatePlantStatus(data) {
        const statusElement = document.getElementById('plantStatus');
        statusElement.textContent = data.status;
        statusElement.className = `plant-status ${this.getStatusClass(data.status)}`;

        // Update timestamp display for data freshness indication
        const lastUpdate = new Date(data.timestamp);
        document.getElementById('lastUpdate').textContent =
            `Last update: ${this.formatTime(lastUpdate)}`;

        this.updateRecommendations(data.recommendations);
    }

    /**
     * FR2: Display plant care recommendations
     * @param {Array} recommendations - List of care recommendations from backend
     */
    updateRecommendations(recommendations) {
        const container = document.getElementById('recommendations');

        if (!recommendations?.length) {
            container.innerHTML = '<p class="no-recommendations">All conditions are optimal</p>';
            return;
        }

        container.innerHTML = `
            <h4>Plant Care Recommendations:</h4>
            <ul>
                ${recommendations.map(rec => `<li>${rec}</li>`).join('')}
            </ul>
        `;
    }

    /**
     * FR1: Update sensor data display with trend analysis
     * @param {Object} data - Sensor readings data from NodeMCU
     */
    updateSensorData(data) {
        const sensors = [
            { id: 'temperature', value: data.temperature, decimals: 1, unit: '°C' },
            { id: 'humidity', value: data.humidity, decimals: 1, unit: '%' },
            { id: 'lightLevel', value: data.light_level, decimals: 0, unit: '%' }
        ];

        sensors.forEach(sensor => {
            const element = document.getElementById(sensor.id);
            const newValue = Number(sensor.value).toFixed(sensor.decimals);

            // Update display value with visual feedback
            element.textContent = newValue;
            this.updateTrend(sensor.id, parseFloat(newValue));

            // Provide visual feedback for data updates
            element.classList.add('updated');
            setTimeout(() => element.classList.remove('updated'), this.updateIntervals.chartAnimation);
        });
    }

    /**
     * FR1: Calculate and display sensor value trends
     * @param {string} sensorId - Sensor identifier
     * @param {number} currentValue - Current sensor value
     */
    updateTrend(sensorId, currentValue) {
        const trendMap = {
            'temperature': 'tempTrend',
            'humidity': 'humidityTrend',
            'lightLevel': 'lightTrend'
        };

        const trendElement = document.getElementById(trendMap[sensorId]);
        if (!trendElement) return;
        const previousValue = this.previousData[sensorId];

        if (previousValue === undefined) {
            trendElement.textContent = 'Initial reading';
            trendElement.className = 'trend';
        } else {
            const diff = currentValue - previousValue;
            const threshold = 0.1; // Minimum change to show trend

            if (Math.abs(diff) < threshold) {
                trendElement.textContent = 'Stable';
                trendElement.className = 'trend stable';
            } else if (diff > 0) {
                trendElement.textContent = `↗ +${diff.toFixed(1)}`;
                trendElement.className = 'trend up';
            } else {
                trendElement.textContent = `↘ ${diff.toFixed(1)}`;
                trendElement.className = 'trend down';
            }
        }
        this.previousData[sensorId] = currentValue;
    }

    /**
     * FR8 - FR9: Update watering system controls display. Shows current state of automatic and manual watering system.
     * @param {Object} data - System control data from backend
     */
    updateControls(data) {
        const autoBtn = document.getElementById('autoToggleBtn');
        const autoStatus = document.getElementById('autoStatus');
        const isEnabled = data.auto_watering_enabled;
        autoStatus.textContent = `Auto: ${isEnabled ? 'ON' : 'OFF'}`;
        autoBtn.className = `control-btn auto ${isEnabled ? 'active' : ''}`;
    }

    /**
     * FR8 - FR9: Update pump operation status display (real-time feedback on pump operations)
     * @param {boolean} isOn - Current pump operation state
     */
    updatePumpStatus(isOn) {
        const pumpStatus = document.getElementById('pumpStatus');
        const newStatus = isOn ? 'ON' : 'OFF';

        // Only update if status actually changed to prevent unnecessary DOM updates
        if (pumpStatus.textContent !== newStatus) {
            pumpStatus.textContent = newStatus;
            pumpStatus.className = `status ${isOn ? 'on' : 'off'}`;

            console.log(`Pump status updated: ${newStatus}`);

            // Visual feedback for status change
            pumpStatus.style.transition = 'color 0.3s ease';
            pumpStatus.style.fontWeight = 'bold';
            setTimeout(() => {
                pumpStatus.style.fontWeight = '';
            }, 1000);
        }
    }

    /**
     * FR3: Check plant conditions and display user notifications
     * @param {Object} data - Plant status data from backend evaluation
     */
    checkAlerts(data) {
        // Clear previous alerts and show current ones
        const alertMappings = {
            'Needs water': {
                key: 'needs-water',
                message: 'Plant needs watering urgently',
                type: 'warning'
            },
            'Change position': {
                key: 'change-position',
                message: 'Plant needs repositioning for better conditions',
                type: 'warning'
            },
            'No data': {
                key: 'no-data',
                message: 'No sensor data available - check connections',
                type: 'error'
            }
        };

        // Remove alerts that no longer apply
        Object.values(alertMappings).forEach(alert => {
            if (data.status !== Object.keys(alertMappings).find(status =>
                alertMappings[status].key === alert.key)) {
                this.removeAlert(alert.key);
            }
        });

        // Show current alert if applicable
        const currentAlert = alertMappings[data.status];
        if (currentAlert) {
            this.showAlert(currentAlert.message, currentAlert.type, currentAlert.key);
        }
    }

    /**
     * Remove specific alert from display
     * @param {string} alertKey - Alert identifier to remove
     */
    removeAlert(alertKey) {
        const alertId = this.activeAlerts.get(alertKey);
        if (alertId) {
            const alertElement = document.getElementById(alertId);
            if (alertElement) alertElement.remove();
            this.activeAlerts.delete(alertKey);
        }
    }

    /**
     * Map plant status to CSS class for visual styling
     * @param {string} status - Plant status string from backend
     * @returns {string} - CSS class name for styling
     */
    getStatusClass(status) {
        const statusMap = {
            'Healthy': 'healthy',
            'Needs water': 'needs-water',
            'Change position': 'needs-attention',
            'No data': 'no-data'
        };
        return statusMap[status] || 'unknown';
    }

    /**
     * FR5: Load and display historical sensor data
     * Retrieves historical environmental data for trend analysis and visualization.
     * @param {number} hours - Number of hours of historical data to load
     */
    async loadHistoricalData(hours = 24) {
        try {
            const response = await this.apiRequest(`/LeaFi/historical-data?hours=${hours}`);
            if (!response?.ok) {
                throw new Error('Failed to fetch historical data');
            }

            const data = await response.json();
            this.renderChart(data.data);

        } catch (error) {
            console.error('Historical data load failed:', error);
            this.showAlert('Failed to load chart data', 'error');
        }
    }

    /**
     * FR5 & FR6: Render environmental data chart
     * Creates interactive Chart.js visualization of sensor data trends for plant environmental analysis.
     * @param {Array} data - Historical sensor data array from backend
     */
    renderChart(data) {
        const ctx = document.getElementById('environmentChart').getContext('2d');
        // Destroy existing chart to prevent memory leaks
        if (this.chart) {
            this.chart.destroy();
        }

        // Handle empty data case
        if (!data.length) {
            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
            ctx.font = '16px Arial';
            ctx.fillStyle = '#666';
            ctx.textAlign = 'center';
            ctx.fillText('No historical data available',
                ctx.canvas.width / 2, ctx.canvas.height / 2);
            return;
        }

        // Prepare data labels for Chart.js
        const labels = data.map(item => {
            const date = new Date(item.timestamp);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        });

        // Create multi-axis chart for different measurement scales
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Temperature (°C)',
                        data: data.map(item => item.temperature),
                        borderColor: '#e74c3c',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)',
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 2,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Humidity (%)',
                        data: data.map(item => item.humidity),
                        borderColor: '#3498db',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 2,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Light (%)',
                        data: data.map(item => item.light_level),
                        borderColor: '#f39c12',
                        backgroundColor: 'rgba(243, 156, 18, 0.1)',
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 2,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { usePointStyle: true }
                    },
                    title: {
                        display: true,
                        text: 'Plant Environmental Conditions'
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Time' }
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        title: { display: true, text: 'Temperature (°C)' }
                    },
                    y1: {
                        type: 'linear',
                        position: 'right',
                        title: { display: true, text: 'Humidity & Light (%)' },
                        grid: { drawOnChartArea: false },
                        min: 0,
                        max: 100
                    }
                }
            }
        });
    }

    // FR8: Manual watering trigger with user feedback
    async manualWater() {
        const button = document.getElementById('manualWaterBtn');
        const originalText = button.innerHTML;

        try {
            // Provide immediate user feedback
            button.innerHTML = '<span>Watering...</span>';
            button.disabled = true;

            const response = await this.apiRequest('/LeaFi/manual-water', { method: 'POST' });
            if (!response?.ok) {
                throw new Error('Manual watering request failed');
            }

            this.showAlert('Manual watering initiated successfully', 'success');

            // Refresh status after watering command for immediate feedback
            setTimeout(() => {
                this.loadCurrentStatus().catch(console.error);
            }, 1000);

        } catch (error) {
            console.error('Manual watering failed:', error);
            this.showAlert('Failed to trigger watering - check connection', 'error');
        } finally {
            // Restore button after delay
            setTimeout(() => {
                button.innerHTML = originalText;
                button.disabled = false;
            }, 2000);
        }
    }

    // FR8: Toggle automatic watering system (enable or disable automatic watering).
    async toggleAutoWatering() {
        try {
            const response = await this.apiRequest('/LeaFi/toggle-auto-watering', { method: 'POST' });
            if (!response?.ok) {
                throw new Error('Failed to toggle auto watering');
            }

            const result = await response.json();
            const status = result.auto_watering_enabled ? 'enabled' : 'disabled';

            this.showAlert(`Auto watering ${status}`, 'success');
            this.loadCurrentStatus();

        } catch (error) {
            console.error('Auto watering toggle failed:', error);
            this.showAlert('Failed to toggle auto watering', 'error');
        }
    }

    // FR7: Open plant care settings modal
    async openSettings() {
        try {
            const response = await this.apiRequest('/LeaFi/settings');
            if (!response?.ok) {
                throw new Error('Failed to load current settings');
            }

            const settings = await response.json();
            this.populateSettingsForm(settings);
            this.showModal();

        } catch (error) {
            console.error('Settings load failed:', error);
            this.showAlert('Failed to load settings', 'error');
        }
    }

    /**
     * Populate settings form with current calibration values
     * @param {Object} settings - Current plant care settings from backend
     */
    populateSettingsForm(settings) {
        const fieldMap = {
            'minHumidity': 'min_humidity',
            'minTemp': 'min_temp',
            'maxTemp': 'max_temp',
            'minLight': 'min_light',
            'maxLight': 'max_light',
            'location': 'location'
        };

        Object.keys(fieldMap).forEach(fieldId => {
            const element = document.getElementById(fieldId);
            const value = settings[fieldMap[fieldId]];

            if (element && value !== undefined) {
                element.value = value;
            }
        });
    }

    // FR7: Save updated plant care settings
    async saveSettings() {
        try {
            const settings = this.getSettingsFromForm();
            this.validateSettings(settings);
            const response = await this.apiRequest('/LeaFi/settings', {
                method: 'POST',
                body: JSON.stringify(settings)
            });

            if (!response?.ok) {
                throw new Error('Failed to save settings to server');
            }
            this.showAlert('Settings saved successfully', 'success');
            this.closeSettings();

            // Refresh data with new settings
            this.loadCurrentStatus();
            this.loadWeather(); // Reload weather if location changed

        } catch (error) {
            console.error('Settings save failed:', error);
            this.showAlert(error.message || 'Failed to save settings', 'error');
        }
    }

    /**
     * Extract settings values from form inputs
     * @returns {Object} - Settings object formatted for API submission
     */
    getSettingsFromForm() {
        return {
            min_humidity: parseFloat(document.getElementById('minHumidity').value),
            max_temp: parseFloat(document.getElementById('maxTemp').value),
            min_temp: parseFloat(document.getElementById('minTemp').value),
            min_light: parseInt(document.getElementById('minLight').value),
            max_light: parseInt(document.getElementById('maxLight').value),
            location: document.getElementById('location').value.trim()
        };
    }

    /**
     * FR7: Validate settings input before submission
     * @param {Object} settings - Settings to validate
     * @throws {Error} - If validation fails with specific error message
     */
    validateSettings(settings) {
        if (settings.min_humidity < 0 || settings.min_humidity > 100) {
            throw new Error('Minimum humidity must be between 0-100%');
        }
        if (settings.min_temp >= settings.max_temp) {
            throw new Error('Minimum temperature must be less than maximum temperature');
        }
        if (settings.min_light < 0 || settings.min_light > 100) {
            throw new Error('Minimum light must be between 0-100%');
        }
        if (settings.max_light < 0 || settings.max_light > 100) {
            throw new Error('Maximum light must be between 0-100%');
        }
        if (settings.min_light >= settings.max_light) {
            throw new Error('Minimum light must be less than maximum light');
        }
        if (!settings.location) {
            throw new Error('Location is required for weather integration');
        }
    }

    // Show settings modal dialog
    showModal() {
        const modal = document.getElementById('settingsModal');
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }

    // Close settings modal dialog
    closeSettings() {
        const modal = document.getElementById('settingsModal');
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }

    // NFR5: User logout with cleanup
    logout() {
        localStorage.removeItem('access_token');
        this.destroy();
        window.location.href = '/login';
    }

    /**
     * FR3: Display user notification alert
     * @param {string} message - Alert message to display
     * @param {string} type - Alert type: 'success', 'error', 'warning', 'info'
     * @param {string} key - Unique alert key to prevent duplicates
     */
    showAlert(message, type = 'info', key = null) {
        const container = document.getElementById('alerts');
        const alertKey = key || message;

        // Prevent duplicate alerts
        if (this.activeAlerts.has(alertKey)) return;

        const alertId = `alert-${btoa(alertKey).replace(/[^a-z0-9]/gi, '')}`;
        const alert = document.createElement('div');
        alert.id = alertId;
        alert.className = `alert ${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button onclick="dashboard.removeAlert('${alertKey}')" 
                    style="float: right; background: none; border: none; 
                           font-size: 18px; cursor: pointer;">&times;</button>
        `;
        container.appendChild(alert);
        this.activeAlerts.set(alertKey, alertId);

        // Auto-remove success alerts after 5 seconds
        if (type === 'success') {
            setTimeout(() => this.removeAlert(alertKey), 5000);
        }
    }

    /**
     * Format timestamp for user display
     * @param {Date} date - Date object to format
     * @returns {string} - Human-readable time string
     */
    formatTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;

        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;

        return date.toLocaleDateString();
    }

    // NFR1: Start automatic dashboard refresh
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        this.refreshInterval = setInterval(() => {
            this.loadCurrentStatus().catch(error => {
                console.error('Auto-refresh failed:', error);
                this.setConnectionStatus('error');
            });
            // Also refresh weather data periodically
            this.loadWeather().catch(() => {
                console.warn('Weather refresh failed');
            });
        }, this.updateIntervals.dashboard);
    }

    // Cleanup dashboard resources on page unload
    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        if (this.chart) {
            this.chart.destroy();
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new PlantDashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.dashboard) {
        window.dashboard.destroy();
    }
});
