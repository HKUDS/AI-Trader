// Portfolio Analysis Page
// Detailed view of individual agent portfolios

const dataLoader = new DataLoader();
let allAgentsData = {};
let currentAgent = null;
let allocationChart = null;

// Load data and refresh UI
async function loadDataAndRefresh() {
    showLoading();

    try {
        // Load all agents data
        console.log('Loading all agents data...');
        allAgentsData = await dataLoader.loadAllAgentsData();
        console.log('Data loaded:', allAgentsData);

        // Populate agent selector
        populateAgentSelector();

        // Load first agent by default
        const firstAgent = Object.keys(allAgentsData)[0];
        if (firstAgent) {
            currentAgent = firstAgent;
            await loadAgentPortfolio(firstAgent);
        }

    } catch (error) {
        console.error('Error loading data:', error);
        alert('Failed to load portfolio data. Please check console for details.');
    } finally {
        hideLoading();
    }
}

// Initialize the page
async function init() {
    // Set up event listeners first
    setupEventListeners();

    // Load initial data
    await loadDataAndRefresh();
    
    // Initialize UI state
    updateMarketUI();
}

// Populate agent selector dropdown
function populateAgentSelector() {
    const select = document.getElementById('agentSelect');
    select.innerHTML = '';

    Object.keys(allAgentsData).forEach(agentName => {
        const option = document.createElement('option');
        option.value = agentName;
        // Use text only for dropdown options (HTML select doesn't support images well)
        option.textContent = dataLoader.getAgentDisplayName(agentName);
        select.appendChild(option);
    });
}

// Load and display portfolio for selected agent
async function loadAgentPortfolio(agentName) {
    showLoading();

    try {
        currentAgent = agentName;
        const data = allAgentsData[agentName];

        // Update performance metrics
        updateMetrics(data);

        // Update holdings table
        await updateHoldingsTable(agentName);

        // Update allocation chart
        await updateAllocationChart(agentName);

        // Update trade history
        updateTradeHistory(agentName);

    } catch (error) {
        console.error('Error loading portfolio:', error);
    } finally {
        hideLoading();
    }
}

// Update performance metrics
function updateMetrics(data) {
    const totalAsset = data.currentValue;
    const totalReturn = data.return;
    const latestPosition = data.positions && data.positions.length > 0 ? data.positions[data.positions.length - 1] : null;
    const cashPosition = latestPosition && latestPosition.positions ? latestPosition.positions.CASH || 0 : 0;
    const totalTrades = data.positions ? data.positions.filter(p => p.this_action).length : 0;

    document.getElementById('totalAsset').textContent = dataLoader.formatCurrency(totalAsset);
    document.getElementById('totalReturn').textContent = dataLoader.formatPercent(totalReturn);
    document.getElementById('totalReturn').className = `metric-value ${totalReturn >= 0 ? 'positive' : 'negative'}`;
    document.getElementById('cashPosition').textContent = dataLoader.formatCurrency(cashPosition);
    document.getElementById('totalTrades').textContent = totalTrades;
}

