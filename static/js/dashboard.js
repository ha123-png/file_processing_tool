// dashboard.js
function switchMainTab(tab) {
    document.querySelectorAll('.main-tab').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tab === tab);
    });
    var workbench = document.getElementById('workbenchTab');
    var dashboard = document.getElementById('dashboardTab');
    var isDashboard = tab === 'dashboard';
    _inDashboard = isDashboard;
    if (isDashboard) {
        // 清除旧动画残留（issue_005根因）
        var dashCards = document.querySelectorAll('#dashKpiRow .dash-kpi-card, .dash-card--chart, .dash-card--today');
        dashCards.forEach(function(c) {
            c.style.animation = 'none';
            c.style.opacity = '0';
        });
        dashboard.style.display = 'block';
        workbench.style.display = 'none';
        _syncDashFilter();
        fetchDashboard();
    } else {
        dashboard.style.display = 'none';
        workbench.style.display = 'block';
        // 刷新后重置合成表状态（防止残留）
        _resetMergeState();
        if (_largeTask.groupId) {
            updateLargeTaskDisplay();
        } else if (currentMode === 'extract' && window._currentExtractResult && window._currentExtractResult.file) {
            displayExtractionResult(window._currentExtractResult);
        } else if (currentMode !== 'extract' && currentResult && currentResult.status === 'completed') {
            displayResult(currentResult);
        }
    }
}
function _getDashMode() {
    var sel = document.getElementById('dashFilterSelect').value;
    if (sel === 'auto') {
        return document.body.classList.contains('mode-extract') ? 'extract' : 'desensitize';
    }
    if (sel === 'all') return null;
    return sel;
}
function _syncDashFilter() {
    var sel = document.getElementById('dashFilterSelect');
    if (sel.value === 'auto' || sel.value === '') { return; }
}
function _zeroDashboardDisplay() {
    document.getElementById('dashTotalFiles').textContent = '-';
    document.getElementById('dashSingleValue').textContent = '-';
    document.getElementById('dashTotalRep').textContent = '-';
    document.getElementById('dashTotalItems').textContent = '-';
    document.getElementById('dashAvgDuration').innerHTML = '-<span class="dash-kpi-unit">s</span>';
    document.getElementById('dashErrorRate').innerHTML = '-<span class="dash-kpi-unit">%</span>';
    document.getElementById('dashTodayFiles').textContent = '-';
    document.getElementById('dashTodayRep').textContent = '-';
    document.getElementById('dashTodayItems').textContent = '-';
    document.getElementById('dashTodayAvg').innerHTML = '-<small>s</small>';
    document.getElementById('dashTodayErrors').textContent = '-';
}
function fetchDashboard() {
    if (_dashFetching) return;
    _dashFetching = true;
    var mode = _getDashMode();
    var url = '/api/stats/dashboard' + (mode ? '?mode=' + mode : '');
    var isExtract = _getDashDisplayMode();
    var sel = document.getElementById('dashFilterSelect').value;
    var p1 = fetch(url).then(function(r) { return r.json(); });
    var p2 = sel !== 'extract' ? fetch('/api/stats/dashboard?mode=desensitize').then(function(r) { return r.json(); }) : Promise.resolve(null);
    var p3 = sel !== 'desensitize' ? fetch('/api/stats/dashboard?mode=extract').then(function(r) { return r.json(); }) : Promise.resolve(null);
    Promise.all([p1, p2, p3]).then(function(results) {
        var data = results[0];
        var desenData = results[1];
        var extractData = results[2];
        if (!data || !data.summary) return;
        var desenRepTotal = (desenData && desenData.summary) ? desenData.summary.total_replacements : 0;
        var extractItemTotal = (extractData && extractData.summary) ? extractData.summary.total_replacements : 0;
        var desenTodayRep = (desenData && desenData.today) ? desenData.today.replacements : 0;
        var extractTodayItems = (extractData && extractData.today) ? extractData.today.replacements : 0;
        _renderKpiCards(data.summary, isExtract, desenRepTotal, extractItemTotal);
        _renderTodayPanel(data.today, isExtract, desenTodayRep, extractTodayItems);
        _renderTrendChart(data.trend_30d);
        _animateKpiEntrance();
    }).catch(function() {}).finally(function() {
        _dashFetching = false;
    });
}
function _fetchDashboardSilent() {
    if (_dashFetching) return;
    _dashFetching = true;
    var mode = _getDashMode();
    var url = '/api/stats/dashboard' + (mode ? '?mode=' + mode : '');
    var isExtract = _getDashDisplayMode();
    var sel = document.getElementById('dashFilterSelect').value;
    var p1 = fetch(url).then(function(r) { return r.json(); });
    var p2 = sel !== 'extract' ? fetch('/api/stats/dashboard?mode=desensitize').then(function(r) { return r.json(); }) : Promise.resolve(null);
    var p3 = sel !== 'desensitize' ? fetch('/api/stats/dashboard?mode=extract').then(function(r) { return r.json(); }) : Promise.resolve(null);
    Promise.all([p1, p2, p3]).then(function(results) {
        var data = results[0];
        var desenData = results[1];
        var extractData = results[2];
        if (!data || !data.summary) return;
        var desenRepTotal = (desenData && desenData.summary) ? desenData.summary.total_replacements : 0;
        var extractItemTotal = (extractData && extractData.summary) ? extractData.summary.total_replacements : 0;
        var desenTodayRep = (desenData && desenData.today) ? desenData.today.replacements : 0;
        var extractTodayItems = (extractData && extractData.today) ? extractData.today.replacements : 0;
        _renderKpiCards(data.summary, isExtract, desenRepTotal, extractItemTotal);
        _renderTodayPanel(data.today, isExtract, desenTodayRep, extractTodayItems);
        _renderTrendChart(data.trend_30d);
    }).catch(function() {}).finally(function() {
        _dashFetching = false;
    });
}
function _renderKpiCards(summary, isExtract, desenRepTotal, extractItemTotal) {
    document.getElementById('dashTotalFiles').textContent = summary.total_files;
    var singleEl = document.getElementById('dashKpiSingle');
    var dualEl = document.getElementById('dashKpiDual');
    var singleVal = document.getElementById('dashSingleValue');
    var singleLbl = document.getElementById('dashSingleLabel');
    var sel = document.getElementById('dashFilterSelect').value;
    if (sel === 'all') {
        singleEl.classList.add('kpi-hidden');
        dualEl.classList.remove('kpi-hidden');
        document.getElementById('dashTotalRep').textContent = (desenRepTotal !== undefined ? desenRepTotal : 0).toLocaleString();
        document.getElementById('dashTotalItems').textContent = (extractItemTotal !== undefined ? extractItemTotal : 0).toLocaleString();
    } else if (isExtract) {
        dualEl.classList.add('kpi-hidden');
        singleEl.classList.remove('kpi-hidden');
        singleVal.textContent = (extractItemTotal !== undefined ? extractItemTotal : 0).toLocaleString();
        singleLbl.textContent = '累计明细条';
    } else {
        dualEl.classList.add('kpi-hidden');
        singleEl.classList.remove('kpi-hidden');
        singleVal.textContent = (desenRepTotal !== undefined ? desenRepTotal : 0).toLocaleString();
        singleLbl.textContent = '累计脱敏项';
    }
    document.getElementById('dashAvgDuration').innerHTML = summary.avg_duration + '<span class="dash-kpi-unit">s</span>';
    var ratePct = (summary.error_rate * 100).toFixed(1);
    document.getElementById('dashErrorRate').innerHTML = ratePct + '<span class="dash-kpi-unit">%</span>';
}
function _renderTodayPanel(today, isExtract, desenTodayRep, extractTodayItems) {
    document.getElementById('dashTodayFiles').textContent = today.files;
    var sel = document.getElementById('dashFilterSelect').value;
    var repItem = document.getElementById('dashTodayRepItem');
    var itemsItem = document.getElementById('dashTodayItemsItem');
    if (sel === 'all') {
        itemsItem.classList.remove('collapsed');
        document.getElementById('dashTodayRep').textContent = desenTodayRep.toLocaleString();
        document.getElementById('dashTodayRepLbl').textContent = '脱敏项';
        document.getElementById('dashTodayItems').textContent = extractTodayItems.toLocaleString();
    } else {
        itemsItem.classList.add('collapsed');
        if (isExtract) {
            document.getElementById('dashTodayRep').textContent = today.replacements.toLocaleString();
            document.getElementById('dashTodayRepLbl').textContent = '明细条';
        } else {
            document.getElementById('dashTodayRep').textContent = today.replacements.toLocaleString();
            document.getElementById('dashTodayRepLbl').textContent = '脱敏项';
        }
    }
    document.getElementById('dashTodayAvg').innerHTML = today.avg_duration + '<small>s</small>';
    document.getElementById('dashTodayErrors').textContent = today.errors;
}
function _renderTrendChart(trend) {
    var svg = document.getElementById('dashSvgTrend');
    var polyline = document.getElementById('dashTrendLine');
    var dotsG = document.getElementById('dashTrendDots');
    var xAxis = document.getElementById('dashXAxis');
    var totalEl = document.getElementById('dashTrendTotal');

    if (!trend || trend.length === 0) {
        polyline.setAttribute('points', '');
        dotsG.innerHTML = '';
        xAxis.innerHTML = '<span style="color:var(--gray-400);font-size:12px;padding:8px;">暂无数据</span>';
        totalEl.textContent = '0';
        return;
    }

    var maxCount = 0;
    var totalCount = 0;
    trend.forEach(function(d) { maxCount = Math.max(maxCount, d.count); totalCount += d.count; });
    totalEl.textContent = totalCount;
    if (maxCount === 0) maxCount = 1;

    var w = 600, h = 180, padL = 4, padR = 4, padT = 12, padB = 8;
    var n = trend.length;
    var xStep = (w - padL - padR) / (n > 1 ? n - 1 : 1);
    var yScale = (h - padT - padB) / maxCount;

    var points = [];
    var dots = [];
    trend.forEach(function(d, i) {
        var x = padL + i * xStep;
        var y = h - padB - d.count * yScale;
        points.push(x + ',' + y);
        dots.push('<circle cx="' + x + '" cy="' + y + '" r="4" fill="var(--primary)" stroke="white" stroke-width="2" class="dash-dot" data-date="' + d.date + '" data-count="' + d.count + '"><title>' + d.date + ': ' + d.count + ' 文件</title></circle>');
    });

    polyline.setAttribute('points', points.join(' '));
    dotsG.innerHTML = dots.join('');

    xAxis.innerHTML = '<div style="display:flex;justify-content:space-between;padding:0 6px;">' +
        trend.filter(function(_, i) { return i === 0 || i === trend.length - 1 || i === Math.floor(trend.length / 2); })
            .map(function(d) { return '<span>' + (d.date || '').slice(-5) + '</span>'; }).join('') +
        '</div>';
}
function _animateKpiEntrance() {
    var cards = document.querySelectorAll('#dashKpiRow .dash-kpi-card');
    cards.forEach(function(card, i) {
        card.style.opacity = '0';
        card.style.animation = 'none';
        card.offsetHeight;
        card.style.opacity = '';
        card.style.animation = 'dashCardIn 0.5s ease forwards';
        card.style.animationDelay = (i * 0.08) + 's';
    });
    var chart = document.querySelector('.dash-card--chart');
    var today = document.querySelector('.dash-card--today');
    if (chart) {
        chart.style.opacity = '0';
        chart.style.animation = 'none';
        chart.offsetHeight;
        chart.style.opacity = '';
        chart.style.animation = 'dashCardIn 0.5s ease forwards';
        chart.style.animationDelay = '0.4s';
    }
    if (today) {
        today.style.opacity = '0';
        today.style.animation = 'none';
        today.offsetHeight;
        today.style.opacity = '';
        today.style.animation = 'dashCardIn 0.5s ease forwards';
        today.style.animationDelay = '0.5s';
    }
    var line = document.getElementById('dashTrendLine');
    if (line) {
        var len = line.getTotalLength ? line.getTotalLength() : 600;
        line.style.strokeDasharray = len;
        line.style.strokeDashoffset = len;
        line.style.animation = 'none';
        line.offsetHeight;
        line.style.animation = 'dashLineDraw 1.2s ease forwards';
        line.style.animationDelay = '0.7s';
    }
}
