// Asset Evolution Chart
// Main page visualization

const dataLoader = new DataLoader();
let chartInstance = null;
let allAgentsData = {};
let isLogScale = false;

// Color palette for different agents
const agentColors = [
    '#00d4ff', // Cyan Blue
    '#00ffcc', // Cyan
    '#ff006e', // Hot Pink
    '#ffbe0b', // Yellow
    '#8338ec', // Purple
    '#3a86ff', // Blue
    '#fb5607', // Orange
    '#06ffa5'  // Mint
];

// Cache for loaded SVG images
const iconImageCache = {};

// Function to load SVG as image
function loadIconImage(iconPath) {
    return new Promise((resolve, reject) => {
        if (iconImageCache[iconPath]) {
            resolve(iconImageCache[iconPath]);
            return;
        }
        
        const img = new Image();
        img.onload = () => {
            iconImageCache[iconPath] = img;
            resolve(img);
        };
        img.onerror = reject;
        img.src = iconPath;
    });
}

// Load data and refresh UI
async function loadDataAndRefresh() {
    showLoading();

    try {
        // Load all agents data
        console.log('Loading all agents data...');
        allAgentsData = await dataLoader.loadAllAgentsData();
        console.log('Data loaded:', allAgentsData);

        // Preload all agent icons
        const agentNames = Object.keys(allAgentsData);
        const iconPromises = agentNames.map(agentName => {
            const iconPath = dataLoader.getAgentIcon(agentName);
            return loadIconImage(iconPath).catch(err => {
                console.warn(`Failed to load icon for ${agentName}:`, err);
            });
        });
        await Promise.all(iconPromises);
        console.log('Icons preloaded');

        // Update stats
        updateStats();

        // Create chart
        createChart();

        // Create legend
        createLegend();

        // Update subtitle based on market
        updateMarketSubtitle();

    } catch (error) {
        console.error('Error loading data:', error);
        alert('Failed to load trading data. Please check console for details.');
    } finally {
        hideLoading();
    }
}

// Update market subtitle
function updateMarketSubtitle() {
    const subtitle = document.getElementById('marketSubtitle');
    if (subtitle) {
        if (dataLoader.getMarket() === 'us') {
            subtitle.textContent = 'Track how different AI models perform in Nasdaq-100 stock trading';
        } else {
            subtitle.textContent = 'Track how different AI models perform in SSE 50 A-share stock trading';
        }
    }
}

// Initialize the page
async function init() {
    // Set up event listeners first
    setupEventListeners();
    
    // Load initial data
    await loadDataAndRefresh();
}

// Update statistics cards
function updateStats() {
    const agentNames = Object.keys(allAgentsData);
    const agentCount = agentNames.length;

    // Calculate date range
    let minDate = null;
    let maxDate = null;

    agentNames.forEach(name => {
        const history = allAgentsData[name].assetHistory;
        if (history.length > 0) {
            const firstDate = history[0].date;
            const lastDate = history[history.length - 1].date;

            if (!minDate || firstDate < minDate) minDate = firstDate;
            if (!maxDate || lastDate > maxDate) maxDate = lastDate;
        }
    });

    // Find best performer
    let bestAgent = null;
    let bestReturn = -Infinity;

    agentNames.forEach(name => {
        const returnValue = allAgentsData[name].return;
        if (returnValue > bestReturn) {
            bestReturn = returnValue;
            bestAgent = name;
        }
    });

    // Update DOM
    document.getElementById('agent-count').textContent = agentCount;
    document.getElementById('trading-period').textContent = minDate && maxDate ?
        `${minDate} to ${maxDate}` : 'N/A';
    document.getElementById('best-performer').textContent = bestAgent ?
        dataLoader.getAgentDisplayName(bestAgent) : 'N/A';
    document.getElementById('avg-return').textContent = bestAgent ?
        dataLoader.formatPercent(bestReturn) : 'N/A';
}

