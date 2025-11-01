// Data Loader Utility
// Handles loading and processing all trading data

class DataLoader {
    constructor() {
        this.agentData = {};
        this.priceCache = {};
        this.config = null;
        this.baseDataPath = './data';
        this.currentMarket = 'us'; // 'us' or 'cn'
    }
    
    // Switch market between US stocks and A-shares
    setMarket(market) {
        this.currentMarket = market;
        this.agentData = {};
        this.priceCache = {};
    }
    
    // Get current market
    getMarket() {
        return this.currentMarket;
    }

    // Initialize with configuration
    async initialize() {
        if (!this.config) {
            this.config = await window.configLoader.loadConfig();
            this.baseDataPath = window.configLoader.getDataPath();
        }
    }

    // Load all agent names from configuration
    async loadAgentList() {
        // Ensure config is loaded
        await this.initialize();

            const agentDataDir = this.currentMarket === 'us' ? 'agent_data' : 'agent_data_astock';
            const agents = [];

            for (const agentConfig of enabledAgents) {
                try {
                    console.log(`Checking agent: ${agent} in ${agentDataDir}`);
                    const response = await fetch(`${this.baseDataPath}/${agentDataDir}/${agent}/position/position.jsonl`);
                    if (response.ok) {
                        agents.push(agentConfig.folder);
                        console.log(`Added agent: ${agentConfig.folder}`);
                    } else {
                        console.log(`Agent ${agentConfig.folder} not found (status: ${response.status})`);
                    }
                } catch (e) {
                    console.log(`Agent ${agentConfig.folder} error:`, e.message);
                }
            }

            return agents;
        } catch (error) {
            console.error('Error loading agent list:', error);
            return [];
        }
    }

    // Load position data for a specific agent
    async loadAgentPositions(agentName) {
        try {
            const agentDataDir = this.currentMarket === 'us' ? 'agent_data' : 'agent_data_astock';
            const response = await fetch(`${this.baseDataPath}/${agentDataDir}/${agentName}/position/position.jsonl`);
            if (!response.ok) throw new Error(`Failed to load positions for ${agentName}`);

            const text = await response.text();
            const lines = text.trim().split('\n').filter(line => line.trim() !== '');
            const positions = lines.map(line => {
                try {
                    return JSON.parse(line);
                } catch (parseError) {
                    console.error(`Error parsing line for ${agentName}:`, line, parseError);
                    return null;
                }
            }).filter(pos => pos !== null);

            console.log(`Loaded ${positions.length} positions for ${agentName}`);
            return positions;
        } catch (error) {
            console.error(`Error loading positions for ${agentName}:`, error);
            return [];
        }
    }

    // Load all A-share stock prices from merged.jsonl
    async loadAStockPrices() {
        if (Object.keys(this.priceCache).length > 0) {
            return this.priceCache;
        }

        try {
            const response = await fetch(`${this.baseDataPath}/A_stock/merged.jsonl`);
            if (!response.ok) throw new Error('Failed to load A-share prices');

            const text = await response.text();
            const lines = text.trim().split('\n');
            
            for (const line of lines) {
                if (!line.trim()) continue;
                const data = JSON.parse(line);
                const symbol = data['Meta Data']['2. Symbol'];
                this.priceCache[symbol] = data['Time Series (Daily)'];
            }
            
            console.log(`Loaded prices for ${Object.keys(this.priceCache).length} A-share stocks`);
            return this.priceCache;
        } catch (error) {
            console.error('Error loading A-share prices:', error);
            return {};
        }
    }

    // Load price data for a specific stock symbol
    async loadStockPrice(symbol) {
        if (this.priceCache[symbol]) {
            return this.priceCache[symbol];
        }

        if (this.currentMarket === 'cn') {
            // For A-shares, load all prices at once
            await this.loadAStockPrices();
            return this.priceCache[symbol] || null;
        }

        // For US stocks, load individual JSON files
        try {
            const priceFilePrefix = window.configLoader.getPriceFilePrefix();
            const response = await fetch(`${this.baseDataPath}/${priceFilePrefix}${symbol}.json`);
            if (!response.ok) throw new Error(`Failed to load price for ${symbol}`);

            const data = await response.json();
            // Support both hourly (60min) and daily data formats
            this.priceCache[symbol] = data['Time Series (60min)'] || data['Time Series (Daily)'];
            return this.priceCache[symbol];
        } catch (error) {
            console.error(`Error loading price for ${symbol}:`, error);
            return null;
        }
    }

    // Get closing price for a symbol on a specific date
    async getClosingPrice(symbol, date) {
        const prices = await this.loadStockPrice(symbol);
        if (!prices || !prices[date]) {
            return null;
        }
        // Support both US format ('4. close') and A-share format ('4. sell price')
        const closePrice = prices[date]['4. close'] || prices[date]['4. sell price'];
        return closePrice ? parseFloat(closePrice) : null;
    }

    // Calculate total asset value for a position on a given date
    async calculateAssetValue(position, date) {
        let totalValue = position.positions.CASH || 0;
        let hasMissingPrice = false;

        // Get all stock symbols (exclude CASH)
        const symbols = Object.keys(position.positions).filter(s => s !== 'CASH');

        for (const symbol of symbols) {
            const shares = position.positions[symbol];
            if (shares > 0) {
                const price = await this.getClosingPrice(symbol, date);
                if (price && !isNaN(price)) {
                    totalValue += shares * price;
                } else {
                    console.warn(`Missing or invalid price for ${symbol} on ${date}`);
                    hasMissingPrice = true;
                }
            }
        }

        // If any stock price is missing, return null to skip this date
        if (hasMissingPrice) {
            return null;
        }

        return totalValue;
    }

    // Load complete data for an agent including asset values over time
    async loadAgentData(agentName) {
        console.log(`Starting to load data for ${agentName} in ${this.currentMarket} market...`);
        const positions = await this.loadAgentPositions(agentName);
        if (positions.length === 0) {
            console.log(`No positions found for ${agentName}`);
            return null;
        }

        console.log(`Processing ${positions.length} positions for ${agentName}...`);

        // Group positions by timestamp and take only the last position for each timestamp
        const positionsByTimestamp = {};
        positions.forEach(position => {
            const timestamp = position.date;
            if (!positionsByTimestamp[timestamp] || position.id > positionsByTimestamp[timestamp].id) {
                positionsByTimestamp[timestamp] = position;
            }
        });

        // Convert to array and sort by timestamp
        const uniquePositions = Object.values(positionsByTimestamp).sort((a, b) => {
            if (a.date !== b.date) {
                return a.date.localeCompare(b.date);
            }
            return a.id - b.id;
        });
        
        console.log(`Reduced from ${positions.length} to ${uniquePositions.length} unique daily positions for ${agentName}`);
        
        // Fill missing dates with previous day's positions
        const filledPositions = [];
        if (uniquePositions.length > 0) {
            const startDate = new Date(uniquePositions[0].date);
            const endDate = new Date(uniquePositions[uniquePositions.length - 1].date);
            
            let currentPosition = uniquePositions[0];
            let positionIndex = 0;
            
            // Iterate through all dates from start to end
            for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
                const dateStr = d.toISOString().split('T')[0];
                
                // Check if we have a position for this date
                if (positionIndex < uniquePositions.length && uniquePositions[positionIndex].date === dateStr) {
                    currentPosition = uniquePositions[positionIndex];
                    filledPositions.push(currentPosition);
                    positionIndex++;
                } else {
                    // Skip weekends (Saturday = 6, Sunday = 0)
                    const dayOfWeek = d.getDay();
                    if (dayOfWeek === 0 || dayOfWeek === 6) {
                        continue;
                    }
                    
                    // Fill with previous position but update the date
                    filledPositions.push({
                        ...currentPosition,
                        date: dateStr,
                        this_action: null  // No action on this day
                    });
                }
            }
        }
        
        console.log(`Filled positions from ${uniquePositions.length} to ${filledPositions.length} days for ${agentName}`);
        
        const assetHistory = [];

        for (const position of filledPositions) {
            const date = position.date;
            const assetValue = await this.calculateAssetValue(position, date);
            
            // Skip if asset value is invalid (e.g., missing price data for that day)
            if (assetValue === null || isNaN(assetValue) || assetValue <= 0) {
                console.warn(`Skipping date ${date} for ${agentName} due to invalid asset value: ${assetValue}`);
                continue;
            }
            
            assetHistory.push({
                date: timestamp,
                value: assetValue,
                id: position.id,
                action: position.this_action || null
            });
        }

        // Check if we have enough valid data
        if (assetHistory.length === 0) {
            console.warn(`No valid asset history for ${agentName}, all dates skipped due to missing prices`);
            return null;
        }

        const result = {
            name: agentName,
            positions: positions,
            assetHistory: assetHistory,
            initialValue: assetHistory[0]?.value || 10000,
            currentValue: assetHistory[assetHistory.length - 1]?.value || 0,
            return: assetHistory.length > 0 ?
                ((assetHistory[assetHistory.length - 1].value - assetHistory[0].value) / assetHistory[0].value * 100) : 0
        };

        console.log(`Successfully loaded data for ${agentName}:`, {
            positions: positions.length,
            assetHistory: assetHistory.length,
            initialValue: result.initialValue,
            currentValue: result.currentValue,
            return: result.return
        });

        return result;
    }

    // Load benchmark data (QQQ for US, SSE 50 for A-shares)
    async loadBenchmarkData() {
        if (this.currentMarket === 'us') {
            return await this.loadQQQData();
        } else {
            return await this.loadSSE50Data();
        }
    }

    // Load SSE 50 Index data for A-shares
    async loadSSE50Data() {
        try {
            console.log('Loading SSE 50 Index data...');
            // SSE 50 Index code: 000016.SH
            const response = await fetch(`${this.baseDataPath}/A_stock/index_daily_sse_50.json`);
            if (!response.ok) throw new Error('Failed to load SSE 50 Index data');
            
            const data = await response.json();
            const timeSeries = data['Time Series (Daily)'];
            
            if (!timeSeries) {
                console.warn('SSE 50 Index data not found');
                return null;
            }
            
            return this.createBenchmarkAssetHistory('SSE 50', timeSeries, 'CNY');
        } catch (error) {
            console.error('Error loading SSE 50 data:', error);
            return null;
        }
    }

    // Load QQQ invesco data
    async loadQQQData() {
        try {
            console.log('Loading QQQ invesco data...');
            const benchmarkFile = window.configLoader.getBenchmarkFile();
            const response = await fetch(`${this.baseDataPath}/${benchmarkFile}`);
            if (!response.ok) throw new Error('Failed to load QQQ data');

            const data = await response.json();
            // Support both hourly (60min) and daily data formats
            const timeSeries = data['Time Series (60min)'] || data['Time Series (Daily)'];
            
            return this.createBenchmarkAssetHistory('QQQ', timeSeries, 'USD');
        } catch (error) {
            console.error('Error loading QQQ data:', error);
            return null;
        }
    }

    // Create benchmark asset history from time series data
    createBenchmarkAssetHistory(name, timeSeries, currency) {
        try {
            // Convert to asset history format
            const assetHistory = [];
            const dates = Object.keys(timeSeries).sort();
            
            // Calculate benchmark performance starting from first agent's initial value
            const agentNames = Object.keys(this.agentData);
            const uiConfig = window.configLoader.getUIConfig();
            let initialValue = uiConfig.initial_value; // Default initial value from config
            
            if (agentNames.length > 0) {
                const firstAgent = this.agentData[agentNames[0]];
                if (firstAgent && firstAgent.assetHistory.length > 0) {
                    initialValue = firstAgent.assetHistory[0].value;
                }
            }
            
            // Find the earliest start date and latest end date across all agents
            let startDate = null;
            let endDate = null;
            if (agentNames.length > 0) {
                agentNames.forEach(agentName => {
                    const agent = this.agentData[agentName];
                    if (agent && agent.assetHistory.length > 0) {
                        const agentStartDate = agent.assetHistory[0].date;
                        const agentEndDate = agent.assetHistory[agent.assetHistory.length - 1].date;
                        
                        if (!startDate || agentStartDate < startDate) {
                            startDate = agentStartDate;
                        }
                        if (!endDate || agentEndDate > endDate) {
                            endDate = agentEndDate;
                        }
                    }
                });
            }
            
            let benchmarkStartPrice = null;
            let currentValue = initialValue;
            
            for (const date of dates) {
                if (startDate && date < startDate) continue;
                if (endDate && date > endDate) continue;
                
                // Support both US format ('4. close') and A-share format ('4. sell price')
                const closePrice = timeSeries[date]['4. close'] || timeSeries[date]['4. sell price'];
                if (!closePrice) continue;
                
                const price = parseFloat(closePrice);
                if (!benchmarkStartPrice) {
                    benchmarkStartPrice = price;
                }
                
                // Calculate benchmark performance relative to start
                const benchmarkReturn = (price - benchmarkStartPrice) / benchmarkStartPrice;
                currentValue = initialValue * (1 + benchmarkReturn);
                
                assetHistory.push({
                    date: date,
                    value: currentValue,
                    id: `${name.toLowerCase().replace(/\s+/g, '-')}-${date}`,
                    action: null
                });
            }

            const result = {
                name: name,
                positions: [],
                assetHistory: assetHistory,
                initialValue: initialValue,
                currentValue: assetHistory.length > 0 ? assetHistory[assetHistory.length - 1].value : initialValue,
                return: assetHistory.length > 0 ?
                    ((assetHistory[assetHistory.length - 1].value - assetHistory[0].value) / assetHistory[0].value * 100) : 0,
                currency: currency
            };
            
            console.log(`Successfully loaded ${name} data:`, {
                assetHistory: assetHistory.length,
                initialValue: result.initialValue,
                currentValue: result.currentValue,
                return: result.return
            });
            
            return result;
        } catch (error) {
            console.error(`Error creating benchmark asset history for ${name}:`, error);
            return null;
        }
    }

    // Load all agents data
    async loadAllAgentsData() {
        console.log('Starting to load all agents data...');
        const agents = await this.loadAgentList();
        console.log('Found agents:', agents);
        const allData = {};

        for (const agent of agents) {
            console.log(`Loading data for ${agent}...`);
            const data = await this.loadAgentData(agent);
            if (data) {
                allData[agent] = data;
                console.log(`Successfully added ${agent} to allData`);
            } else {
                console.log(`Failed to load data for ${agent}`);
            }
        }

        console.log('Final allData:', Object.keys(allData));
        this.agentData = allData;
        
        // Load benchmark data (QQQ for US, SSE 50 for A-shares)
        const benchmarkData = await this.loadBenchmarkData();
        if (benchmarkData) {
            allData[benchmarkData.name] = benchmarkData;
            console.log(`Successfully added ${benchmarkData.name} benchmark to allData`);
        }

        return allData;
    }

    // Get current holdings for an agent (latest position)
    getCurrentHoldings(agentName) {
        const data = this.agentData[agentName];
        if (!data || !data.positions || data.positions.length === 0) return null;

        const latestPosition = data.positions[data.positions.length - 1];
        return latestPosition && latestPosition.positions ? latestPosition.positions : null;
    }

    // Get trade history for an agent
    getTradeHistory(agentName) {
        const data = this.agentData[agentName];
        if (!data) return [];

        return data.positions
            .filter(p => p.this_action)
            .map(p => ({
                date: p.date,
                action: p.this_action.action,
                symbol: p.this_action.symbol,
                amount: p.this_action.amount
            }))
            .reverse(); // Most recent first
    }

    // Format number as currency
    formatCurrency(value) {
        const currency = this.currentMarket === 'us' ? 'USD' : 'CNY';
        const locale = this.currentMarket === 'us' ? 'en-US' : 'zh-CN';
        
        return new Intl.NumberFormat(locale, {
            style: 'currency',
            currency: currency,
            minimumFractionDigits: 2
        }).format(value);
    }

    // Format percentage
    formatPercent(value) {
        const sign = value >= 0 ? '+' : '';
        return `${sign}${value.toFixed(2)}%`;
    }

    // Get nice display name for agent
    getAgentDisplayName(agentName) {
        const names = {
            'gemini-2.5-flash': 'Gemini-2.5-flash',
            'qwen3-max': 'Qwen3-max',
            'MiniMax-M2': 'MiniMax-M2',
            'gpt-5': 'GPT-5',
            'deepseek-chat-v3.1': 'DeepSeek-v3.1',
            'claude-3.7-sonnet': 'Claude 3.7 Sonnet',
            'QQQ': 'QQQ ETF',
            'SSE 50': 'SSE 50 Index'
        };
        return names[agentName] || agentName;
    }

    // Get icon for agent (SVG file path)
    getAgentIcon(agentName) {
        const icons = {
            'gemini-2.5-flash': './figs/google.svg',
            'qwen3-max': './figs/qwen.svg',
            'MiniMax-M2': './figs/minimax.svg',
            'gpt-5': './figs/openai.svg',
            'claude-3.7-sonnet': './figs/claude-color.svg',
            'deepseek-chat-v3.1': './figs/deepseek.svg',
            'QQQ': './figs/stock.svg',
            'SSE 50': './figs/stock.svg'
        };
        return icons[agentName] || './figs/stock.svg';
    }

    // Get agent name without version suffix for icon lookup
    getAgentIconKey(agentName) {
        // This method is kept for backward compatibility
        return agentName;
    }

    // Get brand color for agent
    getAgentBrandColor(agentName) {
        const colors = {
            'gemini-2.5-flash': '#8A2BE2',      // Google purple
            'qwen3-max': '#0066ff',       // Qwen Blue
            'MiniMax-M2': '#ff0000',       // MiniMax Red
            'gpt-5': '#10a37f',                  // OpenAI Green
            'deepseek-chat-v3.1': '#4a90e2',  // DeepSeek Blue
            'claude-3.7-sonnet': '#cc785c', // Anthropic Orange
            'QQQ': '#ff6b00',                       // QQQ Orange
            'SSE 50': '#e74c3c'              // SSE 50 Red
        };
        return colors[agentName] || null;
    }
}

// Export for use in other modules
window.DataLoader = DataLoader;
