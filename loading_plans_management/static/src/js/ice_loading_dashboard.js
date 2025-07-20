/** @odoo-module **/

import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Domain } from "@web/core/domain";

/**
 * Ice Loading Management Dashboard Component
 * Provides real-time statistics and quick actions for loading operations
 */
export class IceLoadingDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            stats: {
                totalRequests: 0,
                todayRequests: 0,
                urgentRequests: 0,
                readyForLoading: 0,
                inTransit: 0,
                availableCars: 0,
                busyCars: 0,
                totalWeight: 0,
                avgWeight: 0
            },
            recentRequests: [],
            statusDistribution: [],
            priorityDistribution: [],
            loading: true,
            error: null,
            refreshInterval: null
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });

        onMounted(() => {
            // Auto-refresh every 30 seconds
            this.state.refreshInterval = setInterval(() => {
                this.loadDashboardData();
            }, 30000);
        });
    }

    willUnmount() {
        if (this.state.refreshInterval) {
            clearInterval(this.state.refreshInterval);
        }
    }

    /**
     * Load all dashboard data
     */
    async loadDashboardData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const [stats, recentRequests, statusDist, priorityDist] = await Promise.all([
                this.loadStatistics(),
                this.loadRecentRequests(),
                this.loadStatusDistribution(),
                this.loadPriorityDistribution()
            ]);

            Object.assign(this.state.stats, stats);
            this.state.recentRequests = recentRequests;
            this.state.statusDistribution = statusDist;
            this.state.priorityDistribution = priorityDist;

        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.error = error.message;
            this.notification.add("Failed to load dashboard data", {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Load statistics data
     */
    async loadStatistics() {
        const today = new Date().toISOString().split('T')[0];
        
        const [
            totalRequests,
            todayRequests,
            urgentRequests,
            readyForLoading,
            inTransit,
            availableCars,
            busyCars,
            weightData
        ] = await Promise.all([
            // Total requests
            this.orm.searchCount("ice.loading.request", []),
            
            // Today's requests
            this.orm.searchCount("ice.loading.request", [
                ['dispatch_time', '>=', today + ' 00:00:00'],
                ['dispatch_time', '<=', today + ' 23:59:59']
            ]),
            
            // Urgent requests (priority 1)
            this.orm.searchCount("ice.loading.request", [
                ['loading_priority', '=', 1],
                ['state', 'not in', ['cancelled', 'done']]
            ]),
            
            // Ready for loading
            this.orm.searchCount("ice.loading.request", [
                ['state', '=', 'ready_for_loading']
            ]),
            
            // In transit
            this.orm.searchCount("ice.loading.request", [
                ['state', '=', 'in_transit']
            ]),
            
            // Available cars
            this.orm.searchCount("fleet.vehicle", [
                ['loading_status', '=', 'available']
            ]),
            
            // Busy cars
            this.orm.searchCount("fleet.vehicle", [
                ['loading_status', 'in', ['in_use', 'ready_for_loading', 'plugged']]
            ]),
            
            // Weight data
            this.orm.readGroup("ice.loading.request", [
                ['state', 'not in', ['cancelled']]
            ], ['total_weight:sum', 'total_weight:avg'], [])
        ]);

        return {
            totalRequests,
            todayRequests,
            urgentRequests,
            readyForLoading,
            inTransit,
            availableCars,
            busyCars,
            totalWeight: weightData.length > 0 ? weightData[0].total_weight : 0,
            avgWeight: weightData.length > 0 ? weightData[0].total_weight : 0
        };
    }

    /**
     * Load recent requests
     */
    async loadRecentRequests() {
        const requests = await this.orm.searchRead(
            "ice.loading.request",
            [],
            ["name", "car_id", "salesman_id", "state", "dispatch_time", "loading_priority", "total_weight"],
            {
                order: "create_date desc",
                limit: 10
            }
        );

        return requests.map(request => ({
            ...request,
            dispatch_time_formatted: this.formatDateTime(request.dispatch_time),
            priority_class: this.getPriorityClass(request.loading_priority),
            state_class: this.getStateClass(request.state)
        }));
    }

    /**
     * Load status distribution
     */
    async loadStatusDistribution() {
        const distribution = await this.orm.readGroup(
            "ice.loading.request",
            [['state', 'not in', ['cancelled']]],
            ['state'],
            ['state']
        );

        return distribution.map(item => ({
            state: item.state,
            count: item.state_count,
            label: this.getStateLabel(item.state),
            color: this.getStateColor(item.state)
        }));
    }

    /**
     * Load priority distribution
     */
    async loadPriorityDistribution() {
        const distribution = await this.orm.readGroup(
            "ice.loading.request",
            [['state', 'not in', ['cancelled', 'done']]],
            ['loading_priority'],
            ['loading_priority']
        );

        return distribution.map(item => ({
            priority: item.loading_priority,
            count: item.loading_priority_count,
            label: this.getPriorityLabel(item.loading_priority),
            color: this.getPriorityColor(item.loading_priority)
        }));
    }

    /**
     * Open loading requests with domain
     */
    async openLoadingRequests(domain = []) {
        this.action.doAction({
            name: "Loading Requests",
            type: "ir.actions.act_window",
            res_model: "ice.loading.request",
            view_mode: "kanban,tree,form",
            domain: domain,
            context: {}
        });
    }

    /**
     * Open fleet vehicles
     */
    async openFleetVehicles(domain = []) {
        this.action.doAction({
            name: "Fleet Vehicles",
            type: "ir.actions.act_window",
            res_model: "fleet.vehicle",
            view_mode: "tree,form",
            domain: domain,
            context: {}
        });
    }

    /**
     * Quick action handlers
     */
    async onTodayRequestsClick() {
        const today = new Date().toISOString().split('T')[0];
        await this.openLoadingRequests([
            ['dispatch_time', '>=', today + ' 00:00:00'],
            ['dispatch_time', '<=', today + ' 23:59:59']
        ]);
    }

    async onUrgentRequestsClick() {
        await this.openLoadingRequests([
            ['loading_priority', '=', 1],
            ['state', 'not in', ['cancelled', 'done']]
        ]);
    }

    async onReadyForLoadingClick() {
        await this.openLoadingRequests([
            ['state', '=', 'ready_for_loading']
        ]);
    }

    async onInTransitClick() {
        await this.openLoadingRequests([
            ['state', '=', 'in_transit']
        ]);
    }

    async onAvailableCarsClick() {
        await this.openFleetVehicles([
            ['loading_status', '=', 'available']
        ]);
    }

    async onBusyCarsClick() {
        await this.openFleetVehicles([
            ['loading_status', 'in', ['in_use', 'ready_for_loading', 'plugged']]
        ]);
    }

    /**
     * Refresh dashboard data
     */
    async refreshDashboard() {
        await this.loadDashboardData();
        this.notification.add("Dashboard refreshed", {
            type: "success"
        });
    }

    /**
     * Utility functions
     */
    formatDateTime(datetime) {
        if (!datetime) return "";
        const date = new Date(datetime);
        return date.toLocaleDateString() + " " + date.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getPriorityClass(priority) {
        const classes = {
            1: "o_priority_badge_1",
            2: "o_priority_badge_2", 
            3: "o_priority_badge_3"
        };
        return classes[priority] || "";
    }

    getStateClass(state) {
        return `o_field_badge_${state}`;
    }

    getStateLabel(state) {
        const labels = {
            'draft': 'Draft',
            // 'confirmed': 'Confirmed',
            'car_checking': 'Car Checking',
            'ready_for_loading': 'Ready for Loading',
            // 'loaded': 'Loaded',
            // 'freezer_loaded': 'Freezer Loaded',
            // 'freezer_handled': 'Freezer Handled',
            'ice_handled': 'Ice Handled',
            'plugged': 'Plugged',
            'in_transit': 'In Transit',
            'delivered': 'Delivered',
            'done': 'Done'
        };
        return labels[state] || state;
    }

    getStateColor(state) {
        const colors = {
            'draft': '#6c757d',
            // 'confirmed': '#17a2b8',
            'car_checking': '#ffc107',
            'ready_for_loading': '#fd7e14',
            // 'loaded': '#20c997',
            // 'freezer_loaded': '#007bff',
            // 'freezer_handled': '#6f42c1',
            'ice_handled': '#e83e8c',
            'plugged': '#28a745',
            'in_transit': '#dc3545',
            'delivered': '#343a40',
            'done': '#198754'
        };
        return colors[state] || '#6c757d';
    }

    getPriorityLabel(priority) {
        const labels = {
            1: 'Urgent',
            2: 'High',
            3: 'Normal'
        };
        return labels[priority] || `Priority ${priority}`;
    }

    getPriorityColor(priority) {
        const colors = {
            1: '#dc3545',
            2: '#fd7e14',
            3: '#ffc107'
        };
        return colors[priority] || '#6c757d';
    }

    /**
     * Calculate weight percentage
     */
    getWeightPercentage(current, max) {
        if (!max || max === 0) return 0;
        return Math.min((current / max) * 100, 100);
    }

    /**
     * Get weight status class
     */
    getWeightStatusClass(percentage) {
        if (percentage >= 90) return 'o_weight_progress_danger';
        if (percentage >= 75) return 'o_weight_progress_warning';
        return 'o_weight_progress_safe';
    }
}

// Template for the dashboard component
IceLoadingDashboard.template = "loading_plans_management.Dashboard";

// Register the dashboard component
registry.category("actions").add("loading_plans_management.dashboard", IceLoadingDashboard);

/**
 * Weight Progress Bar Component
 */
export class WeightProgressBar extends Component {
    get progressPercentage() {
        const { current, max } = this.props;
        if (!max || max === 0) return 0;
        return Math.min((current / max) * 100, 100);
    }

    get progressClass() {
        const percentage = this.progressPercentage;
        if (percentage >= 90) return 'o_weight_progress_danger';
        if (percentage >= 75) return 'o_weight_progress_warning';
        return 'o_weight_progress_safe';
    }

    get progressText() {
        const { current, max, unit = 'kg' } = this.props;
        return `${current}/${max} ${unit}`;
    }
}

WeightProgressBar.template = "loading_plans_management.WeightProgressBar";
WeightProgressBar.props = {
    current: Number,
    max: Number,
    unit: { type: String, optional: true }
};

registry.category("components").add("WeightProgressBar", WeightProgressBar);

/**
 * Real-time updates using bus service
 */
export class IceLoadingRealTimeService {
    constructor(env) {
        this.env = env;
        this.busService = env.services.bus_service;
        this.callbacks = new Set();
        
        // Subscribe to loading request updates
        this.busService.subscribe("ice_loading_request_update", this.onLoadingRequestUpdate.bind(this));
        this.busService.subscribe("fleet_vehicle_status_update", this.onFleetStatusUpdate.bind(this));
    }

    onLoadingRequestUpdate(message) {
        // Notify all registered callbacks
        this.callbacks.forEach(callback => {
            try {
                callback("loading_request", message);
            } catch (error) {
                console.error("Error in real-time callback:", error);
            }
        });
    }

    onFleetStatusUpdate(message) {
        this.callbacks.forEach(callback => {
            try {
                callback("fleet_vehicle", message);
            } catch (error) {
                console.error("Error in real-time callback:", error);
            }
        });
    }

    subscribe(callback) {
        this.callbacks.add(callback);
        return () => this.callbacks.delete(callback);
    }
}

registry.category("services").add("ice_loading_realtime", {
    dependencies: ["bus_service"],
    start(env) {
        return new IceLoadingRealTimeService(env);
    }
});

/**
 * Dashboard initialization and auto-refresh
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips for dashboard elements
    const tooltipElements = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipElements.forEach(element => {
        new bootstrap.Tooltip(element);
    });

    // Initialize weight progress bars
    const weightBars = document.querySelectorAll('.o_weight_progress_container');
    weightBars.forEach(container => {
        const current = parseFloat(container.dataset.current || 0);
        const max = parseFloat(container.dataset.max || 1);
        const percentage = Math.min((current / max) * 100, 100);
        
        const progressBar = container.querySelector('.o_weight_progress_bar');
        if (progressBar) {
            progressBar.style.width = percentage + '%';
            
            // Add appropriate class based on percentage
            if (percentage >= 90) {
                progressBar.classList.add('o_weight_progress_danger');
            } else if (percentage >= 75) {
                progressBar.classList.add('o_weight_progress_warning');
            } else {
                progressBar.classList.add('o_weight_progress_safe');
            }
        }
    });

    // Add click handlers for dashboard tiles
    const dashboardTiles = document.querySelectorAll('.o_ice_loading_dashboard_tile[data-action]');
    dashboardTiles.forEach(tile => {
        tile.addEventListener('click', function() {
            const action = this.dataset.action;
            const domain = this.dataset.domain ? JSON.parse(this.dataset.domain) : [];
            
            // Trigger Odoo action
            if (window.odoo && window.odoo.define) {
                window.odoo.define('ice_loading_dashboard_action', function(require) {
                    const core = require('web.core');
                    const ActionManager = require('web.ActionManager');
                    
                    const actionManager = new ActionManager();
                    actionManager.doAction({
                        name: action,
                        type: 'ir.actions.act_window',
                        res_model: 'ice.loading.request',
                        view_mode: 'kanban,tree,form',
                        domain: domain,
                        context: {}
                    });
                });
            }
        });
    });

    // Auto-refresh dashboard every 30 seconds
    setInterval(function() {
        const dashboardElement = document.querySelector('.o_ice_loading_dashboard');
        if (dashboardElement && document.hasFocus()) {
            // Only refresh if the page is active and dashboard is visible
            location.reload();
        }
    }, 30000);
});

/**
 * Utility functions for dashboard
 */
window.IceLoadingUtils = {
    /**
     * Format weight with appropriate units
     */
    formatWeight: function(weight) {
        if (weight >= 1000) {
            return (weight / 1000).toFixed(1) + ' T';
        }
        return weight.toFixed(1) + ' kg';
    },

    /**
     * Format date for display
     */
    formatDate: function(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        const now = new Date();
        const diffTime = Math.abs(now - date);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays === 1) return 'Today';
        if (diffDays === 2) return 'Yesterday';
        if (diffDays <= 7) return diffDays + ' days ago';
        
        return date.toLocaleDateString();
    },

    /**
     * Get priority icon
     */
    getPriorityIcon: function(priority) {
        const icons = {
            1: '🔴', // Urgent
            2: '🟠', // High  
            3: '🟡', // Normal
            4: '🟢', // Low
            5: '⚪'  // Very Low
        };
        return icons[priority] || '⚪';
    },

    /**
     * Get status icon
     */
    getStatusIcon: function(state) {
        const icons = {
            'draft': '📝',
            // 'confirmed': '✅',
            'car_checking': '🔧',
            'ready_for_loading': '📦',
            // 'loaded': '🚛',
            // 'freezer_loaded': '❄️',
            // 'freezer_handled': '📋',
            'ice_handled': '❄️🚛',
            'plugged': '🔌',
            'in_transit': '🚚',
            'delivered': '✅',
            'done': '🏁',
            'cancelled': '❌'
        };
        return icons[state] || '❓';
    },

    /**
     * Calculate loading efficiency
     */
    calculateEfficiency: function(currentWeight, maxWeight) {
        if (!maxWeight || maxWeight === 0) return 0;
        return Math.round((currentWeight / maxWeight) * 100);
    },

    /**
     * Get efficiency status
     */
    getEfficiencyStatus: function(efficiency) {
        if (efficiency >= 90) return { status: 'excellent', color: '#28a745', text: 'Excellent' };
        if (efficiency >= 75) return { status: 'good', color: '#20c997', text: 'Good' };
        if (efficiency >= 50) return { status: 'fair', color: '#ffc107', text: 'Fair' };
        return { status: 'poor', color: '#dc3545', text: 'Poor' };
    },

    /**
     * Show notification
     */
    showNotification: function(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    },

    /**
     * Animate number counter
     */
    animateCounter: function(element, targetValue, duration = 1000) {
        const startValue = 0;
        const increment = targetValue / (duration / 16); // 60 FPS
        let currentValue = startValue;
        
        const timer = setInterval(() => {
            currentValue += increment;
            element.textContent = Math.floor(currentValue);
            
            if (currentValue >= targetValue) {
                element.textContent = targetValue;
                clearInterval(timer);
            }
        }, 16);
    },

    /**
     * Update progress bar
     */
    updateProgressBar: function(element, percentage) {
        const progressBar = element.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.style.width = percentage + '%';
            progressBar.setAttribute('aria-valuenow', percentage);
            
            // Update color based on percentage
            progressBar.className = 'progress-bar';
            if (percentage >= 90) {
                progressBar.classList.add('bg-danger');
            } else if (percentage >= 75) {
                progressBar.classList.add('bg-warning');
            } else {
                progressBar.classList.add('bg-success');
            }
        }
    }
};

