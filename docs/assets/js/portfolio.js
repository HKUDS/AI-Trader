// Portfolio Analysis Page
// Detailed view of individual agent portfolios

const dataLoader = new DataLoader();
let allAgentsData = {};
let currentAgent = null;
let allocationChart = null;

// Initialize the page
async function init() {
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

        // Set up event listeners
        setupEventListeners();

    } catch (error) {
        console.error('Error initializing page:', error);
        alert('Failed to load portfolio data. Please check console for details.');
    } finally {
        hideLoading();
    }
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
        await updateTradeHistory(agentName);

        // Update realized PnL table
        await updateRealizedPnLTable(agentName);

    } catch (error) {
        console.error('Error loading portfolio:', error);
    } finally {
        hideLoading();
    }
}

// Update performance metrics
async function updateMetrics(data) {
    const totalAsset = data.currentValue;
    const totalReturn = data.return;
    const latestPosition = data.positions && data.positions.length > 0 ? data.positions[data.positions.length - 1] : null;
    const cashPosition = latestPosition && latestPosition.positions ? latestPosition.positions.CASH || 0 : 0;
    const totalTrades = data.positions ? data.positions.filter(p => p.this_action && p.this_action.action !== 'no_trade').length : 0;

    // Calculate realized and unrealized PnL
    const realizedData = await dataLoader.calculateRealizedPnL(currentAgent);
    const unrealizedData = await dataLoader.calculateUnrealizedPnL(currentAgent);

    document.getElementById('totalAsset').textContent = dataLoader.formatCurrency(totalAsset);
    document.getElementById('totalReturn').textContent = dataLoader.formatPercent(totalReturn);
    document.getElementById('totalReturn').className = `metric-value ${totalReturn >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('totalUnrealizedPnL').textContent = dataLoader.formatCurrency(unrealizedData.totalUnrealizedPnL);
    document.getElementById('totalUnrealizedPnL').className = `metric-value ${unrealizedData.totalUnrealizedPnL >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('totalRealizedPnL').textContent = dataLoader.formatCurrency(realizedData.totalRealizedPnL);
    document.getElementById('totalRealizedPnL').className = `metric-value ${realizedData.totalRealizedPnL >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('cashPosition').textContent = dataLoader.formatCurrency(cashPosition);
    document.getElementById('totalTrades').textContent = totalTrades;
}

// Update holdings table
async function updateHoldingsTable(agentName) {
    const tableBody = document.getElementById('holdingsTableBody');
    tableBody.innerHTML = '';

    const data = allAgentsData[agentName];
    if (!data || !data.assetHistory || data.assetHistory.length === 0) {
        return;
    }

    const totalValue = data.currentValue;

    // Get unrealized PnL data which includes all the information we need
    const unrealizedData = await dataLoader.calculateUnrealizedPnL(agentName);
    const holdings = unrealizedData.holdings;

    if (holdings.length === 0) {
        const latestPosition = data.positions[data.positions.length - 1];
        const cashPosition = latestPosition && latestPosition.positions ? latestPosition.positions.CASH || 0 : 0;
        
        // Only show cash row if there's cash
        if (cashPosition > 0) {
            const cashWeight = (cashPosition / totalValue * 100).toFixed(2);
            const cashRow = document.createElement('tr');
            cashRow.innerHTML = `
                <td class="symbol">CASH</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td>${dataLoader.formatCurrency(cashPosition)}</td>
                <td>-</td>
                <td>${cashWeight}%</td>
            `;
            tableBody.appendChild(cashRow);
        } else {
            const noDataRow = document.createElement('tr');
            noDataRow.innerHTML = `
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                    No holdings data available
                </td>
            `;
            tableBody.appendChild(noDataRow);
        }
        return;
    }

    // Sort by market value (descending)
    holdings.sort((a, b) => b.marketValue - a.marketValue);

    // Create table rows
    holdings.forEach(holding => {
        const weight = (holding.marketValue / totalValue * 100).toFixed(2);
        const pnlClass = holding.unrealizedPnL >= 0 ? 'positive' : 'negative';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="symbol">${holding.symbol}</td>
            <td>${holding.shares}</td>
            <td>${dataLoader.formatCurrency(holding.avgCost)}</td>
            <td>${dataLoader.formatCurrency(holding.currentPrice)}</td>
            <td>${dataLoader.formatCurrency(holding.marketValue)}</td>
            <td class="${pnlClass}">${dataLoader.formatCurrency(holding.unrealizedPnL)}</td>
            <td>${weight}%</td>
        `;
        tableBody.appendChild(row);
    });

    // Add cash row
    const latestPosition = data.positions[data.positions.length - 1];
    const cashPosition = latestPosition && latestPosition.positions ? latestPosition.positions.CASH || 0 : 0;
    
    if (cashPosition > 0) {
        const cashWeight = (cashPosition / totalValue * 100).toFixed(2);
        const cashRow = document.createElement('tr');
        cashRow.innerHTML = `
            <td class="symbol">CASH</td>
            <td>-</td>
            <td>-</td>
            <td>-</td>
            <td>${dataLoader.formatCurrency(cashPosition)}</td>
            <td>-</td>
            <td>${cashWeight}%</td>
        `;
        tableBody.appendChild(cashRow);
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
async function updateTradeHistory(agentName) {
    const timeline = document.getElementById('tradeTimeline');
    timeline.innerHTML = '';

    const data = allAgentsData[agentName];
    if (!data || !data.positions) {
        timeline.innerHTML = '<p style="color: var(--text-muted);">No trade history available.</p>';
        return;
    }

    // Get all trades with actions
    const tradesWithActions = data.positions.filter(p => p.this_action && p.this_action.action !== 'no_trade');
    
    if (tradesWithActions.length === 0) {
        timeline.innerHTML = '<p style="color: var(--text-muted);">No trade history available.</p>';
        return;
    }

    // Get realized PnL data for sell trades and calculate cost basis
    const costBasis = {}; // Track cost basis for percentage calculation
    const realizedTradesMap = {};
    
    // Build cost basis and realized trades map
    for (const position of data.positions) {
        if (!position.this_action || position.this_action.action === 'no_trade') continue;
        
        const { action, symbol, amount } = position.this_action;
        const date = position.date;
        const price = await dataLoader.getOpeningPrice(symbol, date);
        
        if (!price) continue;
        
        if (action === 'buy') {
            if (!costBasis[symbol]) costBasis[symbol] = [];
            costBasis[symbol].push({ quantity: amount, price: price });
        } else if (action === 'sell') {
            if (!costBasis[symbol] || costBasis[symbol].length === 0) continue;
            
            let remainingToSell = amount;
            let totalCost = 0;
            let soldQuantity = 0;
            
            // Calculate average cost basis for sold shares (use deep copy to avoid mutation)
            const tempCostBasis = JSON.parse(JSON.stringify(costBasis[symbol]));
            while (remainingToSell > 0 && tempCostBasis.length > 0) {
                const lot = tempCostBasis[0];
                const quantityToSell = Math.min(remainingToSell, lot.quantity);
                totalCost += lot.price * quantityToSell;
                soldQuantity += quantityToSell;
                lot.quantity -= quantityToSell;
                remainingToSell -= quantityToSell;
                if (lot.quantity <= 0) tempCostBasis.shift();
            }
            
            const avgCost = soldQuantity > 0 ? totalCost / soldQuantity : 0;
            const pnl = (price - avgCost) * amount;
            const pnlPercent = avgCost > 0 ? ((price - avgCost) / avgCost * 100) : 0;
            
            const key = `${date}-${symbol}-${amount}`;
            realizedTradesMap[key] = { pnl, pnlPercent, avgCost };
            
            // Update actual cost basis
            remainingToSell = amount;
            while (remainingToSell > 0 && costBasis[symbol].length > 0) {
                const lot = costBasis[symbol][0];
                const quantityToSell = Math.min(remainingToSell, lot.quantity);
                lot.quantity -= quantityToSell;
                remainingToSell -= quantityToSell;
                if (lot.quantity <= 0) costBasis[symbol].shift();
            }
        }
    }

    // Show latest 20 trades (reversed to show most recent first)
    const recentTrades = tradesWithActions.slice(-20).reverse();

    for (const position of recentTrades) {
        const trade = position.this_action;
        const date = position.date;
        
        // Get the opening price for this trade
        const price = await dataLoader.getOpeningPrice(trade.symbol, date);
        
        const tradeItem = document.createElement('div');
        tradeItem.className = 'trade-item';

        if (trade.action === 'buy') {
            tradeItem.innerHTML = `
                <div class="trade-icon buy">📈</div>
                <div class="trade-details">
                    <div class="trade-action">
                        <span><strong>Bought ${trade.amount}</strong> shares of <strong>${trade.symbol}</strong>
                        ${price ? ` @ ${dataLoader.formatCurrency(price)}` : ''}</span>
                    </div>
                    <div class="trade-meta">
                        ${date}
                        ${price ? ` • Total: ${dataLoader.formatCurrency(price * trade.amount)}` : ''}
                    </div>
                </div>
            `;
        } else if (trade.action === 'sell') {
            // Look up realized PnL for this trade
            const key = `${date}-${trade.symbol}-${trade.amount}`;
            const realizedTrade = realizedTradesMap[key];
            const pnl = realizedTrade ? realizedTrade.pnl : null;
            const pnlPercent = realizedTrade ? realizedTrade.pnlPercent : null;
            const pnlClass = pnl !== null ? (pnl >= 0 ? 'positive' : 'negative') : '';
            const pnlSign = pnl !== null && pnl >= 0 ? '+' : '';
            const percentSign = pnlPercent !== null && pnlPercent >= 0 ? '+' : '';
            
            tradeItem.innerHTML = `
                <div class="trade-icon sell">📉</div>
                <div class="trade-details">
                    <div class="trade-action">
                        <span><strong>Sold ${trade.amount}</strong> shares of <strong>${trade.symbol}</strong>
                        ${price ? ` @ ${dataLoader.formatCurrency(price)}` : ''}</span>
                        ${pnl !== null ? `
                            <div class="trade-pnl ${pnlClass}">
                                <span class="trade-pnl-amount">${pnlSign}${dataLoader.formatCurrency(pnl)}</span>
                                <span class="trade-pnl-percent">(${percentSign}${pnlPercent.toFixed(2)}%)</span>
                            </div>
                        ` : ''}
                    </div>
                    <div class="trade-meta">
                        ${date}
                        ${price ? ` • Total: ${dataLoader.formatCurrency(price * trade.amount)}` : ''}
                    </div>
                </div>
            `;
        }

        timeline.appendChild(tradeItem);
    }
}

// Update realized PnL table (not needed anymore but keeping for compatibility)
async function updateRealizedPnLTable(agentName) {
    // This function is no longer used as we integrated the info into trade history
    // Keeping it to avoid breaking the code flow
    return;
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('agentSelect').addEventListener('change', (e) => {
        loadAgentPortfolio(e.target.value);
    });

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
