/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

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
        return `${current || 0}/${max || 0} ${unit}`;
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
 * Ice Loading Management Dashboard Component
 */
export class IceLoadingDashboard extends Component {
    setup() {
        this.isMounted = true;

        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            stats: {
                todayRequests: 0,
                urgentRequests: 0,
                readyForLoading: 0,
                delivering: 0,
                availableCars: 0,
                busyCars: 0,
                carChecking: 0,
                loading: 0,
                readyForSecondLoading: 0,
                startedSecondLoading: 0,
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
            this.state.refreshInterval = setInterval(() => {
                this.loadDashboardData();
            }, 30000);
        });

        onWillUnmount(() => {
            this.isMounted = false;
            if (this.state.refreshInterval) {
                clearInterval(this.state.refreshInterval);
            }
        });
    }

    async loadDashboardData() {
        try {
            if (!this.isMounted) return;
            this.state.loading = true;
            this.state.error = null;

            const [stats, recentRequests, statusDist, priorityDist] = await Promise.all([
                this.loadStatistics(),
                this.loadRecentRequests(),
                this.loadStatusDistribution(),
                this.loadPriorityDistribution()
            ]);

            if (!this.isMounted) return;

            Object.assign(this.state.stats, stats);
            this.state.recentRequests = recentRequests;
            this.state.statusDistribution = statusDist;
            this.state.priorityDistribution = priorityDist;

        } catch (error) {
            if (!this.isMounted) return;
            console.error("Error loading dashboard data:", error);
            this.state.error = error.message;
            this.notification.add("Failed to load dashboard data", {
                type: "danger"
            });
        } finally {
            if (!this.isMounted) return;
            this.state.loading = false;
        }
    }
    
    async loadStatistics() {
        const today = new Date().toISOString().split('T')[0];
        const [
            todayRequests, urgentRequests, readyForLoading, delivering,
            availableCars, busyCars, carChecking, loading,
            readyForSecondLoading, startedSecondLoading
        ] = await Promise.all([
            this.orm.searchCount("ice.loading.request", [['dispatch_time', '>=', today + ' 00:00:00'], ['dispatch_time', '<=', today + ' 23:59:59']]),
            this.orm.searchCount("ice.loading.request", [['priority', '=', 1], ['state', 'not in', ['cancelled', 'done']]]),
            this.orm.searchCount("ice.loading.request", [['state', '=', 'ready_for_loading']]),
            this.orm.searchCount("ice.loading.request", [['state', 'in', ['delivering', 'second_loading_delivering']]]),
            this.orm.searchCount("fleet.vehicle", [['loading_status', '=', 'available']]),
            this.orm.searchCount("fleet.vehicle", [['loading_status', 'in', ['in_use', 'ready_for_loading', 'plugged']]]),
            this.orm.searchCount("ice.loading.request", [['state', '=', 'car_checking']]),
            this.orm.searchCount("ice.loading.request", [['state', '=', 'loading']]),
            this.orm.searchCount("ice.loading.request", [['state', '=', 'ready_for_second_loading']]),
            this.orm.searchCount("ice.loading.request", [['state', '=', 'started_second_loading']])
        ]);

        return {
            todayRequests, urgentRequests, readyForLoading, delivering,
            availableCars, busyCars, carChecking, loading,
            readyForSecondLoading, startedSecondLoading
        };
    }

    async loadRecentRequests() {
        // Step 1: Fetch loading requests without the problematic field
        const requests = await this.orm.searchRead(
            "ice.loading.request", [],
            ["name", "car_id", "salesman_id", "state", "dispatch_time", "priority", "total_weight"],
            { order: "create_date desc", limit: 10 }
        );

        if (!requests.length) {
            return [];
        }

        // Step 2: Collect all unique car IDs that are not null
        const carIds = [...new Set(requests.map(req => req.car_id ? req.car_id[0] : null).filter(id => id))];

        // Step 3: If there are cars, fetch their capacities
        let carCapacities = {};
        if (carIds.length > 0) {
            const carData = await this.orm.read("fleet.vehicle", carIds, ["total_weight_capacity"]);
            // Create a map of car_id -> capacity
            carData.forEach(car => {
                carCapacities[car.id] = car.total_weight_capacity;
            });
        }

        // Step 4: Map the results, merging the capacity data
        return requests.map(request => {
            const carId = request.car_id ? request.car_id[0] : null;
            const carData = request.car_id ? {
                id: carId,
                name: request.car_id[1],
                total_weight_capacity: carCapacities[carId] || 0
            } : false;

            return {
                ...request,
                car_id: carData,
                dispatch_time_formatted: this.formatDateTime(request.dispatch_time),
                priority_class: this.getPriorityClass(request.priority),
                state_class: this.getStateClass(request.state),
                state: this.getStateLabel(request.state)
            };
        });
    }

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

    async loadPriorityDistribution() {
        const distribution = await this.orm.readGroup(
            "ice.loading.request",
            [['state', 'not in', ['cancelled', 'done']]],
            ['priority'],
            ['priority']
        );
        return distribution.map(item => ({
            priority: item.priority,
            count: item.priority_count,
            label: this.getPriorityLabel(item.priority),
            color: this.getPriorityColor(item.priority)
        }));
    }

    async openLoadingRequests(domain = []) {
        this.action.doAction({
            name: "Loading Requests",
            type: "ir.actions.act_window",
            res_model: "ice.loading.request",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain: domain,
            context: {}
        });
    }
    
    async openFleetVehicles(domain = []) {
        this.action.doAction({
            name: "Fleet Vehicles",
            type: "ir.actions.act_window",
            res_model: "fleet.vehicle",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            context: {}
        });
    }

    async onTodayRequestsClick() {
        const today = new Date().toISOString().split('T')[0];
        await this.openLoadingRequests([
            ['dispatch_time', '>=', today + ' 00:00:00'],
            ['dispatch_time', '<=', today + ' 23:59:59']
        ]);
    }

    async onUrgentRequestsClick() {
        await this.openLoadingRequests([['priority', '=', 1], ['state', 'not in', ['cancelled', 'done']]]);
    }

    async onReadyForLoadingClick() {
        await this.openLoadingRequests([['state', '=', 'ready_for_loading']]);
    }

    async onDeliveringClick() {
        await this.openLoadingRequests([['state', 'in', ['delivering', 'second_loading_delivering']]]);
    }
    
    async onCarCheckingClick() {
        await this.openLoadingRequests([['state', '=', 'car_checking']]);
    }

    async onLoadingClick() {
        await this.openLoadingRequests([['state', '=', 'loading']]);
    }

    async onReadyForSecondLoadingClick() {
        await this.openLoadingRequests([['state', '=', 'ready_for_second_loading']]);
    }

    async onStartedSecondLoadingClick() {
        await this.openLoadingRequests([['state', '=', 'started_second_loading']]);
    }

    async onAvailableCarsClick() {
        await this.openFleetVehicles([['loading_status', '=', 'available']]);
    }

    async onBusyCarsClick() {
        await this.openFleetVehicles([['loading_status', 'in', ['in_use', 'ready_for_loading', 'plugged']]]);
    }
    
    async refreshDashboard() {
        await this.loadDashboardData();
        this.notification.add("Dashboard refreshed", { type: "success" });
    }

    formatDateTime(datetime) {
        if (!datetime) return "";
        const date = new Date(datetime);
        return date.toLocaleDateString() + " " + date.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getPriorityClass(priority) {
        const classes = { 1: "o_priority_badge_1", 2: "o_priority_badge_2", 3: "o_priority_badge_3" };
        return classes[priority] || "";
    }

    getStateClass(state) {
        return `o_field_badge_${state}`;
    }

    getStateLabel(state) {
        const labels = {
            'draft': 'Draft', 'car_checking': 'Car Checking', 'ready_for_loading': 'Ready',
            'ice_handled': 'Ice Handled', 'plugged': 'Plugged', 'delivering': 'Delivering',
            'session_closed': 'Session Closed', 'delivered': 'Delivered',
            'done': 'Done', 'loading': 'Loading', 'ready_for_second_loading': 'Ready for 2nd',
            'started_second_loading': '2nd Loading', 'second_loading_delivering': '2nd Delivering'
        };
        return labels[state] || state;
    }

    getStateColor(state) {
        const colors = {
            'draft': '#6c757d', 'car_checking': '#ffc107', 'ready_for_loading': '#fd7e14',
            'ice_handled': '#e83e8c', 'plugged': '#28a745', 'delivering': '#007bff',
            'session_closed': '#343a40', 'delivered': '#343a40', 'done': '#198754',
            'loading': '#6610f2', 'ready_for_second_loading': '#17a2b8', 'started_second_loading': '#20c997',
            'second_loading_delivering': '#0d6efd'
        };
        return colors[state] || '#6c757d';
    }

    getPriorityLabel(priority) {
        const labels = { 1: 'Urgent', 2: 'High', 3: 'Normal' };
        return labels[priority] || `Priority ${priority}`;
    }

    getPriorityColor(priority) {
        const colors = { 1: '#dc3545', 2: '#fd7e14', 3: '#ffc107' };
        return colors[priority] || '#6c757d';
    }
}

IceLoadingDashboard.template = "loading_plans_management.Dashboard";
IceLoadingDashboard.components = { WeightProgressBar };
registry.category("actions").add("loading_plans_management.dashboard", IceLoadingDashboard);