// Update holdings table
async function updateHoldingsTable(agentName) {
    const holdings = dataLoader.getCurrentHoldings(agentName);
    const tableBody = document.getElementById('holdingsTableBody');
    tableBody.innerHTML = '';

    if (!holdings) {
        return;
    }

    const data = allAgentsData[agentName];
    if (!data || !data.assetHistory || data.assetHistory.length === 0) {
        return;
    }

    const latestDate = data.assetHistory[data.assetHistory.length - 1].date;
    const totalValue = data.currentValue;

    // Get all stocks with non-zero holdings
    const stocks = Object.entries(holdings)
        .filter(([symbol, shares]) => symbol !== 'CASH' && shares > 0);

    // Sort by market value (descending)
    const holdingsData = await Promise.all(
        stocks.map(async ([symbol, shares]) => {
            const price = await dataLoader.getClosingPrice(symbol, latestDate);
            const marketValue = price ? shares * price : 0;
            return { symbol, shares, price, marketValue };
        })
    );

    holdingsData.sort((a, b) => b.marketValue - a.marketValue);

    // Create table rows
    holdingsData.forEach(holding => {
        const weight = (holding.marketValue / totalValue * 100).toFixed(2);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="symbol">${holding.symbol}</td>
            <td>${holding.shares}</td>
            <td>${dataLoader.formatCurrency(holding.price || 0)}</td>
            <td>${dataLoader.formatCurrency(holding.marketValue)}</td>
            <td>${weight}%</td>
        `;
        tableBody.appendChild(row);
    });

    // Add cash row
    if (holdings.CASH > 0) {
        const cashWeight = (holdings.CASH / totalValue * 100).toFixed(2);
        const cashRow = document.createElement('tr');
        cashRow.innerHTML = `
            <td class="symbol">CASH</td>
            <td>-</td>
            <td>-</td>
            <td>${dataLoader.formatCurrency(holdings.CASH)}</td>
            <td>${cashWeight}%</td>
        `;
        tableBody.appendChild(cashRow);
    }

    // If no holdings data, show a message
    if (holdingsData.length === 0 && (!holdings.CASH || holdings.CASH === 0)) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = `
            <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                No holdings data available
            </td>
        `;
        tableBody.appendChild(noDataRow);
    }
}

// Update allocation chart (pie chart)
async function updateAllocationChart(agentName) {
    const holdings = dataLoader.getCurrentHoldings(agentName);
    if (!holdings) return;

    const data = allAgentsData[agentName];
    const latestDate = data.assetHistory[data.assetHistory.length - 1].date;

    // Calculate market values
    const allocations = [];

    for (const [symbol, shares] of Object.entries(holdings)) {
        if (symbol === 'CASH') {
            if (shares > 0) {
                allocations.push({ label: 'CASH', value: shares });
            }
        } else if (shares > 0) {
            const price = await dataLoader.getClosingPrice(symbol, latestDate);
            if (price) {
                allocations.push({ label: symbol, value: shares * price });
            }
        }
    }

    // Sort by value and take top 10, combine rest as "Others"
    allocations.sort((a, b) => b.value - a.value);

    const topAllocations = allocations.slice(0, 10);
    const othersValue = allocations.slice(10).reduce((sum, a) => sum + a.value, 0);

    if (othersValue > 0) {
        topAllocations.push({ label: 'Others', value: othersValue });
    }

    // Destroy existing chart
    if (allocationChart) {
        allocationChart.destroy();
    }

    // Create new chart
    const ctx = document.getElementById('allocationChart').getContext('2d');
    const colors = [
        '#00d4ff', '#00ffcc', '#ff006e', '#ffbe0b', '#8338ec',
        '#3a86ff', '#fb5607', '#06ffa5', '#ff006e', '#ffbe0b', '#8338ec'
    ];

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: topAllocations.map(a => a.label),
            datasets: [{
                data: topAllocations.map(a => a.value),
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#1a2238'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#a0aec0',
                        padding: 15,
                        font: {
                            size: 12
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 34, 56, 0.95)',
                    titleColor: '#00d4ff',
                    bodyColor: '#fff',
                    borderColor: '#2d3748',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = dataLoader.formatCurrency(context.parsed);
                            const total = context.dataset.data.reduce((sum, v) => sum + v, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Update trade history timeline
function updateTradeHistory(agentName) {
    const trades = dataLoader.getTradeHistory(agentName);
    const timeline = document.getElementById('tradeTimeline');
    timeline.innerHTML = '';

    if (trades.length === 0) {
        timeline.innerHTML = '<p style="color: var(--text-muted);">No trade history available.</p>';
        return;
    }

    // Show latest 20 trades
    const recentTrades = trades.slice(0, 20);

    recentTrades.forEach(trade => {
        const tradeItem = document.createElement('div');
        tradeItem.className = 'trade-item';

        const icon = trade.action === 'buy' ? '📈' : '📉';
        const iconClass = trade.action === 'buy' ? 'buy' : 'sell';
        const actionText = trade.action === 'buy' ? 'Bought' : 'Sold';

        // Format the timestamp for hourly data
        let formattedDate = trade.date;
        if (trade.date.includes(':')) {
            const date = new Date(trade.date);
            formattedDate = date.toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        tradeItem.innerHTML = `
            <div class="trade-icon ${iconClass}">${icon}</div>
            <div class="trade-details">
                <div class="trade-action">${actionText} ${trade.amount} shares of ${trade.symbol}</div>
                <div class="trade-meta">${formattedDate}</div>
            </div>
        `;

        timeline.appendChild(tradeItem);
    });
}

// Update UI based on current market state
function updateMarketUI() {
    const currentMarket = dataLoader.getMarket();
    const usBtn = document.getElementById('usMarketBtn');
    const cnBtn = document.getElementById('cnMarketBtn');
    const granularityWrapper = document.getElementById('granularityWrapper');
    const dailyBtn = document.getElementById('dailyBtn');
    const hourlyBtn = document.getElementById('hourlyBtn');

    // Reset all active states
    if (usBtn) usBtn.classList.remove('active');
    if (cnBtn) cnBtn.classList.remove('active');
    if (dailyBtn) dailyBtn.classList.remove('active');
    if (hourlyBtn) hourlyBtn.classList.remove('active');

    if (currentMarket === 'us') {
        if (usBtn) usBtn.classList.add('active');
        if (granularityWrapper) granularityWrapper.classList.add('hidden');
    } else {
        // Both 'cn' and 'cn_hour' keep the main CN button active
        if (cnBtn) cnBtn.classList.add('active');
        if (granularityWrapper) granularityWrapper.classList.remove('hidden');
        
        if (currentMarket === 'cn_hour') {
            if (hourlyBtn) hourlyBtn.classList.add('active');
        } else {
            if (dailyBtn) dailyBtn.classList.add('active');
        }
    }
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('agentSelect').addEventListener('change', (e) => {
        loadAgentPortfolio(e.target.value);
    });

    // Market switching
    const usMarketBtn = document.getElementById('usMarketBtn');
    const cnMarketBtn = document.getElementById('cnMarketBtn');
    
    // Granularity switching
    const dailyBtn = document.getElementById('dailyBtn');
    const hourlyBtn = document.getElementById('hourlyBtn');

    if (usMarketBtn) {
        usMarketBtn.addEventListener('click', async () => {
            if (dataLoader.getMarket() !== 'us') {
                dataLoader.setMarket('us');
                updateMarketUI();
                await loadDataAndRefresh();
            }
        });
    }

    if (cnMarketBtn) {
        cnMarketBtn.addEventListener('click', async () => {
            const current = dataLoader.getMarket();
            // If not currently in any CN mode, switch to default CN (Hourly)
            if (current !== 'cn' && current !== 'cn_hour') {
                dataLoader.setMarket('cn_hour');
                updateMarketUI();
                await loadDataAndRefresh();
            }
        });
    }

    if (dailyBtn) {
        dailyBtn.addEventListener('click', async () => {
            if (dataLoader.getMarket() !== 'cn') {
                dataLoader.setMarket('cn');
                updateMarketUI();
                await loadDataAndRefresh();
            }
        });
    }

    if (hourlyBtn) {
        hourlyBtn.addEventListener('click', async () => {
            if (dataLoader.getMarket() !== 'cn_hour') {
                dataLoader.setMarket('cn_hour');
                updateMarketUI();
                await loadDataAndRefresh();
            }
        });
    }

    // Scroll to top button
    const scrollBtn = document.getElementById('scrollToTop');
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 300) {
            scrollBtn.classList.add('visible');
        } else {
            scrollBtn.classList.remove('visible');
        }
    });

    scrollBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

// Loading overlay controls
function showLoading() {
    document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', init);