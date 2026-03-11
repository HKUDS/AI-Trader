// Data Loader Utility
// Handles loading and processing all trading data

class DataLoader {
    constructor() {
        this.agentData = {};
        this.priceCache = {};
        this.config = null;
        this.baseDataPath = './data';
        this.currentMarket = 'us'; // 'us' or 'cn'
        this.cacheManager = new CacheManager(); // Initialize cache manager
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

    // Get current market configuration
    getMarketConfig() {
        return window.configLoader.getMarketConfig(this.currentMarket);
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
        try {
            // Ensure config is loaded
            await this.initialize();

            const marketConfig = this.getMarketConfig();
            const agentDataDir = marketConfig ? marketConfig.data_dir : 'agent_data';
            const agents = [];
            const enabledAgents = window.configLoader.getEnabledAgents(this.currentMarket);

            for (const agentConfig of enabledAgents) {
                try {
                    console.log(`Checking agent: ${agentConfig.folder} in ${agentDataDir}`);
                    const response = await fetch(`${this.baseDataPath}/${agentDataDir}/${agentConfig.folder}/position/position.jsonl`);
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
            const marketConfig = this.getMarketConfig();
            const agentDataDir = marketConfig ? marketConfig.data_dir : 'agent_data';
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
            const marketConfig = this.getMarketConfig();
            // Default to merged.jsonl if not specified
            const priceFile = marketConfig && marketConfig.price_data_file ? 
                marketConfig.price_data_file : 'A_stock/merged.jsonl';
            
            console.log(`Loading A-share prices from ${priceFile}...`);
            const response = await fetch(`${this.baseDataPath}/${priceFile}`);
            if (!response.ok) throw new Error(`Failed to load A-share prices from ${priceFile}`);

            const text = await response.text();
            const lines = text.trim().split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                const data = JSON.parse(line);
                const symbol = data['Meta Data']['2. Symbol'];
                // Support both Daily and 60min keys
                this.priceCache[symbol] = data['Time Series (Daily)'] || data['Time Series (60min)'];
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

        if (this.currentMarket.startsWith('cn')) {
            // For A-shares, load all prices at once
            await this.loadAStockPrices();
            return this.priceCache[symbol] || null;
        }

        // For US stocks, load individual JSON files
        try {
            const priceFilePrefix = window.configLoader.getPriceFilePrefix();
            const filePath = `${this.baseDataPath}/${priceFilePrefix}${symbol}.json`;
            const response = await fetch(filePath);
            if (!response.ok) {
                console.warn(`[loadStockPrice] ❌ ${symbol}: HTTP ${response.status}`);
                throw new Error(`Failed to load price for ${symbol}`);
            }

            const data = await response.json();
            // Support both hourly (60min) and daily data formats
            this.priceCache[symbol] = data['Time Series (60min)'] || data['Time Series (Daily)'];

            if (!this.priceCache[symbol]) {
                console.warn(`[loadStockPrice] ❌ ${symbol}: No time series data found`);
                return null;
            }

            const dataPointCount = Object.keys(this.priceCache[symbol]).length;
            const sampleDates = Object.keys(this.priceCache[symbol]).sort().slice(0, 3);
            console.log(`[loadStockPrice] ✅ ${symbol}: ${dataPointCount} points, samples: ${sampleDates.join(', ')}`);

            return this.priceCache[symbol];
        } catch (error) {
            console.error(`[loadStockPrice] ❌ ${symbol}:`, error.message);
            return null;
        }
    }

    // Get closing price for a symbol on a specific date/time
    async getClosingPrice(symbol, dateOrTimestamp) {
        const prices = await this.loadStockPrice(symbol);
        if (!prices) {
            return null;
        }

        // Try exact match first (for hourly data like "2025-10-01 10:00:00")
        if (prices[dateOrTimestamp]) {
            const closePrice = prices[dateOrTimestamp]['4. close'] || prices[dateOrTimestamp]['4. sell price'];
            return closePrice ? parseFloat(closePrice) : null;
        }

        // For A-shares: Extract date only for daily data matching
        // Only do this fuzzy matching if we are NOT in hourly mode or if exact match failed
        if (this.currentMarket.startsWith('cn')) {
            const dateOnly = dateOrTimestamp.split(' ')[0]; // "2025-10-01 10:00:00" -> "2025-10-01"
            if (prices[dateOnly]) {
                const closePrice = prices[dateOnly]['4. close'] || prices[dateOnly]['4. sell price'];
                return closePrice ? parseFloat(closePrice) : null;
            }

            // If still not found, try to find the closest timestamp on the same date (for hourly data)
            const datePrefix = dateOnly;
            const matchingKeys = Object.keys(prices).filter(key => key.startsWith(datePrefix));

            if (matchingKeys.length > 0) {
                // Use the last (most recent) timestamp for that date
                const lastKey = matchingKeys.sort().pop();
                const closePrice = prices[lastKey]['4. close'] || prices[lastKey]['4. sell price'];
                return closePrice ? parseFloat(closePrice) : null;
            }
        }

        return null;
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

        // For A-shares: If any stock price is missing, return null to skip this date
        if (this.currentMarket.startsWith('cn') && hasMissingPrice) {
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

        let assetHistory = [];
        
        const marketConfig = this.getMarketConfig();
        const isHourlyConfig = marketConfig && marketConfig.time_granularity === 'hourly';

        if (this.currentMarket.startsWith('cn') && !isHourlyConfig) {
            // A-SHARES DAILY LOGIC: Handle multiple transactions per day AND fill date gaps
            // Used only for 'cn' (daily) market, not 'cn_hour'

            // Detect if data is hourly or daily
            const firstDate = positions[0]?.date || '';
            const isHourlyData = firstDate.includes(':'); // Has time component

            console.log(`Detected ${isHourlyData ? 'hourly' : 'daily'} data format for ${agentName}`);

            // Group positions by DATE (for hourly data, group by date and take last entry)
            const positionsByDate = {};
            positions.forEach(position => {
                let dateKey;
                if (isHourlyData) {
                    // Extract date only: "2025-10-01 10:00:00" -> "2025-10-01"
                    dateKey = position.date.split(' ')[0];
                } else {
                    // Already in date format: "2025-10-01"
                    dateKey = position.date;
                }

                // Skip weekends when building position map
                const d = new Date(dateKey + 'T00:00:00');
                const dayOfWeek = d.getDay();
                if (dayOfWeek === 0 || dayOfWeek === 6) {
                    console.log(`Skipping weekend date ${dateKey} from position data`);
                    return; // Skip this position (it's a weekend)
                }

                // Keep the position with the highest ID for each date (most recent)
                if (!positionsByDate[dateKey] || position.id > positionsByDate[dateKey].id) {
                    positionsByDate[dateKey] = {
                        ...position,
                        dateKey: dateKey,  // Store normalized date for price lookup
                        originalDate: position.date  // Keep original for reference
                    };
                }
            });

            // Convert to array and sort by date
            const uniquePositions = Object.values(positionsByDate).sort((a, b) => {
                return a.dateKey.localeCompare(b.dateKey);
            });

            console.log(`Reduced from ${positions.length} to ${uniquePositions.length} unique daily positions for ${agentName}`);

            if (uniquePositions.length === 0) {
                console.warn(`No unique positions for ${agentName}`);
                return null;
            }

            // Get date range
            const startDate = new Date(uniquePositions[0].dateKey + 'T00:00:00');
            const endDate = new Date(uniquePositions[uniquePositions.length - 1].dateKey + 'T00:00:00');

            // Create a map of positions by date for quick lookup
            const positionMap = {};
            uniquePositions.forEach(pos => {
                positionMap[pos.dateKey] = pos;
            });

            // Fill all dates in range (skip weekends)
            let currentPosition = null;
            for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
                // Extract date string in local timezone (avoid UTC conversion issues)
                const year = d.getFullYear();
                const month = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                const dateStr = `${year}-${month}-${day}`;
                const dayOfWeek = d.getDay();

                // Skip weekends (Saturday = 6, Sunday = 0)
                if (dayOfWeek === 0 || dayOfWeek === 6) {
                    console.log(`Skipping weekend in gap-fill loop: ${dateStr} (day ${dayOfWeek})`);
                    continue;
                }

                // Use position for this date if exists, otherwise use last known position
                if (positionMap[dateStr]) {
                    currentPosition = positionMap[dateStr];
                }

                // Skip if we don't have any position yet
                if (!currentPosition) {
                    continue;
                }

                // Calculate asset value using current iteration date for price lookup
                const assetValue = await this.calculateAssetValue(currentPosition, dateStr);

                if (assetValue === null || isNaN(assetValue)) {
                    console.warn(`Skipping date ${dateStr} for ${agentName} due to missing price data`);
                    continue;
                }

                assetHistory.push({
                    date: dateStr,
                    value: assetValue,
                    id: currentPosition.id,
                    action: positionMap[dateStr]?.this_action || null  // Only show action if position changed
                });
            }

        } else {
            // US STOCKS OR CN HOURLY LOGIC: Keep timestamps, do not flatten to daily
            console.log(`Using fine-grained timestamp logic for ${this.currentMarket} (hourly/raw mode)`);

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

            console.log(`Reduced from ${positions.length} to ${uniquePositions.length} unique positions for ${agentName}`);

            for (const position of uniquePositions) {
                const timestamp = position.date;
                const assetValue = await this.calculateAssetValue(position, timestamp);
                
                // For CN Hourly, we might have missing prices if timestamp doesn't align perfectly
                if (assetValue === null) {
                     console.warn(`Skipping timestamp ${timestamp} for ${agentName} due to missing price`);
                     continue;
                }

                assetHistory.push({
                    date: timestamp,
                    value: assetValue,
                    id: position.id,
                    action: position.this_action || null
                });
            }
        }

        // Check if we have enough valid data
        if (assetHistory.length === 0) {
            console.error(`❌ ${agentName}: NO VALID ASSET HISTORY`);
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
            return: result.return,
            dateRange: assetHistory.length > 0 ?
                `${assetHistory[0].date} to ${assetHistory[assetHistory.length - 1].date}` : 'N/A',
            sampleDates: assetHistory.slice(0, 5).map(h => h.date)
        });

        return result;
    }

    // Load benchmark data (QQQ for US, SSE 50 for A-shares)
    async loadBenchmarkData() {
        const marketConfig = this.getMarketConfig();
        if (!marketConfig) {
            return await this.loadQQQData();
        }

        if (this.currentMarket === 'us') {
            return await this.loadQQQData();
        } else if (this.currentMarket.startsWith('cn')) {
            return await this.loadSSE50Data();
        }

        return null;
    }

    // Aggregate hourly time series data to daily (take end-of-day close price)
    aggregateHourlyToDaily(hourlyTimeSeries) {
        const dailyData = {};
        const dates = Object.keys(hourlyTimeSeries).sort();
        
        for (const timestamp of dates) {
            const dateOnly = timestamp.split(' ')[0]; // Extract date part
            const hour = timestamp.split(' ')[1]?.split(':')[0]; // Extract hour
            
            // Keep the last (end of day) price for each date
            // Assuming market closes at 15:00 (3 PM)
            if (!dailyData[dateOnly] || hour === '15') {
                dailyData[dateOnly] = hourlyTimeSeries[timestamp];
            }
        }
        
        console.log(`Aggregated ${dates.length} hourly data points to ${Object.keys(dailyData).length} daily data points`);
        return dailyData;
    }

    // Load SSE 50 Index data for A-shares
    async loadSSE50Data() {
        try {
            console.log('Loading SSE 50 Index data...');
            // Always use daily SSE 50 data, even in hourly mode
            const benchmarkFile = 'A_stock/index_daily_sse_50.json';

            const response = await fetch(`${this.baseDataPath}/${benchmarkFile}`);
            if (!response.ok) throw new Error('Failed to load SSE 50 Index data');

            const data = await response.json();
            const timeSeries = data['Time Series (Daily)'];

            if (!timeSeries) {
                console.warn('SSE 50 Index data not found');
                return null;
            }

            const marketConfig = this.getMarketConfig();
            const benchmarkName = marketConfig ? marketConfig.benchmark_display_name : 'SSE 50';
            
            // For hourly mode, we need to expand daily benchmark to match hourly agent timestamps
            const isHourlyMode = this.currentMarket === 'cn_hour';
            return this.createBenchmarkAssetHistory(benchmarkName, timeSeries, 'CNY', isHourlyMode);
        } catch (error) {
            console.error('Error loading SSE 50 data:', error);
            return null;
        }
    }

    // Load QQQ invesco data
    async loadQQQData() {
        try {
            console.log('Loading QQQ invesco data...');
            // Use market-specific benchmark file if available
            const marketConfig = this.getMarketConfig();
            const benchmarkFile = marketConfig ? marketConfig.benchmark_file : window.configLoader.getBenchmarkFile();
            const benchmarkName = marketConfig ? marketConfig.benchmark_display_name : 'QQQ Invesco';
            
            console.log(`Loading benchmark from: ${this.baseDataPath}/${benchmarkFile}`);
            const response = await fetch(`${this.baseDataPath}/${benchmarkFile}`);
            if (!response.ok) throw new Error(`Failed to load QQQ data: ${response.status}`);

            const data = await response.json();
            // Support both hourly (60min) and daily data formats
            const timeSeries = data['Time Series (60min)'] || data['Time Series (Daily)'];

            if (!timeSeries) {
                console.error('No time series data found in QQQ file');
                return null;
            }

            console.log(`QQQ time series has ${Object.keys(timeSeries).length} data points`);
            
            // Detect if agents are using daily or hourly data
            const agentNames = Object.keys(this.agentData);
            let isAgentHourly = false;
            if (agentNames.length > 0) {
                const firstAgent = this.agentData[agentNames[0]];
                if (firstAgent && firstAgent.assetHistory.length > 0) {
                    const firstDate = firstAgent.assetHistory[0].date;
                    isAgentHourly = firstDate.includes(':'); // Has time component
                    console.log(`Agent data granularity detected: ${isAgentHourly ? 'Hourly' : 'Daily'}`);
                }
            }
            
            // If agents are daily but QQQ is hourly, we need to aggregate QQQ to daily
            const qqqIsHourly = Object.keys(timeSeries)[0]?.includes(':');
            const needsAggregation = !isAgentHourly && qqqIsHourly;
            
            let processedTimeSeries = timeSeries;
            if (needsAggregation) {
                console.log('Aggregating hourly QQQ data to daily for daily agents');
                processedTimeSeries = this.aggregateHourlyToDaily(timeSeries);
            }
            
            return this.createBenchmarkAssetHistory(benchmarkName, processedTimeSeries, 'USD');
        } catch (error) {
            console.error('Error loading QQQ data:', error);
            return null;
        }
    }

    // Create benchmark asset history from time series data
    createBenchmarkAssetHistory(name, timeSeries, currency, expandToHourly = false) {
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
            // Collect all agent timestamps for hourly expansion
            const allAgentTimestamps = new Set();
            
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
                        
                        // Collect all timestamps if we need to expand
                        if (expandToHourly) {
                            agent.assetHistory.forEach(h => allAgentTimestamps.add(h.date));
                        }
                    }
                });
            }