// Create the main chart
function createChart() {
    // Destroy existing chart if any
    if (chartInstance) {
        chartInstance.destroy();
        chartInstance = null;
    }

    const ctx = document.getElementById('assetChart').getContext('2d');

    // Collect all unique dates and sort them
    const allDates = new Set();
    Object.keys(allAgentsData).forEach(agentName => {
        allAgentsData[agentName].assetHistory.forEach(h => allDates.add(h.date));
    });
    const sortedDates = Array.from(allDates).sort();

    const datasets = Object.keys(allAgentsData).map((agentName, index) => {
        const data = allAgentsData[agentName];
        let color, borderWidth, borderDash;
        
        // Special styling for benchmark (QQQ or SSE 50)
        const isBenchmark = agentName === 'QQQ' || agentName === 'SSE 50';
        if (isBenchmark) {
            color = dataLoader.getAgentBrandColor(agentName) || '#ff6b00';
            borderWidth = 2;
            borderDash = [5, 5]; // Dashed line for benchmark
        } else {
            color = agentColors[index % agentColors.length];
            borderWidth = 3;
            borderDash = [];
        }

        // Create data points for all dates, filling missing dates with null
        const chartData = sortedDates.map(date => {
            const historyEntry = data.assetHistory.find(h => h.date === date);
            return {
                x: date,
                y: historyEntry ? historyEntry.value : null
            };
        });

        return {
            label: dataLoader.getAgentDisplayName(agentName),
            data: chartData,
            borderColor: color,
            backgroundColor: agentName === 'QQQ' ? 'transparent' : createGradient(ctx, color),
            borderWidth: borderWidth,
            borderDash: borderDash,
            tension: 0.42, // Smooth curves for financial charts
            pointRadius: 0,
            pointHoverRadius: 7,
            pointHoverBackgroundColor: color,
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 3,
            fill: agentName !== 'QQQ', // No fill for QQQ benchmark
            agentName: agentName,
            agentIcon: dataLoader.getAgentIcon(agentName),
            cubicInterpolationMode: 'monotone' // Smooth, monotonic interpolation
        };
    });

    // Create gradient for area fills
    function createGradient(ctx, color) {
        // Parse color and create gradient
        const gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, color + '30'); // 30% opacity at top
        gradient.addColorStop(0.5, color + '15'); // 15% opacity at middle
        gradient.addColorStop(1, color + '05'); // 5% opacity at bottom
        return gradient;
    }

    // Custom plugin to draw icons on chart lines
    const iconPlugin = {
        id: 'iconLabels',
        afterDatasetsDraw: (chart) => {
            const ctx = chart.ctx;

            chart.data.datasets.forEach((dataset, datasetIndex) => {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (!meta.hidden && dataset.data.length > 0) {
                    // Get the last point
                    const lastPoint = meta.data[meta.data.length - 1];

                    if (lastPoint) {
                        const x = lastPoint.x;
                        const y = lastPoint.y;

                        ctx.save();

                        // Draw background circle with glow
                        const iconSize = 30;

                        // Outer glow
                        ctx.shadowColor = dataset.borderColor;
                        ctx.shadowBlur = 15;
                        ctx.fillStyle = dataset.borderColor;
                        ctx.beginPath();
                        ctx.arc(x + 22, y, iconSize / 2, 0, Math.PI * 2);
                        ctx.fill();

                        // Reset shadow
                        ctx.shadowBlur = 0;

                        // Draw icon image if loaded
                        if (iconImageCache[dataset.agentIcon]) {
                            const img = iconImageCache[dataset.agentIcon];
                            const imgSize = iconSize * 0.6; // Icon slightly smaller than circle
                            ctx.drawImage(img, x + 22 - imgSize/2, y - imgSize/2, imgSize, imgSize);
                        }

                        ctx.restore();
                    }
                }
            });
        }
    };

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 200,
            layout: {
                padding: {
                    right: 50,
                    top: 10,
                    bottom: 10
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            elements: {
                line: {
                    borderJoinStyle: 'round',
                    borderCapStyle: 'round'
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 34, 56, 0.95)',
                    titleColor: '#00d4ff',
                    bodyColor: '#fff',
                    borderColor: '#2d3748',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = dataLoader.formatCurrency(context.parsed.y);
                            // Tooltips don't support images, so just show label and value
                            return `${label}: ${value}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'category',
                    labels: sortedDates,
                    grid: {
                        color: 'rgba(45, 55, 72, 0.3)',
                        drawBorder: false,
                        lineWidth: 1
                    },
                    ticks: {
                        color: '#a0aec0',
                        maxRotation: 45,
                        minRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 10,
                        font: {
                            size: 11
                        }
                    }
                },
                y: {
                    type: isLogScale ? 'logarithmic' : 'linear',
                    grid: {
                        color: 'rgba(45, 55, 72, 0.3)',
                        drawBorder: false,
                        lineWidth: 1
                    },
                    ticks: {
                        color: '#a0aec0',
                        callback: function(value) {
                            return dataLoader.formatCurrency(value);
                        },
                        font: {
                            size: 11
                        }
                    }
                }
            }
        },
        plugins: [iconPlugin]
    });
}

// Create legend
function createLegend() {
    const legendContainer = document.getElementById('agentLegend');
    legendContainer.innerHTML = '';

    Object.keys(allAgentsData).forEach((agentName, index) => {
        const data = allAgentsData[agentName];
        let color, borderStyle;
        
        // Special styling for benchmark (QQQ or SSE 50)
        const isBenchmark = agentName === 'QQQ' || agentName === 'SSE 50';
        if (isBenchmark) {
            color = dataLoader.getAgentBrandColor(agentName) || '#ff6b00';
            borderStyle = 'dashed';
        } else {
            color = agentColors[index % agentColors.length];
            borderStyle = 'solid';
        }
        
        const returnValue = data.return;
        const returnClass = returnValue >= 0 ? 'positive' : 'negative';
        const iconPath = dataLoader.getAgentIcon(agentName);
        const brandColor = dataLoader.getAgentBrandColor(agentName);

        const legendItem = document.createElement('div');
        legendItem.className = 'legend-item';
        legendItem.innerHTML = `
            <div class="legend-icon" ${brandColor ? `style="background: ${brandColor}20;"` : ''}>
                <img src="${iconPath}" alt="${agentName}" class="legend-icon-img" />
            </div>
            <div class="legend-color" style="background: ${color}; border-style: ${borderStyle};"></div>
            <div class="legend-info">
                <div class="legend-name">${dataLoader.getAgentDisplayName(agentName)}</div>
                <div class="legend-return ${returnClass}">${dataLoader.formatPercent(returnValue)}</div>
            </div>
        `;

        legendContainer.appendChild(legendItem);
    });
}

// Toggle between linear and log scale
function toggleScale() {
    isLogScale = !isLogScale;

    const button = document.getElementById('toggle-log');
    button.textContent = isLogScale ? 'Log Scale' : 'Linear Scale';

    // Update chart
    if (chartInstance) {
        chartInstance.destroy();
    }
    createChart();
}

// Export chart data as CSV
function exportData() {
    let csv = 'Date,';

    // Header row with agent names
    const agentNames = Object.keys(allAgentsData);
    csv += agentNames.map(name => dataLoader.getAgentDisplayName(name)).join(',') + '\n';

    // Collect all unique dates
    const allDates = new Set();
    agentNames.forEach(name => {
        allAgentsData[name].assetHistory.forEach(h => allDates.add(h.date));
    });

    // Sort dates
    const sortedDates = Array.from(allDates).sort();

    // Data rows
    sortedDates.forEach(date => {
        const row = [date];
        agentNames.forEach(name => {
            const history = allAgentsData[name].assetHistory;
            const entry = history.find(h => h.date === date);
            row.push(entry ? entry.value.toFixed(2) : '');
        });
        csv += row.join(',') + '\n';
    });

    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'aitrader_asset_evolution.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('toggle-log').addEventListener('click', toggleScale);
    document.getElementById('export-chart').addEventListener('click', exportData);

    // Market selector buttons
    const usMarketBtn = document.getElementById('usMarketBtn');
    const cnMarketBtn = document.getElementById('cnMarketBtn');
    
    usMarketBtn.addEventListener('click', async () => {
        if (dataLoader.getMarket() === 'us') return; // Already on US market
        
        // Switch to US market
        usMarketBtn.classList.add('active');
        cnMarketBtn.classList.remove('active');
        dataLoader.setMarket('us');
        
        // Reload data
        await loadDataAndRefresh();
    });
    
    cnMarketBtn.addEventListener('click', async () => {
        if (dataLoader.getMarket() === 'cn') return; // Already on CN market
        
        // Switch to CN market
        cnMarketBtn.classList.add('active');
        usMarketBtn.classList.remove('active');
        dataLoader.setMarket('cn');
        
        // Reload data
        await loadDataAndRefresh();
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

    // Window resize handler for chart responsiveness
    let resizeTimeout;
    const handleResize = () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (chartInstance) {
                console.log('Resizing chart...'); // Debug log
                chartInstance.resize();
                chartInstance.update('none'); // Force update without animation
            }
        }, 100); // Faster response
    };

    window.addEventListener('resize', handleResize);

    // Also handle orientation change for mobile
    window.addEventListener('orientationchange', handleResize);
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