/**
 * Real-time dashboard updates using WebSocket or polling
 */
class IceLoadingRealtimeUpdater {
    constructor() {
        this.updateInterval = null;
        this.isActive = true;
        this.lastUpdate = Date.now();
    }

    start() {
        // Start polling for updates every 10 seconds
        this.updateInterval = setInterval(() => {
            if (this.isActive && document.hasFocus()) {
                this.checkForUpdates();
            }
        }, 10000);

        // Listen for visibility changes
        document.addEventListener('visibilitychange', () => {
            this.isActive = !document.hidden;
        });
    }

    stop() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    async checkForUpdates() {
        try {
            // Check if any loading requests have been updated since last check
            const response = await fetch('/ice_loading/api/updates', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    last_update: this.lastUpdate
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.has_updates) {
                    this.handleUpdates(data.updates);
                    this.lastUpdate = Date.now();
                }
            }
        } catch (error) {
            console.error('Error checking for updates:', error);
        }
    }

    handleUpdates(updates) {
        updates.forEach(update => {
            switch (update.type) {
                case 'loading_request_state_change':
                    this.updateRequestStatus(update.data);
                    break;
                case 'car_status_change':
                    this.updateCarStatus(update.data);
                    break;
                case 'new_urgent_request':
                    this.showUrgentNotification(update.data);
                    break;
                case 'stats_update':
                    this.updateDashboardStats(update.data);
                    break;
            }
        });
    }

    updateRequestStatus(data) {
        const statusElement = document.querySelector(`[data-request-id="${data.request_id}"] .status-badge`);
        if (statusElement) {
            statusElement.textContent = data.new_status;
            statusElement.className = `status-badge badge ${this.getStatusClass(data.new_status)}`;
        }
    }

    updateCarStatus(data) {
        const carElement = document.querySelector(`[data-car-id="${data.car_id}"] .car-status`);
        if (carElement) {
            carElement.textContent = data.new_status;
            carElement.className = `car-status badge ${this.getCarStatusClass(data.new_status)}`;
        }
    }

    showUrgentNotification(data) {
        window.IceLoadingUtils.showNotification(
            `🚨 Urgent loading request created: ${data.request_name}`,
            'danger'
        );
    }

    updateDashboardStats(data) {
        Object.keys(data).forEach(statKey => {
            const element = document.querySelector(`[data-stat="${statKey}"]`);
            if (element) {
                window.IceLoadingUtils.animateCounter(element, data[statKey]);
            }
        });
    }

    getStatusClass(status) {
        const classes = {
            'draft': 'bg-secondary',
            // 'confirmed': 'bg-info',
            'car_checking': 'bg-warning',
            'ready_for_loading': 'bg-primary',
            // 'loaded': 'bg-success',
            // 'freezer_loaded': 'bg-info',
            // 'freezer_handled': 'bg-primary',
            'ice_handled': 'bg-success',
            'plugged': 'bg-success',
            'in_transit': 'bg-danger',
            'delivered': 'bg-dark',
            'done': 'bg-success',
            'cancelled': 'bg-secondary'
        };
        return classes[status] || 'bg-secondary';
    }

    getCarStatusClass(status) {
        const classes = {
            'available': 'bg-success',
            'in_use': 'bg-warning',
            'not_available': 'bg-secondary',
            'ready_for_loading': 'bg-info',
            'plugged': 'bg-primary'
        };
        return classes[status] || 'bg-secondary';
    }
}

// Initialize real-time updater when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const realtimeUpdater = new IceLoadingRealtimeUpdater();
    realtimeUpdater.start();
    
    // Stop updater when page is unloaded
    window.addEventListener('beforeunload', function() {
        realtimeUpdater.stop();
    });
});

/**
 * Export utilities for use in other modules
 */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        IceLoadingDashboard,
        WeightProgressBar,
        IceLoadingRealtimeService,
        IceLoadingRealtimeUpdater,
        IceLoadingUtils: window.IceLoadingUtils
    };
}