            let benchmarkStartPrice = null;
            let currentValue = initialValue;
            
            // Build a price map for easy lookup
            const priceMap = {};
            for (const date of dates) {
                const closePrice = timeSeries[date]['4. close'] || timeSeries[date]['4. sell price'];
                if (closePrice) {
                    priceMap[date] = parseFloat(closePrice);
                }
            }

            // If expanding to hourly, use agent timestamps; otherwise use benchmark dates
            const timestampsToUse = expandToHourly ? 
                Array.from(allAgentTimestamps).sort() : 
                dates;

            // Determine if benchmark data is hourly (has time component)
            const isHourlyBenchmark = dates.length > 0 && dates[0].includes(':');
            console.log(`Benchmark data type: ${isHourlyBenchmark ? 'Hourly' : 'Daily'}, expandToHourly: ${expandToHourly}`);

            for (const timestamp of timestampsToUse) {
                // Skip if outside agent date range
                if (startDate && timestamp < startDate) continue;
                if (endDate && timestamp > endDate) continue;

                // Find the benchmark price
                let price;
                if (isHourlyBenchmark && !expandToHourly) {
                    // Hourly benchmark data (like QQQ 60min), use exact timestamp
                    price = priceMap[timestamp];
                } else if (expandToHourly) {
                    // Daily benchmark data expanded to hourly timestamps, use date part
                    const dateOnly = timestamp.split(' ')[0];
                    price = priceMap[dateOnly];
                } else {
                    // Daily benchmark data with daily timestamps
                    price = priceMap[timestamp];
                }
                
                if (!price) {
                    // console.warn(`No price found for ${timestamp}`);
                    continue;
                }

                if (!benchmarkStartPrice) {
                    benchmarkStartPrice = price;
                }

                // Calculate benchmark performance relative to start
                const benchmarkReturn = (price - benchmarkStartPrice) / benchmarkStartPrice;
                currentValue = initialValue * (1 + benchmarkReturn);

                assetHistory.push({
                    date: timestamp,
                    value: currentValue,
                    id: `${name.toLowerCase().replace(/\s+/g, '-')}-${timestamp}`,
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

    // Load all agents data with caching
    async loadAllAgentsData() {
        const startTime = performance.now();
        console.log('Starting to load all agents data...');

        // Try to load from cache first
        const cachedData = await this.cacheManager.loadCache(this.currentMarket);

        if (cachedData) {
            const loadTime = performance.now() - startTime;
            console.log('✓ Using cached data (fast path)');

            if (this.cacheManager.shouldShowPerformanceMetrics()) {
                console.log(`%c⚡ Total data load time: ${loadTime.toFixed(2)}ms (cached)`, 'color: #00ff00; font-weight: bold');
            }

            this.agentData = cachedData;
            return cachedData;
        }

        // Cache miss or disabled - fall back to live calculation
        console.log('⚠ Cache miss - performing live calculation (slow path)');
        const calcStartTime = performance.now();

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
            console.log(`Successfully added ${benchmarkData.name} to allData`);
        }

        const calcTime = performance.now() - calcStartTime;
        const totalTime = performance.now() - startTime;

        if (this.cacheManager.shouldShowPerformanceMetrics()) {
            console.log(`%c⏱️  Live calculation time: ${calcTime.toFixed(2)}ms`, 'color: #ffbe0b; font-weight: bold');
            console.log(`%c⏱️  Total data load time: ${totalTime.toFixed(2)}ms (live)`, 'color: #ff006e; font-weight: bold');

            // Show potential speedup if cache was enabled
            const cacheMetrics = this.cacheManager.getPerformanceMetrics();
            if (cacheMetrics.lastLoadTime) {
                const speedup = (totalTime / cacheMetrics.lastLoadTime).toFixed(1);
                console.log(`%c💡 Cache would be ${speedup}x faster!`, 'color: #8338ec; font-weight: bold');
            }
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
        if (!data) {
            console.log(`[getTradeHistory] No data for agent: ${agentName}`);
            return [];
        }

        console.log(`[getTradeHistory] Agent: ${agentName}, Total positions: ${data.positions.length}`);

        const allActions = data.positions.filter(p => p.this_action);
        console.log(`[getTradeHistory] Positions with this_action: ${allActions.length}`);

        const trades = data.positions
            .filter(p => p.this_action && p.this_action.action !== 'no_trade')
            .map(p => ({
                date: p.date,
                action: p.this_action.action,
                symbol: p.this_action.symbol,
                amount: p.this_action.amount
            }))
            .reverse(); // Most recent first

        console.log(`[getTradeHistory] Actual trades (excluding no_trade): ${trades.length}`);
        console.log(`[getTradeHistory] First 3 trades:`, trades.slice(0, 3));

        return trades;
    }

    // Format number as currency
    formatCurrency(value) {
        const marketConfig = this.getMarketConfig();
        const currency = marketConfig ? marketConfig.currency : 'USD';
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
        const displayName = window.configLoader.getDisplayName(agentName, this.currentMarket);
        if (displayName) return displayName;

        // Fallback to legacy names
        const names = {
            'gemini-2.5-flash': 'Gemini-2.5-flash',
            'qwen3-max': 'Qwen3-max',
            'MiniMax-M2': 'MiniMax-M2',
            'gpt-5': 'GPT-5',
            'deepseek-chat-v3.1': 'DeepSeek-v3.1',
            'claude-3.7-sonnet': 'Claude 3.7 Sonnet',
            'QQQ Invesco': 'QQQ ETF',
            'SSE 50 Index': 'SSE 50 Index'
        };
        return names[agentName] || agentName;
    }

    // Get icon for agent (SVG file path)
    getAgentIcon(agentName) {
        const icon = window.configLoader.getIcon(agentName, this.currentMarket);
        if (icon) return icon;

        // Fallback to legacy icons
        const icons = {
            'gemini-2.5-flash': './figs/google.svg',
            'qwen3-max': './figs/qwen.svg',
            'MiniMax-M2': './figs/minimax.svg',
            'gpt-5': './figs/openai.svg',
            'claude-3.7-sonnet': './figs/claude-color.svg',
            'deepseek-chat-v3.1': './figs/deepseek.svg',
            'QQQ Invesco': './figs/stock.svg',
            'SSE 50 Index': './figs/stock.svg'
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
        const color = window.configLoader.getColor(agentName, this.currentMarket);
        console.log(`[getAgentBrandColor] agentName: ${agentName}, market: ${this.currentMarket}, color: ${color}`);
        if (color) return color;

        // Fallback to legacy colors
        const colors = {
            'gemini-2.5-flash': '#8A2BE2',
            'qwen3-max': '#0066ff',
            'MiniMax-M2': '#ff0000',
            'gpt-5': '#10a37f',
            'deepseek-chat-v3.1': '#4a90e2',
            'claude-3.7-sonnet': '#cc785c',
            'QQQ Invesco': '#ff6b00',
            'SSE 50 Index': '#e74c3c'
        };
        return colors[agentName] || null;
    }

    // Get cache manager instance
    getCacheManager() {
        return this.cacheManager;
    }
}

// Export for use in other modules and expose globally
window.DataLoader = DataLoader;

// Expose cache manager globally for easy access
if (typeof window !== 'undefined') {
    window.cacheManager = new CacheManager();
}