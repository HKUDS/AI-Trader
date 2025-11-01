// Config Loader Utility
// Loads and manages the YAML configuration file

class ConfigLoader {
    constructor() {
        this.config = null;
        this.configPath = './config.yaml';
    }

    // Load the YAML configuration file
    async loadConfig() {
        if (this.config) {
            return this.config;
        }

        try {
            console.log('Loading configuration from:', this.configPath);
            const response = await fetch(this.configPath);
            if (!response.ok) {
                throw new Error(`Failed to load config: ${response.status}`);
            }

            const yamlText = await response.text();
            this.config = jsyaml.load(yamlText);
            console.log('Configuration loaded successfully:', this.config);
            return this.config;
        } catch (error) {
            console.error('Error loading configuration:', error);
            throw error;
        }
    }

    // Get all enabled agents
    getEnabledAgents() {
        if (!this.config || !this.config.agents) {
            return [];
        }
        return this.config.agents.filter(agent => agent.enabled);
    }

    // Get all agent folders (enabled only)
    getAgentFolders() {
        return this.getEnabledAgents().map(agent => agent.folder);
    }

    // Get agent configuration by folder name
    getAgentConfig(folderName) {
        if (!this.config || !this.config.agents) {
            return null;
        }
        return this.config.agents.find(agent => agent.folder === folderName);
    }

    // Get display name for agent
    getDisplayName(folderName) {
        const agent = this.getAgentConfig(folderName);
        return agent ? agent.display_name : folderName;
    }

    // Get icon path for agent
    getIcon(folderName) {
        const agent = this.getAgentConfig(folderName);
        return agent ? agent.icon : './figs/stock.svg';
    }

    // Get color for agent
    getColor(folderName) {
        const agent = this.getAgentConfig(folderName);
        return agent ? agent.color : null;
    }

    // Get benchmark configuration
    getBenchmarkConfig() {
        if (!this.config || !this.config.benchmark) {
            return null;
        }
        return this.config.benchmark;
    }

    // Get data path configuration
    getDataPath() {
        if (!this.config || !this.config.data) {
            return './data';
        }
        return this.config.data.base_path;
    }

    // Get price file prefix
    getPriceFilePrefix() {
        if (!this.config || !this.config.data) {
            return 'daily_prices_';
        }
        return this.config.data.price_file_prefix;
    }

    // Get benchmark file name
    getBenchmarkFile() {
        if (!this.config || !this.config.data) {
            return 'Adaily_prices_QQQ.json';
        }
        return this.config.data.benchmark_file;
    }

    // Get chart configuration
    getChartConfig() {
        if (!this.config || !this.config.chart) {
            return {
                default_scale: 'linear',
                max_ticks: 15,
                point_radius: 0,
                point_hover_radius: 7,
                border_width: 3,
                tension: 0.42
            };
        }
        return this.config.chart;
    }

    // Get UI configuration
    getUIConfig() {
        if (!this.config || !this.config.ui) {
            return {
                initial_value: 10000,
                max_recent_trades: 20,
                date_formats: {
                    hourly: 'MM/DD HH:mm',
                    daily: 'YYYY-MM-DD'
                }
            };
        }
        return this.config.ui;
    }

    // Check if an agent is enabled
    isAgentEnabled(folderName) {
        const agent = this.getAgentConfig(folderName);
        return agent ? agent.enabled : false;
    }

    // Get all agents (including disabled ones)
    getAllAgents() {
        if (!this.config || !this.config.agents) {
            return [];
        }
        return this.config.agents;
    }
}

// Create a global instance
window.configLoader = new ConfigLoader();
