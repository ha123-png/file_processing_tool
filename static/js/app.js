// app.js
function _scheduleMergeAutoSave() {
    if (_mergeAutoSaveTimer) clearTimeout(_mergeAutoSaveTimer);
    _mergeAutoSaveTimer = setTimeout(function() {
        _flushDirtyCells();
    }, 600);
}
function saveDefaultPanels() {
    _defaultEmptyPanels.original = originalPanel.innerHTML;
    _defaultEmptyPanels.desensitized = desensitizedPanel.innerHTML;
    _defaultEmptyPanels.replacements = replacementsPanel.innerHTML;
    _defaultEmptyPanels.extract = document.querySelector('#extractPanel .result-empty') ? document.querySelector('#extractPanel .result-empty').outerHTML : '';
    _defaultEmptyPanels.merge = document.querySelector('#mergePanel .result-empty') ? document.querySelector('#mergePanel .result-empty').outerHTML : '';
}
function saveExtractionHistory(data) {
    var exists = extractionHistory.some(function(h) {
        return h.file === data.file && h.timestamp === data.timestamp;
    });
    if (!exists) {
        extractionHistory.unshift(data);
    }
    if (extractionHistory.length > 100) extractionHistory.pop();
}
function resetExtractCompare() {
    var wrap = document.getElementById('extractWrapper');
    var left = document.getElementById('extractCompareLeft');
    if (wrap) {
        wrap.classList.remove('extract-wrap--compare');
        var handle = wrap.querySelector('.extract-resize-handle');
        if (handle) handle.remove();
    }
    if (left) {
        left.innerHTML = '';
        left.style.width = '';
    }
    var btn = document.getElementById('extractCompareBtn');
    if (btn) btn.textContent = '对照查看';
}
function ellipsKeepEnd(str, maxLen) {
    if (!str || str.length <= maxLen) return str || '';
    return '\u2026' + str.slice(str.length - maxLen + 1);
}
function updateHeaderTimerDisplay() {
    if (!headerTimer || !headerTimerTime || !headerTimerFile) return;
    var sec = processingSeconds;
    var name = processingFileName || '';
    headerTimerTime.textContent = sec + 's';
    headerTimerFile.textContent = name ? ellipsKeepEnd('[' + name + ']', 34) : '';
}
function startProcessingTimer(filename) {
    stopProcessingTimer();
    processingFileName = filename;
    processingSeconds = 0;
    if (headerTimer) {
        headerTimer.classList.add('visible', 'running');
        updateHeaderTimerDisplay();
    }
    processingTimer = setInterval(function() {
        processingSeconds++;
        updateHeaderTimerDisplay();
    }, 1000);
}
function stopProcessingTimer() {
    if (processingTimer) {
        clearInterval(processingTimer);
        processingTimer = null;
    }
    if (headerTimer) {
        headerTimer.classList.remove('visible', 'running');
    }
    if (headerTimerFile) headerTimerFile.textContent = '';
    if (headerTimerTime) headerTimerTime.textContent = '';
    processingSeconds = 0;
    processingFileName = '';
}
function setMode(mode) {
    if (mode === currentMode) return;
    _saveModePanelCache();
    currentMode = mode;
    var isExtract = mode === 'extract';
    document.body.classList.toggle('mode-extract', isExtract);
    modeDesensitize.classList.toggle('active', !isExtract);
    modeExtract.classList.toggle('active', isExtract);
    headerModeLabel.textContent = isExtract ? '数据提取' : '文件脱敏';
    headerSubtitle.textContent = isExtract ? '拖拽文件 · 自动识别 · 结构化提取' : '拖拽文件 · 自动识别 · 双重脱敏';
    resultTitle.innerHTML = isExtract ? '提取结果' : '脱敏结果';
    tabOriginal.textContent = isExtract ? '原文件' : '原文预览';
    tabDesensitized.style.display = isExtract ? 'none' : '';
    tabReplacements.style.display = isExtract ? 'none' : '';
    var extractTab = document.querySelector('.result-tab[data-tab="extract"]');
    if (extractTab) extractTab.style.display = isExtract ? '' : 'none';
    if (mergeTab) mergeTab.style.display = isExtract ? '' : 'none';
    resetExtractCompare();

    if (_modePanelCache[mode]) {
        _restoreModePanelCache();
        if (!isExtract) {
            window._currentExtractResult = null;
        }
        if (isExtract) { switchTab('extract'); loadMergePreview(); }
        else switchTab('original');
        var cached = _resultByMode[mode];
        if (cached && cached.status === 'completed') {
            if (!isExtract) {
                displayResult(cached);
            } else {
                displayExtractionResult(cached);
            }
        }
    } else {
        _desensitizeOriginalContent = '';
        _desensitizePanels = {};
        _extractResultContent = '';
        _extractOriginalContent = '';
        currentResult = null;
        window._currentExtractResult = null;
        _currentDesensitizeData = null;
        resultMeta.innerHTML = '';
        resultActions.innerHTML = '';

        if (!isExtract) {
        extractPanel.innerHTML = _defaultEmptyPanels.extract;
        mergePanel.innerHTML = _defaultEmptyPanels.merge;
        _extractResultContent = '';
        _extractOriginalContent = '';
        window._currentExtractResult = null;

        originalPanel.innerHTML = _desensitizeOriginalContent && _desensitizeOriginalContent.indexOf('result-empty') === -1
            ? _desensitizeOriginalContent : _defaultEmptyPanels.original;
        desensitizedPanel.innerHTML = _defaultEmptyPanels.desensitized;
        replacementsPanel.innerHTML = _defaultEmptyPanels.replacements;
        if (_desensitizePanels.desensitizedText) {
            desensitizedPanel.innerHTML = '';
            desensitizedPanel.style.position = '';
            var _ta = document.createElement('textarea');
            _ta.value = _desensitizePanels.desensitizedText;
            _ta.style.cssText = 'width:100%;height:100%;margin:0;padding:16px;border:none;outline:none;resize:none;font-size:14px;line-height:1.7;font-family:"JetBrains Mono","Fira Code","Consolas",monospace;color:var(--gray-800);background:transparent;';
            desensitizedPanel.appendChild(_ta);
            replacementsPanel.innerHTML = _desensitizePanels.replacements || _defaultEmptyPanels.replacements;
        }
        switchTab('original');
    } else {
        originalPanel.innerHTML = '';
        desensitizedPanel.innerHTML = _defaultEmptyPanels.desensitized;
        replacementsPanel.innerHTML = _defaultEmptyPanels.replacements;
        _desensitizeOriginalContent = '';
        _desensitizePanels = {desensitized: '', desensitizedText: '', replacements: ''};

        if (_extractResultContent) {
            extractPanel.innerHTML = _extractResultContent;
            resetExtractCompare();
            switchTab('extract');
        } else if (window._currentExtractResult) {
            displayExtractionResult(window._currentExtractResult);
        } else {
            extractPanel.innerHTML = _defaultEmptyPanels.extract;
            switchTab('original');
        }
        loadMergePreview();
    }
    }
    if (_largeTask.isActive()) {
        var activeTaskParent = _queueItems[_largeTask.groupId];
        if (activeTaskParent && activeTaskParent.mode === mode) {
            updateLargeTaskDisplay();
        }
    }

    if (!_modePanelCache[mode]) {

    if (_inDashboard) {
        _zeroDashboardDisplay();
        fetchDashboard();
    } else {
        var cachedResult = _resultByMode[mode];
        if (cachedResult && cachedResult.status === 'completed') {
            if (isExtract) {
                displayExtractionResult(cachedResult);
            } else {
                displayResult(cachedResult);
            }
        }
    }
    }

    fetch('/api/mode', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode:mode})})
    .then(function(r){return r.json();})
    .then(function(d){addLog('info','已切换到'+(isExtract?'提取':'脱敏')+'模式');})
    .catch(function(e){addLog('error','模式切换失败');});
    var cb = document.getElementById('queueCheckAll');
    if (cb) cb.checked = false;
    if (_inDashboard) {
        _zeroDashboardDisplay();
        fetchDashboard();
    }
    renderQueueList();
}
function connectSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource('/api/events');

    eventSource.addEventListener('connected', function(e) {
        const data = JSON.parse(e.data);
        updateStatus(data);
    });

    eventSource.addEventListener('status', function(e) {
        const data = JSON.parse(e.data);
        updateStatus(data);
    });

    eventSource.addEventListener('log', function(e) {
        const data = JSON.parse(e.data);
        addLog(data.level, data.message);
        if (data.message && (data.message.indexOf('开始处理') >= 0 || data.message.indexOf('开始提取') >= 0)) {
            var match = data.message.match(/\[(.+?)\]/);
            if (match) {
                startProcessingTimer(match[1]);
                var hasProcessing = false;
                for (var k in _queueItems) {
                    if (_queueItems[k].status === 'processing') { hasProcessing = true; break; }
                }
                for (var k in _queueItems) {
                    if (_queueItems[k].orig_name === match[1] && (_queueItems[k].status === 'paused' || _queueItems[k].status === 'waiting')) {
                        _queueItems[k].status = hasProcessing ? 'waiting' : 'processing';
                        _queueItems[k].message = hasProcessing ? '等待中' : '';
                        renderQueueList();
                        break;
                    }
                }
            }
        }
    });

    eventSource.addEventListener('result', function(e) {
        const data = JSON.parse(e.data);
        handleResult(data);
    });

    eventSource.addEventListener('error', function(e) {
        try {
            const data = JSON.parse(e.data);
            addLog('error', data.message || '未知错误');
            if (data.queue_id) updateQueue(data.queue_id, 'error', data.message);
        } catch(err) {}
    });

    eventSource.onerror = function() {
        // 不清空队列，只重连
        // 队列状态由后端task_store维护，SSE断开不影响前端队列显示
        setTimeout(connectSSE, 3000);
    };
}
function updateStatus(data) {
    const qsize = data.queue_size || 0;
    const processing = data.processing || false;
    const paused = data.paused || false;
    var wasLocked = _processingLocked;
    _processingLocked = processing;
    _queueSize = qsize;
    document.body.classList.toggle('processing-readonly', _processingLocked);
    _toggleResultButtons(!_processingLocked || paused);
    document.body.classList.toggle('queue-paused', paused);
    if (wasLocked !== _processingLocked && window._currentExtractResult && currentMode === 'extract') {
        displayExtractionResult(window._currentExtractResult);
    }
    if (paused) {
        togglePauseBtn.style.display = '';
        togglePauseBtn.className = 'control-btn resume-btn';
        togglePauseBtn.textContent = '▶';
        togglePauseBtn.title = '继续（恢复队列运行）';
        statusDot.className = 'dot paused';
        statusBadge.className = 'status-badge paused';
        statusBadge.textContent = '已暂停';
    } else if (processing) {
        statusDot.className = 'dot processing';
        statusBadge.className = 'status-badge running';
        statusBadge.textContent = '处理中';
        togglePauseBtn.style.display = '';
        togglePauseBtn.className = 'control-btn pause-btn';
        togglePauseBtn.textContent = '';
        togglePauseBtn.title = '暂停（中断当前任务并冻结队列）';
        var hasProcessing = false;
        for (var k in _queueItems) {
            if (_queueItems[k].status === 'processing') { hasProcessing = true; break; }
        }
        if (!hasProcessing) {
            for (var n2 in _queueItems) {
                if (_queueItems[n2].status === 'paused') {
                    _queueItems[n2].status = 'processing';
                    _queueItems[n2].message = '';
                    break;
                }
            }
            for (var k in _queueItems) {
                if (_queueItems[k].status === 'processing') { hasProcessing = true; break; }
            }
            if (!hasProcessing && !wasLocked) {
                for (var n4 in _queueItems) {
                    if (_queueItems[n4].status === 'pending' || _queueItems[n4].status === 'waiting') {
                        _queueItems[n4].status = 'processing';
                        _queueItems[n4].message = '';
                        break;
                    }
                }
            }
        }
        if (_queueTab !== 'processing') switchQueueTab('processing');
        renderQueueList();
    } else {
        var hasActive = false;
        for (var n3 in _queueItems) {
            var s3 = _queueItems[n3].status;
            if (s3 === 'pending' || s3 === 'waiting' || s3 === 'processing' || s3 === 'paused') {
                hasActive = true;
                break;
            }
        }
        if (hasActive) {
            renderQueueList();
            return;
        }
        document.body.classList.remove('queue-paused');
        statusDot.className = 'dot';
        statusBadge.className = 'status-badge idle';
        statusBadge.textContent = '闲置中';
        togglePauseBtn.style.display = 'none';
        if (!processing) { stopProcessingTimer(); _currentTaskId = ''; }
    }
    renderQueueList();
}
function _saveModePanelCache() {
    _modePanelCache[currentMode] = {
        resultMeta: resultMeta.innerHTML,
        resultActions: resultActions.innerHTML,
        originalPanel: originalPanel.innerHTML,
        desensitizedPanel: desensitizedPanel.innerHTML,
        replacementsPanel: replacementsPanel.innerHTML,
        extractPanel: extractPanel.innerHTML,
        mergePanel: mergePanel.innerHTML,
        currentResult: currentResult,
        resultByMode: _resultByMode,
        currentExtractResult: window._currentExtractResult,
        desensitizeOriginalContent: _desensitizeOriginalContent,
        desensitizePanels: {desensitized: _desensitizePanels.desensitized || '', desensitizedText: _desensitizePanels.desensitizedText || '', replacements: _desensitizePanels.replacements || ''},
        extractResultContent: _extractResultContent,
        extractOriginalContent: _extractOriginalContent
    };
}
function _restoreModePanelCache() {
    var p = _modePanelCache[currentMode];
    if (!p) {
        resultMeta.innerHTML = '';
        resultActions.innerHTML = '';
        originalPanel.innerHTML = '';
        desensitizedPanel.innerHTML = '';
        replacementsPanel.innerHTML = '';
        extractPanel.innerHTML = '';
        mergePanel.innerHTML = '';
        _desensitizeOriginalContent = '';
        _desensitizePanels = {};
        _extractResultContent = '';
        _extractOriginalContent = '';
        currentResult = null;
        window._currentExtractResult = null;
        _currentDesensitizeData = null;
        return false;
    }
    resultMeta.innerHTML = p.resultMeta || '';
    resultActions.innerHTML = p.resultActions || '';
    originalPanel.innerHTML = p.originalPanel || '';
    desensitizedPanel.innerHTML = p.desensitizedPanel || '';
    replacementsPanel.innerHTML = p.replacementsPanel || '';
    extractPanel.innerHTML = p.extractPanel || '';
    mergePanel.innerHTML = p.mergePanel || '';
    // 不恢复 currentResult/_resultByMode/currentExtractResult
    // 这些数据始终以 handleResult 更新的为准，避免缓存覆盖新数据
    _desensitizeOriginalContent = p.desensitizeOriginalContent || '';
    _desensitizePanels = p.desensitizePanels || {};
    _extractResultContent = p.extractResultContent || '';
    _extractOriginalContent = p.extractOriginalContent || '';
    return true;
}
function _toggleResultButtons(visible) {
    var ra = document.getElementById('resultActions');
    if (!ra) return;
    if (visible) {
        if (_savedResultActions && !ra.innerHTML.trim()) {
            ra.innerHTML = _savedResultActions;
        }
        _savedResultActions = '';
        ra.style.display = '';
    } else {
        if (!_savedResultActions) {
            _savedResultActions = ra.innerHTML;
            ra.innerHTML = '';
        }
        ra.style.display = 'none';
    }
}
function _updateParentProgress(parentId, childTaskId, chunkIndex) {
    if (!parentId || !_queueItems[parentId]) return;
    if (_largeTask.groupId) updateLargeTaskDisplay();
}
function addLog(level, message) {
    const now = new Date();
    const time = now.toTimeString().slice(0, 8);
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-level ${level}">${level.toUpperCase()}</span>
        <span class="log-msg">${escapeHtml(message)}</span>
    `;
    logPanel.appendChild(entry);
    logPanel.scrollTop = logPanel.scrollHeight;
    logCount++;
    if (logCount > 200) {
        const toRemove = logPanel.children.length - 200;
        for (let i = 0; i < toRemove && logPanel.children.length > 200; i++) {
            logPanel.removeChild(logPanel.children[0]);
        }
    }
}
function clearLogs() {
    while (logPanel.children.length > 1) {
        logPanel.removeChild(logPanel.lastChild);
    }
    logCount = 0;
    addLog('info', '日志已清空');
}
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
function getFileType(name) {
    var ext = name.split('.').pop().toUpperCase();
    return ext.length <= 4 ? ext : 'FILE';
}
function enqueueWithId(tid, name, status, message, mode, totalChunks) {
    _queueItems[tid] = {name: name, orig_name: name, status: status, message: message || getStatusText(status), type: getFileType(name), task_id: tid, mode: mode || currentMode};
    if (totalChunks) { _queueItems[tid].total_chunks = totalChunks; _queueItems[tid].is_large = true; }
    if (_pendingUpdates[tid]) {
        _queueItems[tid].status = _pendingUpdates[tid].status;
        _queueItems[tid].message = _pendingUpdates[tid].message || getStatusText(_pendingUpdates[tid].status);
        delete _pendingUpdates[tid];
    }
    if (_queueTab !== 'processing') switchQueueTab('processing');
    else renderQueueList();
    return tid;
}
function updateQueue(qid, status, message) {
    if (_queueItems[qid]) {
        _queueItems[qid].status = status;
        _queueItems[qid].message = message || getStatusText(status);
    } else {
        _pendingUpdates[qid] = {status: status, message: message};
    }
    renderQueueList();
}
function switchQueueTab(tab) {
    _queueTab = tab;
    document.querySelectorAll('.queue-tab').forEach(function(t){
        t.classList.toggle('active', t.getAttribute('data-qt') === tab);
    });
    var cb = document.getElementById('queueCheckAll');
    if (cb) cb.checked = false;
    renderQueueList();
}
function getQueueItemsByTab(tab) {
    var items = [];
    for (var qid in _queueItems) {
        var item = _queueItems[qid];
        var match = false;
        if (tab !== 'processing' && item.mode && item.mode !== currentMode) continue;
        if (tab === 'processing') {
            match = (item.status === 'pending' || item.status === 'waiting' || item.status === 'processing' || item.status === 'paused');
        } else if (tab === 'completed') {
            match = (item.status === 'completed');
        } else if (tab === 'failed') {
            match = (item.status === 'error' || item.status === 'failed' || item.status === 'cancelled');
        }
        if (match) items.push({name: item.name, queueId: qid, data: item});
    }
    if (tab === 'processing') {
        items.sort(function(a, b) {
            var orderA = a.data.status === 'processing' ? 0 : (a.data.status === 'paused' ? 1 : 2);
            var orderB = b.data.status === 'processing' ? 0 : (b.data.status === 'paused' ? 1 : 2);
            if (orderA !== orderB) return orderA - orderB;
            return 0;
        });
    } else if (tab === 'failed') {
        items.sort(function(a, b) {
            var aIsCancel = a.data.status === 'cancelled' ? 0 : 1;
            var bIsCancel = b.data.status === 'cancelled' ? 0 : 1;
            return aIsCancel - bIsCancel;
        });
    }
    return items;
}
function renderQueueList() {
    var checkedIds = {};
    document.querySelectorAll('#queueList .queue-cb:checked').forEach(function(cb){
        checkedIds[cb.value] = true;
    });
    var items = getQueueItemsByTab(_queueTab);
    var isPaused = document.body.classList.contains('queue-paused');
    var html = '';
    if (items.length === 0) {
        var emptyTexts = { processing: '暂无待处理文件', completed: '暂无已完成文件', failed: '暂无失败文件' };
        html = '<div class="queue-empty"><div class="queue-empty-text">' + (emptyTexts[_queueTab] || '暂无文件') + '</div></div>';
    } else {
        var showCheck = (_queueTab === 'processing' || _queueTab === 'failed') && !_processingLocked;
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var name = item.name;
            var data = item.data;
            var qid = item.queueId;
            var statusText = data.message || getStatusText(data.status);
            html += '<div class="queue-item" data-file="' + escapeHtml(name) + '">';
            if (showCheck) {
                html += '<input type="checkbox" class="queue-cb" value="' + escapeHtml(qid) + '" style="margin-right:4px;flex-shrink:0;"' + (checkedIds[qid] ? ' checked' : '') + '>';
            }
            html += '<span class="queue-type-badge">' + getFileType(data.orig_name || name) + '</span>';
            if (data.mode) {
                var modeColor = data.mode === 'extract' ? '#059669' : '#7c3aed';
                html += '<span class="queue-mode-tag" style="font-size:10px;color:' + modeColor + ';margin-right:4px;flex-shrink:0;">[' + (data.mode === 'extract' ? '提取' : '脱敏') + ']</span>';
            }
            html += '<span class="queue-item-name">' + escapeHtml(name) + '</span>' +
                '<span class="queue-status-chip ' + data.status + '">' + escapeHtml(statusText) + '</span>';
            if ((data.status === 'error' || data.status === 'failed' || data.status === 'cancelled') && !_processingLocked) {
                html += '<button class="download-btn queue-retry-btn" onclick="event.stopPropagation();retryFile(\'' + escapeHtml(qid) + '\')" style="font-size:11px;padding:2px 8px;margin-left:4px;flex-shrink:0;">重试</button>';
            }
            html += '</div>';
        }
        if (showCheck && items.length > 1) {
            document.getElementById('selectAllLabel').style.display = '';
        } else {
            document.getElementById('selectAllLabel').style.display = 'none';
        }
    }
    var list = document.getElementById('queueList');
    list.innerHTML = html;
    updateQueueCounts();
    updateBatchActions();
}
function updateQueueCounts() {
    var pp = 0, pc = 0, pf = 0;  // per-mode completed/failed
    var pAll = 0;  // all-mode processing
    for (var qid in _queueItems) {
        var item = _queueItems[qid];
        var s = item.status;
        if (s === 'pending' || s === 'waiting' || s === 'processing' || s === 'paused') {
            pAll++;
        } else if (s === 'completed') {
            if (!item.mode || item.mode === currentMode) pc++;
        } else if (s === 'error' || s === 'failed' || s === 'cancelled') {
            if (!item.mode || item.mode === currentMode) pf++;
        }
    }
    document.getElementById('qtProcessingCount').textContent = pAll;
    document.getElementById('qtCompletedCount').textContent = pc;
    document.getElementById('qtFailedCount').textContent = pf;
    document.getElementById('queueCount').textContent = pAll;
}
function toggleAllQueueCb(el) {
    var checked = el.checked;
    document.querySelectorAll('#queueList .queue-cb').forEach(function(cb) {
        cb.checked = checked;
    });
}
function updateBatchActions() {
    var batchEl = document.getElementById('queueBatchActions');
    var batchRetryBtn = document.getElementById('batchRetryBtn');
    var batchKillBtn = document.getElementById('batchKillBtn');
    var batchDeleteBtn = document.getElementById('batchDeleteBtn');
    if (_processingLocked) {
        batchEl.style.display = 'none';
        return;
    }
    var failedCount = 0, procCount = 0;
    for (var qid in _queueItems) {
        var item = _queueItems[qid];
        var s = item.status;
        if (s === 'error' || s === 'failed' || s === 'cancelled') failedCount++;
        if (s === 'pending' || s === 'waiting' || s === 'processing' || s === 'paused') procCount++;
    }
    var showRetry = _queueTab === 'failed' && failedCount >= 1;
    var showDelete = _queueTab === 'failed' && failedCount >= 1;
    var showKill = _queueTab === 'processing' && procCount > 0;
    if (showRetry || showKill || showDelete) {
        batchEl.style.display = 'flex';
        batchRetryBtn.style.display = showRetry ? '' : 'none';
        batchKillBtn.style.display = showKill ? '' : 'none';
        batchDeleteBtn.style.display = showDelete ? '' : 'none';
    } else {
        batchEl.style.display = 'none';
    }
}
function getCheckedQueueIds() {
    var ids = [];
    document.querySelectorAll('#queueList .queue-cb:checked').forEach(function(cb){
        ids.push(cb.value);
    });
    return ids;
}
function batchRetry() {
    var ids = getCheckedQueueIds();
    if (ids.length === 0) { addLog('warning', '请先勾选要重试的文件'); return; }
    if (_batchOperationLock) { showToast('正在执行批量操作，请稍候', false, true); return; }
    _batchOperationLock = true;
    var prevStates = {};
    var largeFileId = null;
    ids.forEach(function(tid){
        if (_queueItems[tid]) {
            prevStates[tid] = {status: _queueItems[tid].status, message: _queueItems[tid].message};
            if (_queueItems[tid].is_large) {
                largeFileId = tid;
            }
        }
    });
    ids.forEach(function(tid){
        if (_queueItems[tid]) {
            _queueItems[tid].status = 'waiting';
            if (tid === largeFileId && _queueItems[tid].total_chunks) {
                _queueItems[tid].message = '等待中 (/' + _queueItems[tid].total_chunks + ')';
            } else {
                _queueItems[tid].message = '等待中';
            }
        }
    });
    if (largeFileId && _queueItems[largeFileId]) {
        var lfe = _queueItems[largeFileId];
        if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
        _largeTask.groupId = largeFileId;
        _largeTask.queueId = largeFileId;
        _largeTask.totalChunks = lfe.total_chunks || 1;
        _largeTask.displayVersion = 0;
        startLargeTaskPolling();
        updateLargeTaskDisplay();
    }
    renderQueueList();
    fetch('/api/queue/tasks/batch-retry', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_ids: ids})
    }).then(function(r){return r.json();})
    .then(function(d){
        if (d.error) {
            ids.forEach(function(tid){
                if (prevStates[tid] && _queueItems[tid]) {
                    _queueItems[tid].status = prevStates[tid].status;
                    _queueItems[tid].message = prevStates[tid].message;
                }
            });
            if (largeFileId) {
                _largeTask.groupId = null;
                _largeTask.queueId = null;
                _largeTask.totalChunks = 0;
                if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
            }
            renderQueueList();
            addLog('error', '重试失败: ' + d.error);
        } else {
            addLog('info', '已发起 ' + ids.length + ' 个文件的重试');
            fetch('/api/queue/resume', {method:'POST'}).catch(function(){});
        }
    }).catch(function(e){
        ids.forEach(function(tid){
            if (prevStates[tid] && _queueItems[tid]) {
                _queueItems[tid].status = prevStates[tid].status;
                _queueItems[tid].message = prevStates[tid].message;
            }
        });
        if (largeFileId) {
            _largeTask.groupId = null;
            _largeTask.queueId = null;
            _largeTask.totalChunks = 0;
            if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
        }
        renderQueueList();
        addLog('error', '重试失败: ' + e.message);
    }).finally(function(){
        _batchOperationLock = false;
    });
}
function batchKillQueue() {
    var ids = getCheckedQueueIds();
    if (ids.length === 0) { addLog('warning', '请先勾选要终止的文件'); return; }
    if (_batchOperationLock) { showToast('正在执行批量操作，请稍候', false, true); return; }
    if (!confirm('确定要从队列中移除 ' + ids.length + ' 个文件吗？')) return;
    _batchOperationLock = true;
    if (_largeTask.groupId && ids.indexOf(_largeTask.groupId) !== -1) {
        _killLargeTask();
    }
    var prevStates = {};
    ids.forEach(function(tid){
        if (_queueItems[tid]) {
            prevStates[tid] = {status: _queueItems[tid].status, message: _queueItems[tid].message};
            _queueItems[tid].status = 'cancelled'; _queueItems[tid].message = '已取消';
        }
    });
    renderQueueList();
    fetch('/api/queue/tasks/batch-cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_ids: ids})
    }).then(function(r){return r.json();})
    .then(function(d){
        if (d.error) {
            ids.forEach(function(tid){
                if (prevStates[tid] && _queueItems[tid]) {
                    _queueItems[tid].status = prevStates[tid].status;
                    _queueItems[tid].message = prevStates[tid].message;
                }
            });
            renderQueueList();
            addLog('error', '移除失败: ' + d.error);
            return;
        }
        addLog('info', '已从队列移除 ' + ids.length + ' 个文件');
    }).catch(function(e){
        ids.forEach(function(tid){
            if (prevStates[tid] && _queueItems[tid]) {
                _queueItems[tid].status = prevStates[tid].status;
                _queueItems[tid].message = prevStates[tid].message;
            }
        });
        renderQueueList();
        addLog('error', '移除失败: ' + e.message);
    }).finally(function(){
        _batchOperationLock = false;
    });
}
function batchDeleteFailed() {
    var ids = getCheckedQueueIds();
    if (ids.length === 0) { addLog('warning', '请先勾选要删除的文件'); return; }
    if (_batchOperationLock) { showToast('正在执行批量操作，请稍候', false, true); return; }
    if (!confirm('确定要彻底删除 ' + ids.length + ' 个文件吗？此操作不可恢复。')) return;
    _batchOperationLock = true;
    var deletedItems = {};
    ids.forEach(function(tid){
        if (_queueItems[tid]) {
            deletedItems[tid] = _queueItems[tid];
            delete _queueItems[tid];
        }
    });
    renderQueueList();
    fetch('/api/queue/tasks/batch-delete', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_ids: ids})
    }).then(function(r){return r.json();})
    .then(function(d){
        if (d.error) {
            ids.forEach(function(tid){
                if (deletedItems[tid]) _queueItems[tid] = deletedItems[tid];
            });
            renderQueueList();
            addLog('error', '删除失败: ' + d.error);
            return;
        }
        addLog('info', '已彻底删除 ' + ids.length + ' 个文件');
    }).catch(function(e){
        ids.forEach(function(tid){
            if (deletedItems[tid]) _queueItems[tid] = deletedItems[tid];
        });
        renderQueueList();
        addLog('error', '删除失败: ' + e.message);
    }).finally(function(){
        _batchOperationLock = false;
    });
}
function retryFile(tid) {
    var entry = _queueItems[tid];
    if (!entry) return;
    var isLarge = entry.is_large;

    if (_queueItems[tid]) {
        _queueItems[tid].status = 'waiting';
        _queueItems[tid].message = isLarge ? ('等待中' + (entry.total_chunks ? ' (/' + entry.total_chunks + ')' : '')) : '等待中';
    }
    if (isLarge) {
        if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
        _largeTask.groupId = tid;
        _largeTask.queueId = tid;
        _largeTask.totalChunks = entry.total_chunks || 1;
        _largeTask.displayVersion = 0;
        startLargeTaskPolling();
        updateLargeTaskDisplay();
    }
    renderQueueList();

    fetch('/api/queue/tasks/batch-retry', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_ids: [tid]})
    }).then(function(r){return r.json();})
    .then(function(data){
        if (data.error) {
            if (_queueItems[tid]) {
                _queueItems[tid].status = 'failed';
                _queueItems[tid].message = '重试失败';
                if (isLarge) {
                    _largeTask.groupId = null;
                    _largeTask.queueId = null;
                    _largeTask.totalChunks = 0;
                    if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
                }
            }
            renderQueueList();
            addLog('error', '[' + entry.name + '] 重试失败: ' + data.error);
        } else {
            addLog('info', '[' + entry.name + '] 已重新加入队列');
        }
    })
    .catch(function(err){
        if (_queueItems[tid]) {
            _queueItems[tid].status = 'failed';
            _queueItems[tid].message = '重试失败';
            if (isLarge) {
                _largeTask.groupId = null;
                _largeTask.queueId = null;
                _largeTask.totalChunks = 0;
                if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
            }
        }
        renderQueueList();
        addLog('error', '[' + entry.name + '] 重试失败: ' + err.message);
    });
}
function getStatusText(status) {
    switch(status) {
        case 'waiting': return '等待中';
        case 'pending': return '等待中';
        case 'processing': return '处理中';
        case 'paused': return '等待中';
        case 'completed': return '已完成';
        case 'failed': return '失败';
        case 'error': return '失败';
        case 'cancelled': return '已取消';
        default: return status;
    }
}
function handleResult(data) {
    var queueItem = data.task_id ? _queueItems[data.task_id] : null;
    var resultMode = (queueItem && queueItem.mode) || data.mode || 'desensitize';
    var inDashboard = _inDashboard;
    var isCurrentMode = resultMode === currentMode;

    if (inDashboard && isCurrentMode) {
        _fetchDashboardSilent();
    }

    if (data.task_id) _currentTaskId = data.task_id;

    if (data.parent_task_id && data.parent_task_id !== 'None' && _queueItems[data.parent_task_id]) {
        if (data.status === 'completed' || data.status === 'error') {
            _updateParentProgress(data.parent_task_id, data.task_id, data.chunk_index);
        }
    }

    /* 队列状态更新不受模式影响 */
    if (data.status === 'completed') {
        if (isCurrentMode) stopProcessingTimer();
        const now = new Date();
        data.timestamp = now.toLocaleString();
        data.process_time = data.duration || processingSeconds;
        data.process_file = processingFileName;
        if (resultMode === 'extract') {
            if (_largeTask.groupId) {
                // 大文件提取：检查所有子任务是否完成
                fetch('/api/queue/parent/' + encodeURIComponent(_largeTask.groupId) + '/extract_merged')
                .then(function(r) {
                    if (!r.ok) throw new Error('获取合并结果失败 (HTTP ' + r.status + ')');
                    return r.json();
                })
                .then(function(g) {
                    if (g.error) {
                        addLog('error', '获取大文件提取合并结果失败: ' + g.error);
                        return;
                    }
                    if (g.completed >= g.total) {
                        var extractData = {
                            mode: 'extract',
                            file: g.parent_display_name || '',
                            status: 'completed',
                            extract_header: g.header || [],
                            extract_header_labels: g.header_labels || [],
                            extract_fields: g.fields || [],
                            extract_field_keys: g.field_keys || [],
                            extract_field_sections: g.field_sections || [],
                            extract_items: g.items || [],
                            item_count: g.item_count || 0,
                            original_length: g.original_length || 0,
                            timestamp: new Date().toLocaleString(),
                            process_file: g.parent_display_name || '',
                            process_time: 0,
                            duration: 0,
                        };
                        _resultByMode['extract'] = extractData;
                        window._currentExtractResult = extractData;
                        saveExtractionHistory(extractData);
                        if (isCurrentMode) {
                            displayExtractionResult(extractData);
                        }
                        addLog('success', '[' + (g.parent_display_name || '大文件') + '] 提取完成，共' + g.item_count + '条明细');
                    }
                })
                .catch(function(e) {
                    addLog('error', '获取大文件提取合并结果异常: ' + e.message);
                });
            } else {
                saveExtractionHistory(data);
                _resultByMode['extract'] = data;
                window._currentExtractResult = data;
                if (isCurrentMode) {
                    displayExtractionResult(data);
                }
            }
            if (data.task_id) updateQueue(data.task_id, 'completed', '已完成');
        } else {
            if (_largeTask.groupId) {
                if (isCurrentMode) updateLargeTaskDisplay();
            } else {
                currentResult = data;
                _resultByMode[resultMode] = data;
                if (data.task_id && _queueItems[data.task_id]) {
                    data.file = _queueItems[data.task_id].name;
                }
                resultsHistory.unshift(data);
                if (resultsHistory.length > 50) resultsHistory.pop();
                if (isCurrentMode && currentMode !== 'extract') {
                    displayResult(data);
                }
                if (data.task_id) {
                    updateQueue(data.task_id, 'completed', '已完成');
                }
            }
        }
    } else if (data.status === 'cancelled') {
        _hasProcessedAny = true;
        if (data.task_id) updateQueue(data.task_id, 'cancelled', '已取消');
        if (isCurrentMode) stopProcessingTimer();
        if (_largeTask.groupId && data.parent_group_id === _largeTask.groupId) { _killLargeTask(); return; }
    } else if (data.status === 'paused') {
        _currentTaskId = '';
        if (data.task_id) updateQueue(data.task_id, 'paused', '等待中');
        if (isCurrentMode) stopProcessingTimer();
        if (_largeTask.groupId) { updateLargePaused(); if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; } return; }
    } else if (data.status === 'error') {
        _hasProcessedAny = true;
        if (data.task_id) updateQueue(data.task_id, 'error', data.message || '处理失败');
        if (isCurrentMode) stopProcessingTimer();
        currentResult = null;
        // 不kill大文件，让进度逻辑自然处理
        // 子任务失败不等于用户取消，应该保留大文件继续处理其他子任务
        if (data.parent_task_id && data.parent_task_id !== 'None' && _queueItems[data.parent_task_id]) {
            _updateParentProgress(data.parent_task_id, data.task_id, data.chunk_index);
        }
    }
}
function displayExtractionResult(data) {
    window._currentExtractResult = data;
    resetExtractCompare();
    var headers = data.extract_header || {};
    var fieldLabels = data.extract_fields || [];
    var fieldKeys = data.extract_field_keys || [];
    var fieldSections = data.extract_field_sections || [];
    var items = data.extract_items || [];
    var itemCount = data.item_count || 0;
    var fileSize = data.original_length || 0;
    var autoMerged = data.auto_merged || false;
    var origUrl = data.original_file_url || '';
    var hasOrig = origUrl && (origUrl.endsWith('.png') || origUrl.endsWith('.jpg') || origUrl.endsWith('.jpeg') || origUrl.endsWith('.bmp') || origUrl.endsWith('.webp'));
    var isImageFile = hasOrig;
    var origDisplayUrl = isImageFile ? ('/api/download/' + encodeURIComponent(origUrl)) : '';

    if (isImageFile && origDisplayUrl) {
        originalPanel.innerHTML = '<div class="extract-orig-frame" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;"><img class="extract-orig-preview-img" src="' + origDisplayUrl + '" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;cursor:zoom-in;" alt="原文件"></div>';
    } else {
        originalPanel.innerHTML = '<pre>' + escapeHtml(data.original_preview || '') + '</pre>';
    }
    _extractOriginalContent = originalPanel.innerHTML;

    var historyCount = extractionHistory.length;
    resultMeta.innerHTML = '<span style="font-size:13px;color:var(--gray-600);">' +
        '<strong>' + escapeHtml(data.file) + '</strong> &middot; 原文 ' + fileSize + ' 字 &middot; 提取 <strong>' + itemCount + '</strong> 条明细</span>';

    var validation = data.invoice_validation || null;
    var isInvoice = false;
    for (var ci = 0; ci < fieldKeys.length; ci++) {
        if (fieldKeys[ci] === '税率/征收率' || fieldKeys[ci] === '税额') { isInvoice = true; break; }
    }
    var errorCellMap = {};
    var headerErrors = {};
    if (validation && validation.errors) {
        for (var ei = 0; ei < validation.errors.length; ei++) {
            var err = validation.errors[ei];
            var rk = (err.item_index !== null && err.item_index !== undefined) ? err.item_index : -1;
            var ek = err.field || '';
            if (rk >= 0) {
                if (!errorCellMap[rk]) errorCellMap[rk] = {};
                errorCellMap[rk][ek] = err.reason || '';
            } else {
                headerErrors[ek] = (headerErrors[ek] ? headerErrors[ek] + '; ' : '') + (err.reason || '');
            }
        }
    }

    var headerHtml = '<div class="extract-header-card"><div class="extract-header-title">票据信息</div><div class="extract-header-grid">';
    var isRo = document.body.classList.contains('processing-readonly');
    var hdrKeys = Object.keys(headers);
    for (var ki = 0; ki < hdrKeys.length; ki++) {
        var key = hdrKeys[ki];
        var labelInfo = data.extract_header_labels ? data.extract_header_labels[key] : null;
        var label = labelInfo ? labelInfo.label : key;
        var hdrErr = isInvoice ? (headerErrors[key] || '') : '';
        var hdrStyle = hdrErr ? 'background:#ffcccc;' : '';
        var hdrTitle = hdrErr ? ' title="' + escapeHtml(hdrErr) + '"' : '';
        headerHtml += '<div class="extract-header-row"><span class="extract-header-label">' + escapeHtml(label) + '</span>' +
            '<div class="extract-header-value"><input class="extract-cell-input" value="' + escapeHtml(headers[key] || '') + '" data-row="-1" data-key="' + key + '" data-section="header" style="' + hdrStyle + '"' + hdrTitle + (isRo ? ' readonly' : '') + '></div>' +
            '</div>';
    }
    headerHtml += '</div></div>';

    var itemHtml = '<div class="extract-items-section"><div class="extract-section-title">明细列表 (' + itemCount + ' 条)</div>';
    itemHtml += '<table class="extract-item-table"><thead><tr>';
    for (var ci = 0; ci < fieldKeys.length; ci++) {
        if (fieldSections[ci] === 'item') {
            itemHtml += '<th>' + escapeHtml(fieldLabels[ci]) + '</th>';
        }
    }
    itemHtml += '</tr></thead><tbody>';
    for (var ri = 0; ri < items.length; ri++) {
        var item = items[ri];
        var rowErrors = errorCellMap[ri] || {};
        itemHtml += '<tr>';
        for (var ci = 0; ci < fieldKeys.length; ci++) {
            if (fieldSections[ci] === 'item') {
                var key = fieldKeys[ci];
                var val = item[key] || '';
                var cellErr = isInvoice ? (rowErrors[key] || '') : '';
                var cellStyle = cellErr ? 'text-align:center;font-size:12px;padding:4px 6px;background:#ffcccc;' : 'text-align:center;font-size:12px;padding:4px 6px;';
                var cellTitle = cellErr ? ' title="' + escapeHtml(cellErr) + '"' : '';
                itemHtml += '<td><input class="extract-cell-input" value="' + escapeHtml(val) + '" data-row="' + ri + '" data-key="' + key + '" data-section="item" style="' + cellStyle + '"' + cellTitle + (isRo ? ' readonly' : '') + '></td>';
            }
        }
        itemHtml += '</tr>';
    }
    itemHtml += '</tbody></table></div>';
    if (items.length === 0) {
        itemHtml = '<div style="text-align:center;padding:20px;color:var(--gray-400);">未识别到明细数据</div>';
    }

    var mergeNote = autoMerged ? '<div style="padding:8px 12px;margin-bottom:8px;background:var(--success-bg);color:var(--success);border-radius:var(--radius-sm);font-size:13px;font-weight:500;">已自动合并到Excel表格，数据如下：</div>' : '';

    var validationHtml = '';
    if (isInvoice && validation) {
        var rulesSkipped = validation.rules_skipped || 0;
        if (validation.status === 'has_errors') {
            validationHtml = '<div style="padding:10px 14px;margin:8px 0;background:#fff0f0;border:1px solid #fecaca;border-radius:8px;font-size:13px;color:#dc2626;line-height:1.6;">' +
                '<strong>共发现 ' + validation.error_count + ' 个潜在错误</strong>' +
                (rulesSkipped > 0 ? '，' + rulesSkipped + ' 项校验因字段缺失跳过' : '') +
                '</div>';
        } else if (validation.error_count === 0) {
            validationHtml = '<div style="padding:10px 14px;margin:8px 0;background:#f0fff0;border:1px solid #bbf7d0;border-radius:8px;font-size:13px;color:#16a34a;">' +
                '自动校对无误' +
                (rulesSkipped > 0 ? '，' + rulesSkipped + ' 项校验因字段缺失跳过' : '') +
                '</div>';
        }
    }

    var compareFab = '';
    if (isInvoice) {
        compareFab = (isImageFile && origDisplayUrl)
            ? '<div class="extract-compare-fab"><button type="button" class="download-btn" onclick="autoVerifyInvoice()" style="background:var(--primary);margin-right:6px;">自动校对</button><button type="button" class="download-btn" id="extractCompareBtn">对照查看</button></div>'
            : '<div class="extract-compare-fab"><button type="button" class="download-btn" onclick="autoVerifyInvoice()" style="background:var(--primary);">自动校对</button></div>';
    } else if (isImageFile && origDisplayUrl) {
        compareFab = '<div class="extract-compare-fab"><button type="button" class="download-btn" id="extractCompareBtn">对照查看</button></div>';
    }
    extractPanel.innerHTML = mergeNote + headerHtml + itemHtml + validationHtml + compareFab;
    extractPanel.setAttribute('data-orig-url', origDisplayUrl || '');

    if (autoMerged) {
        resultActions.innerHTML =
            '<div class="extract-actions">' +
            '<button type="button" class="download-btn" onclick="saveExtractOnly()" style="background:var(--primary);"' + (isRo ? ' disabled' : '') + '>保存修改</button>' +
            '<button type="button" class="download-btn" onclick="saveExtractAndSync()" style="background:var(--success);"' + (isRo ? ' disabled' : '') + '>添加到表</button>' +
            '<span class="help-badge" onclick="showMergeHelp()" style="cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:var(--gray-300);color:#666;font-size:11px;font-weight:700;margin-left:4px;" title="添加到表说明">?</span>' +
            '</div>';
        switchTab('extract');
        loadMergePreview();
    } else {
        resultActions.innerHTML =
            '<div class="extract-actions">' +
            '<button type="button" class="download-btn" onclick="saveExtractOnly()" style="background:var(--primary);"' + (isRo ? ' disabled' : '') + '>保存修改</button>' +
            '<button type="button" class="download-btn" onclick="saveExtractAndSync()" style="background:var(--success);"' + (isRo ? ' disabled' : '') + '>添加到表</button>' +
            '<span class="help-badge" onclick="showMergeHelp()" style="cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:var(--gray-300);color:#666;font-size:11px;font-weight:700;margin-left:4px;" title="添加到表说明">?</span>' +
            '</div>';
    }

    switchTab('extract');
    _extractResultContent = extractPanel.innerHTML;
    setTimeout(function() {
        enableExtractResize();
        enableResizableColumns('.extract-item-table');
    }, 50);
}
function toggleHistory() {
    var html = '<div class="extract-history-panel"><div class="extract-section-title">提取历史</div>';
    if (!extractionHistory.length) {
        html += '<div style="padding:12px;color:var(--gray-400);font-size:13px;">暂无历史</div>';
    } else {
        extractionHistory.forEach(function(h, i) {
            var cnt = h.item_count || 0;
            var timeStr = '';
            if (h.process_time) {
                var sec = h.process_time;
                timeStr = sec >= 60 ? Math.floor(sec / 60) + '分' + (sec % 60) + '秒' : sec + '秒';
            }
            var durationTag = timeStr ? '<span class="duration-tag">' + timeStr + '</span>' : '';
            html += '<div class="history-item" onclick="viewExtractionItem(' + i + ')" style="cursor:pointer;">' +
                '<div><div class="history-item-name">' + escapeHtml(h.file) + '</div>' +
                '<div class="history-item-meta">' + (h.timestamp || '') + ' ' + durationTag + ' ' + cnt + '条明细</div></div>' +
                '<span class="history-view-btn">查看</span></div>';
        });
    }
    html += '</div>';
    showModal(html, '提取历史');
}
function viewExtractionItem(index) {
    var data = extractionHistory[index];
    if (data) {
        displayExtractionResult(data);
        closeModal();
    }
}
function showModal(html, title) {
    var overlay = document.getElementById('modalOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'modalOverlay';
        overlay.className = 'settings-overlay';
        overlay.innerHTML = '<div class="settings-panel" style="max-width:95vw;"><div class="settings-header"><div class="settings-title" id="modalTitle"></div><button class="settings-close" onclick="closeModal()">&times;</button></div><div class="settings-body" id="modalBody"></div></div>';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', function(e) { if (e.target === this) closeModal(); });
    }
    document.getElementById('modalTitle').textContent = title || '';
    document.getElementById('modalBody').innerHTML = html;
    overlay.classList.add('active');
}
function closeModal() {
    var overlay = document.getElementById('modalOverlay');
    if (overlay) overlay.classList.remove('active');
}
function startLargeTaskPolling() {
    updateLargeTaskDisplay();
}
function _killLargeTask() {
    if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
    if (_largeTask.queueId) updateQueue(_largeTask.queueId, 'error', '处理中断');
    fetch('/api/queue/tasks/batch-cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_ids: [_largeTask.groupId]})
    }).catch(function(){});
    _largeTask.groupId = null;
    _largeTask.queueId = null;
    _largeTask.totalChunks = 0;
    stopProcessingTimer();
}
function updateLargePaused() {
    if (_largeTask.queueId) updateQueue(_largeTask.queueId, 'paused', '等待中');
}
function updateLargeTaskDisplay() {
    if (!_largeTask.groupId) return;
    var parentItem = _queueItems[_largeTask.groupId];
    var taskMode = parentItem && parentItem.mode || currentMode;
    var isExtract = taskMode === 'extract';
    var endpoint = isExtract ? '/api/queue/parent/' + encodeURIComponent(_largeTask.groupId) + '/extract_merged'
                             : '/api/queue/parent/' + encodeURIComponent(_largeTask.groupId) + '/merged';
    var version = ++_largeTask.displayVersion;
    fetch(endpoint)
    .then(function(r) { return r.json(); })
    .then(function(g) {
        if (version !== _largeTask.displayVersion) return;
        if (!g || !g.total) return;
        if (currentMode !== taskMode) return;
        var completed = g.completed || 0;
        var total = g.total || 0;
        var displayName = (_largeTask.queueId && _queueItems[_largeTask.queueId]) ? _queueItems[_largeTask.queueId].name : (g.parent_display_name || '');

        if (isExtract) {
            var extractData = {
                mode: 'extract',
                file: displayName,
                status: 'completed',
                header: g.header || [],
                header_labels: g.header_labels || [],
                fields: g.fields || [],
                field_keys: g.field_keys || [],
                field_sections: g.field_sections || [],
                items: g.items || [],
                item_count: g.item_count || 0,
                original_length: g.original_length || 0,
                timestamp: new Date().toLocaleString(),
                process_file: displayName,
                process_time: 0,
                duration: 0,
            };
            if (completed >= total) {
                saveExtractionHistory(extractData);
                if (currentMode === 'extract') {
                    displayExtractionResult(extractData);
                }
            }
        } else {
            var fakeData = {
                file: g.parent_display_name || '',
                original_preview: g.original_text ? g.original_text.substring(0, 2000) : '',
                desensitized_preview: g.text ? g.text.substring(0, 2000) : '',
                _full_content: g.text,
                _full_original: g.original_text || g.text,
                replacements: g.replacements || [],
                output_file: '',
                original_length: g.original_text ? g.original_text.length : (g.text ? g.text.length : 0),
                desensitized_length: g.text ? g.text.length : 0,
                group_info: {
                    chunk_count: completed,
                    total_chunks: total,
                    duration: g.total_duration || 0,
                    original_preview: g.original_text ? g.original_text.substring(0, 2000) : '',
                    original_length: g.original_text ? g.original_text.length : 0,
                    desensitized_length: g.text ? g.text.length : 0,
                }
            };
            displayDesensitizedResult(fakeData, true);
        }

        if (_largeTask.queueId) updateQueue(_largeTask.queueId, completed >= total ? 'completed' : 'processing', completed + '/' + total);

        if (completed >= total) {
            stopProcessingTimer();
            if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
            _largeTask.groupId = null;
            _largeTask.queueId = null;
            _largeTask.totalChunks = 0;
            addLog('success', '[' + (g.parent_display_name || '') + '] 所有子任务已完成');
            if (!isExtract) {
                var mergedEntry = {
                    file: displayName,
                    original_preview: g.original_text ? g.original_text.substring(0, 2000) : '',
                    desensitized_preview: g.text ? g.text.substring(0, 2000) : '',
                    _full_content: g.text,
                    _full_original: g.original_text || g.text,
                    replacements: g.replacements || [],
                    output_file: '',
                    status: 'completed',
                    timestamp: new Date().toLocaleString(),
                    process_file: g.parent_display_name || '',
                    replacement_count: (g.replacements || []).length,
                    original_length: (g.original_text || g.text || '').length,
                    desensitized_length: (g.text || '').length
                };
                resultsHistory.unshift(mergedEntry);
                if (resultsHistory.length > 50) resultsHistory.pop();
                currentResult = fakeData;
                var modeKey = (parentItem && parentItem.mode) || 'desensitize';
                _resultByMode[modeKey] = fakeData;
            }
        }
    })
    .catch(function() {});
}
function displayResult(data) {
    displayDesensitizedResult(data, false);
}
function displayDesensitizedResult(data, isLargeTask) {
    var groupInfo = data.group_info || null;
    const originalLen = groupInfo ? (groupInfo.original_length || data.original_length || 0) : (data.original_length || 0);
    const desensitizedLen = groupInfo ? (groupInfo.desensitized_length || data.desensitized_length || 0) : (data.desensitized_length || 0);
    const reps = data.replacements || [];
    var repCount = reps.length;
    var previewLimit = isLargeTask ? 2000 : 8000;
    var displayReps = isLargeTask ? reps.slice(0, 50) : reps;

    _currentDesensitizeData = {
        file: data.file,
        output_file: data.output_file,
        original_preview: data.original_preview || '',
        desensitized_preview: data.desensitized_preview || '',
        _full_original: data._full_original || '',
        _full_content: data._full_content || '',
        replacements: reps,
        replaced_with: (reps[0] || {}).replaced_with || 'xxx',
        isLargeTask: isLargeTask,
        groupId: _largeTask.groupId
    };

    var isInProgress = isLargeTask && groupInfo && groupInfo.chunk_count < groupInfo.total_chunks;

    var titleHtml = '<span style="font-size:13px;color:var(--gray-600);"><strong>' + escapeHtml(data.file) + '</strong>';
    if (isLargeTask && groupInfo) {
        titleHtml += ' &middot; 已完成 ' + groupInfo.chunk_count + '/' + groupInfo.total_chunks + ' &middot; 耗时 ' + (groupInfo.duration || 0) + 's';
    }
    titleHtml += ' &middot; 原文 ' + originalLen + ' 字 &middot; 脱敏后 ' + desensitizedLen + ' 字 &middot; 替换 <strong>' + repCount + '</strong> 项</span>';
    resultMeta.innerHTML = titleHtml;

    var origPreview = (groupInfo ? (groupInfo.original_preview || '') : (data.original_preview || ''));
    if (isLargeTask && data._full_original && data._full_original.length > previewLimit) {
        origPreview = origPreview.substring(0, previewLimit) + '\n\n...（已截断，共 ' + originalLen + ' 字）';
    }
    originalPanel.innerHTML = '<pre>' + escapeHtml(origPreview) + '</pre>';
    _desensitizeOriginalContent = originalPanel.innerHTML;
    _desensitizePanels.replacements = '';

    var fullContent = data._full_content || (data.desensitized_preview || '');
    if (fullContent === (data.desensitized_preview || '')) {
        fullContent = fullContent.replace(/\.\.\.$/, '');
    }
    if (isLargeTask) {
        if (fullContent.length > previewLimit) {
            fullContent = fullContent.substring(0, previewLimit) + '\n\n...（已截断，共 ' + desensitizedLen + ' 字）';
        }
        var existingPre = desensitizedPanel.querySelector('pre[_large_pre]');
        if (existingPre && isInProgress) {
            var scrollTop = existingPre.parentElement ? existingPre.parentElement.scrollTop || 0 : 0;
            existingPre.textContent = fullContent;
            if (existingPre.parentElement) existingPre.parentElement.scrollTop = scrollTop;
        } else {
            desensitizedPanel.innerHTML = '';
            desensitizedPanel.style.position = '';
            var preEl = document.createElement('pre');
            preEl.setAttribute('_large_pre', '1');
            preEl.textContent = fullContent;
            preEl.style.cssText = 'width:100%;height:100%;margin:0;padding:16px;border:none;outline:none;white-space:pre-wrap;font-size:14px;line-height:1.7;font-family:"JetBrains Mono","Fira Code","Consolas",monospace;color:var(--gray-800);background:transparent;overflow:auto;';
            desensitizedPanel.appendChild(preEl);
        }
        _desensitizePanels.desensitizedText = fullContent;
    } else {
        desensitizedPanel.innerHTML = '';
        desensitizedPanel.style.position = '';
        const textarea = document.createElement('textarea');
        textarea.value = fullContent;
        textarea.style.cssText = 'width:100%;height:100%;margin:0;padding:16px;border:none;outline:none;resize:none;font-size:14px;line-height:1.7;font-family:"JetBrains Mono","Fira Code","Consolas",monospace;color:var(--gray-800);background:transparent;';
        desensitizedPanel.appendChild(textarea);
        _desensitizePanels.desensitizedText = fullContent;
    }

    if (repCount > 0) {
        let regexCount = reps.filter(function(r) { return r.source === '正则'; }).length;
        let llmCount = repCount - regexCount;
        let tableHtml = '<div style="font-size:13px;color:var(--gray-500);margin-bottom:8px;">共 ' + repCount + ' 项（正则 ' + regexCount + ' + 大模型 ' + llmCount + '）替换为 <code>' + escapeHtml((data.replacements[0] || {}).replaced_with || '**') + '</code>';
        if (isLargeTask && displayReps.length < repCount) {
            tableHtml += '（仅显示前50条）';
        }
        tableHtml += '</div>';
        tableHtml += '<table class="rep-table"><thead><tr><th style="width:40px;">#</th><th>敏感信息</th><th style="width:60px;">来源</th><th style="width:70px;">类别</th><th style="width:70px;">替换为</th></tr></thead><tbody>';
        displayReps.forEach(function(r, i) {
            tableHtml += '<tr><td>' + (i+1) + '</td><td><code>' + escapeHtml(r.sensitive) + '</code></td><td>' + escapeHtml(r.source || '') + '</td><td style="font-size:11px;color:var(--gray-500);">' + escapeHtml(r.category || '') + '</td><td><code>' + escapeHtml(r.replaced_with) + '</code></td></tr>';
        });
        tableHtml += '</tbody></table>';
        replacementsPanel.innerHTML = tableHtml;
    } else {
        replacementsPanel.innerHTML = '<div class="result-empty"><div class="result-empty-text">未识别到敏感信息</div></div>';
    }

    var activeTab = document.querySelector('.result-tab.active');
    var activeTabName = activeTab ? activeTab.getAttribute('data-tab') : 'desensitized';
    if (activeTabName === 'desensitized') {
        if (isLargeTask) {
            resultActions.innerHTML = '<button class="download-btn" onclick="showToast(\'大文件不支持编辑修改\',false,true)" style="background:var(--success);margin-right:6px;">保存修改</button><button class="download-btn" onclick="downloadCurrentTab()" style="margin-right:6px;">下载</button>';
        } else {
            resultActions.innerHTML = `
                <button class="download-btn" onclick="saveEditedDesensitized('${encodeURIComponent(data.output_file)}')" style="background:var(--success);margin-right:6px;">
                    保存修改
                </button>
                <button class="download-btn" onclick="downloadCurrentTab()" style="margin-right:6px;">
                    下载
                </button>
            `;
        }
    }
    _desensitizePanels.desensitizedText = fullContent;
    _desensitizePanels.desensitized = desensitizedPanel.innerHTML;
    _desensitizePanels.replacements = replacementsPanel.innerHTML;
}
function saveEditedDesensitized(encodedFile) {
    var filename = decodeURIComponent(encodedFile);
    var ta = desensitizedPanel.querySelector('textarea');
    if (!ta) { showToast('大文件不支持编辑修改', false, true); return; }
    var content = ta.value;
    fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filename: filename, content: content})
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
        if (resp.error) { addLog('error', '保存失败: ' + resp.error); }
        else {
            addLog('success', '修改已保存 (' + resp.size + '字符)');
            _desensitizePanels.desensitizedText = content;
            _desensitizePanels.desensitized = desensitizedPanel.innerHTML;
            var btn = resultActions.querySelector('button');
            if (btn) {
                var orig = btn.innerHTML;
                btn.innerHTML = '已保存';
                btn.style.background = 'var(--success)';
                setTimeout(function() { btn.innerHTML = '保存修改'; }, 2000);
            }
        }
    })
    .catch(function(err) { addLog('error', '保存失败: ' + err.message); });
}
function downloadCurrentTab() {
    var activeTab = document.querySelector('.result-tab.active');
    if (!activeTab) return;
    var tabName = activeTab.getAttribute('data-tab');
    if (tabName === 'replacements') {
        downloadReplacementsExcel();
    } else if (tabName === 'original') {
        downloadOriginalText();
    } else if (tabName === 'desensitized') {
        downloadDesensitizedText();
    }
}
function downloadOriginalText() {
    var data = _currentDesensitizeData;
    if (!data) return;
    var content = data._full_original || '';
    if (!content) {
        var preEl = originalPanel.querySelector('pre');
        if (preEl) {
            content = preEl.textContent || '';
        }
    }
    if (!content) {
        content = data.original_preview || '';
    }
    if (!content) { addLog('warning', '原文内容为空'); return; }
    var stem = (data.file || 'original').replace(/\.[^.]+$/, '');
    var filename = stem + '_原文.txt';
    downloadBlob(content, filename, 'text/plain');
    addLog('success', '原文已下载');
}
function downloadDesensitizedText() {
    var data = _currentDesensitizeData;
    if (!data) return;
    var content = data._full_content || '';
    if (!content) {
        var ta = desensitizedPanel.querySelector('textarea');
        if (ta) {
            content = ta.value || '';
        } else {
            var preEl = desensitizedPanel.querySelector('pre');
            if (preEl) content = preEl.textContent || '';
        }
    }
    if (!content) {
        content = data.desensitized_preview || '';
    }
    if (!content) { addLog('warning', '脱敏内容为空'); return; }
    if (data.output_file) {
        var link = document.createElement('a');
        link.href = '/api/download/' + encodeURIComponent(data.output_file);
        link.download = data.output_file;
        link.click();
        addLog('success', '脱敏文件已下载');
        return;
    }
    var stem = (data.file || 'desensitized').replace(/\.[^.]+$/, '');
    var filename = stem + '_脱敏后.txt';
    downloadBlob(content, filename, 'text/plain');
    addLog('success', '脱敏内容已下载');
}
function downloadReplacementsExcel() {
    var data = _currentDesensitizeData;
    if (!data || !data.replacements || data.replacements.length === 0) {
        addLog('warning', '没有替换数据可下载');
        return;
    }
    var reps = data.replacements;
    var csvContent = '\uFEFF序号,敏感信息,来源,类别,替换为\n';
    reps.forEach(function(r, i) {
        var sensitive = (r.sensitive || '').replace(/"/g, '""');
        var source = (r.source || '').replace(/"/g, '""');
        var category = (r.category || '').replace(/"/g, '""');
        var replaced = (r.replaced_with || data.replaced_with || 'xxx').replace(/"/g, '""');
        csvContent += (i+1) + ',"' + sensitive + '","' + source + '","' + category + '","' + replaced + '"\n';
    });
    var stem = (data.file || 'replacements').replace(/\.[^.]+$/, '');
    var filename = stem + '_替换详情.csv';
    downloadBlob(csvContent, filename, 'text/csv');
    addLog('success', '替换详情已下载（共' + reps.length + '条）');
}
function downloadBlob(content, filename, mimeType) {
    var blob = new Blob([content], { type: mimeType + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
function uploadFile(file) {
    var MAX_FILE_SIZE = 20 * 1024 * 1024;
    var WARN_FILE_SIZE = 10 * 1024 * 1024;
    if (file.size > MAX_FILE_SIZE) {
        showToast('文件过大（' + (file.size / 1024 / 1024).toFixed(1) + 'MB），超过' + (MAX_FILE_SIZE / 1024 / 1024) + 'MB限制，请拆分后上传', true);
        return;
    }
    // 提取模式大文件锁：PDF≥5页或文本≥5000字
    if (currentMode === 'extract') {
        var ext = file.name.split('.').pop().toLowerCase();
        if (ext === 'pdf') {
            // PDF文件无法前端判断页数，交由后端拒绝
        } else if (['txt', 'md', 'csv', 'log'].indexOf(ext) !== -1) {
            // 文本类文件：读前5100字符快速判断
            var reader = new FileReader();
            reader.onload = function(e) {
                var text = e.target.result || '';
                if (text.length >= 5000) {
                    addLog('warning', '[' + file.name + '] 提取模式不支持大文件（文本≥5000字），请使用脱敏模式处理');
                    showToast('提取模式不支持大文件（文本≥5000字/PDF≥5页），请使用脱敏模式', true);
                    return;
                }
                _doUpload(file);
            };
            reader.readAsText(file, 'utf-8');
            return;
        }
    }
    _doUpload(file);
}
function _doUpload(file) {
    var WARN_FILE_SIZE = 10 * 1024 * 1024;
    if (file.size > WARN_FILE_SIZE) {
        addLog('warning', '[' + file.name + '] 文件较大（' + (file.size / 1024 / 1024).toFixed(1) + 'MB），处理可能耗时较长，建议拆分');
    }
    var formData = new FormData();
    formData.append('file', file);
    formData.append('mode', currentMode);
    fetch('/api/upload', {method: 'POST', body: formData})
    .then(function(r) {
        var ct = r.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
            throw new Error('服务器返回非JSON响应(HTTP ' + r.status + ')');
        }
        return r.json().then(function(data) { return {status: r.status, data: data}; });
    })
    .then(function(result) {
        var data = result.data;
        if (data.error) {
            if (result.status === 409) {
                showToast(data.error);
            } else {
                addLog('error', '[' + file.name + '] 上传失败: ' + data.error);
            }
        } else {
            var tid = data.task_id;
            if (data.is_large) {
                if (_largeTask.intervalId) { clearInterval(_largeTask.intervalId); _largeTask.intervalId = null; }
                window._currentExtractResult = null;
                currentResult = null;
                _currentDesensitizeData = null;
                if (data.mode && _resultByMode) { _resultByMode[data.mode] = null; }

                _largeTask.groupId = tid;
                _largeTask.queueId = tid;
                _largeTask.totalChunks = data.total_chunks || 1;
                enqueueWithId(tid, file.name, 'pending', '等待中 (0/' + (data.total_chunks || 1) + ')', data.mode, data.total_chunks || 1);
                addLog('info', '[' + file.name + '] 已拆分为 ' + (data.total_chunks || 1) + ' 个子任务');
                startLargeTaskPolling();
            } else {
                enqueueWithId(tid, file.name, 'pending', '等待中', data.mode);
                addLog('info', '[' + file.name + '] 已加入队列（第' + data.queue_size + '位）');
            }
        }
    })
    .catch(function(err) {
        addLog('error', '[' + file.name + '] 上传失败: ' + err.message);
    });
}
function showToast(msg, isError, isWarning) {
    settingsToast.textContent = msg;
    var cls = 'settings-toast show';
    if (isWarning) cls += ' warning';
    else if (isError) cls += ' error';
    settingsToast.className = cls;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function() { settingsToast.className = 'settings-toast'; }, 3000);
}
function markDirty() { _settingsDirty = true; }

function tryCloseSettings() {
    if (_settingsDirty) {
        if (!confirm('设置尚未保存，确定离开吗？')) return;
    }
    _settingsDirty = false;
    settingsOverlay.classList.remove('active');
}
function saveSettings() {
    settingsSave.disabled = true;
    settingsSave.textContent = '保存中...';
    var configBody = {
        server: {
            port: parseInt(document.getElementById('settingServerPort').value) || 5000
        },
        llm: {
            provider: document.getElementById('settingProvider').value,
            base_url: document.getElementById('settingBaseURL').value.trim(),
            api_key: document.getElementById('settingLMApiKey').value.trim(),
            model: document.getElementById('settingModel').value.trim(),
            max_tokens: parseInt(document.getElementById('settingMaxTokens').value) || 2048,
            temperature: parseFloat(document.getElementById('settingTemperature').value) || 0.3,
            timeout: parseInt(document.getElementById('settingTimeout').value) || 300,
            multimodal: document.getElementById('settingMultimodal').value === 'true',
            enable_thinking: document.getElementById('settingEnableThinking').value === 'true',
            reasoning_effort: null
        },
        desensitization: {
            placeholder: document.getElementById('settingPlaceholder').value.trim() || 'xxx',
            date_format: document.getElementById('settingDateFormat').value.trim() || 'YYYY年MM月DD日',
            depth: document.getElementById('settingDepth').value || 'standard'
        },
        extraction: {
            auto_merge: document.getElementById('settingAutoMerge').checked,
            docx_image_extract: document.getElementById('settingDocxImageExtract').checked,
            invoice_tolerance: parseFloat(document.getElementById('settingInvoiceTolerance').value) || 0.02,
            invoice_rules: {
                R1: document.getElementById('settingInvRuleR1').checked,
                R2: document.getElementById('settingInvRuleR2').checked,
                R3: document.getElementById('settingInvRuleR3').checked
            }
        }
    };
    var promptBody = {};
    var pf = document.getElementById('settingPromptFirst').value.trim();
    var ps = document.getElementById('settingPromptSecond').value.trim();
    if (pf) promptBody.first_pass = pf;
    if (ps) promptBody.second_pass = ps;
    var templates = window._templates || [];
    var body = {
        config: configBody,
        prompt: promptBody,
        templates: templates
    };
    fetch('/api/save_settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) { showToast('保存失败: ' + data.error, true); }
        else {
            _settingsDirty = false;
            showToast(data.message, false);
            loadProfiles();
            settingsOverlay.classList.remove('active');
        }
    })
    .catch(function(e) { showToast('保存失败: ' + e.message, true); })
    .finally(function() { settingsSave.disabled = false; settingsSave.textContent = '保存设置'; });
}
function _browseFolder(inputId, toastMsg) {
    try {
        if (typeof showDirectoryPicker === 'function') {
            showDirectoryPicker().then(function(handle) {
                document.getElementById(inputId).value = handle.name;
                showToast(toastMsg || '已选择文件夹', false);
            }).catch(function(err) {
                if (err.name !== 'AbortError') showToast('选择文件夹失败: ' + err.message, true);
            });
        } else {
            showToast('当前浏览器不支持文件夹选择，请手动输入完整路径', true);
        }
    } catch(e) {
        showToast('当前浏览器不支持文件夹选择，请手动输入完整路径', true);
    }
}
function renderHistory() {
    var isExtract = currentMode === 'extract';
    var list = isExtract ? extractionHistory : resultsHistory;
    var titleEl = document.querySelector('.history-panel-title');
    if (titleEl) titleEl.textContent = isExtract ? '提取历史记录' : '脱敏历史记录';
    if (list.length === 0) {
        historyList.innerHTML = '<div class="history-empty">暂无历史记录</div>';
        return;
    }
    var html = '';
    for (var i = 0; i < list.length; i++) {
        var h = list[i];
        var timeStr = '';
        if (h.process_time) {
            var sec = h.process_time;
            if (sec >= 60) {
                timeStr = Math.floor(sec / 60) + '分' + (sec % 60) + '秒';
            } else {
                timeStr = sec + '秒';
            }
        }
        var durationTag = timeStr ? '<span class="duration-tag">' + timeStr + '</span>' : '';
        if (isExtract) {
            var cnt = h.item_count || 0;
            html += '<div class="history-item" onclick="viewHistoryItem(' + i + ')">';
            html += '<div><div class="history-item-name">' + escapeHtml(h.file) + '</div>';
            html += '<div class="history-item-meta">' + (h.timestamp || '') + ' ' + durationTag + ' ' + cnt + '条明细</div></div>';
            html += '<span class="history-view-btn">查看</span></div>';
        } else {
            var reps = h.replacements || [];
            html += '<div class="history-item" onclick="viewHistoryItem(' + i + ')">';
            html += '<div><div class="history-item-name">' + escapeHtml(h.file) + '</div>';
            html += '<div class="history-item-meta">' + (h.timestamp || '') + ' ' + durationTag + ' 替换 ' + reps.length + ' 项 &middot; ' + (h.original_length || 0) + '字</div></div>';
            html += '<span class="history-view-btn">查看</span></div>';
        }
    }
    historyList.innerHTML = html;
}
function viewHistoryItem(index) {
    var isExtract = currentMode === 'extract';
    var list = isExtract ? extractionHistory : resultsHistory;
    var data = list[index];
    if (data) {
        if (isExtract) {
            displayExtractionResult(data);
            switchTab('extract');
        } else {
            displayResult(data);
            switchTab('desensitized');
        }
        historyOverlay.classList.remove('active');
    }
}
function switchTab(tabName) {
    var isExtractMode = document.body.classList.contains('mode-extract');
    if (isExtractMode && tabName !== 'extract') {
        resetExtractCompare();
    }
    document.querySelectorAll('.result-tab').forEach(function(t) {
        var name = t.getAttribute('data-tab');
        if (!isExtractMode) {
            if (name === 'extract' || name === 'merge') {
                t.style.display = 'none';
                t.classList.remove('active');
            } else {
                t.style.display = '';
                t.classList.toggle('active', name === tabName);
            }
        } else {
            if (name === 'desensitized' || name === 'replacements') {
                t.style.display = 'none';
                t.classList.remove('active');
            } else {
                t.style.display = '';
                t.classList.toggle('active', name === tabName);
            }
        }
    });
    document.querySelectorAll('.result-panel').forEach(function(p) {
        p.classList.toggle('active', p.id === tabName + 'Panel');
    });
    document.body.classList.toggle('tab-extract-active', isExtractMode && tabName === 'extract');
    document.body.classList.toggle('tab-merge-active', isExtractMode && tabName === 'merge');
    if (!isExtractMode) {
        document.body.classList.remove('tab-extract-active', 'tab-merge-active');
        var isRo = document.body.classList.contains('processing-readonly');
        if (tabName === 'original') {
            var hasOrig = originalPanel.querySelector('.result-empty') === null && originalPanel.innerHTML.trim() !== '';
            resultActions.innerHTML = hasOrig
                ? '<button class="download-btn" onclick="downloadOriginalText()">下载原文</button>'
                : '';
        } else if (tabName === 'desensitized') {
            var hasDesen = desensitizedPanel.querySelector('.result-empty') === null && desensitizedPanel.innerHTML.trim() !== '';
            resultActions.innerHTML = hasDesen
                ? '<button class="download-btn" onclick="saveEditedDesensitized(\'' + encodeURIComponent((currentResult || {}).output_file || '') + '\')" style="background:var(--success);margin-right:6px;">保存修改</button>' +
                  '<button class="download-btn" onclick="downloadCurrentTab()">下载</button>'
                : '';
        } else if (tabName === 'replacements') {
            var hasReps = replacementsPanel.querySelector('.result-empty') === null && replacementsPanel.innerHTML.trim() !== '';
            resultActions.innerHTML = hasReps
                ? '<button class="download-btn" onclick="downloadReplacementsExcel()">下载替换详情</button>'
                : '';
        }
    }
    if (isExtractMode && tabName === 'merge') {
        resultActions.innerHTML =
            '<div class="extract-actions" style="gap:4px;">' +
            '<select class="settings-select" id="sheetSelect" style="width:140px;display:inline-block;font-size:12px;padding:4px 8px;" onchange="switchSheet()"></select>' +
            '<button type="button" class="download-btn" onclick="newExcelSheet()">新建表</button>' +
            '<button type="button" class="download-btn" onclick="triggerImportExcel()" style="background:var(--gray-600);">导入Excel</button>' +
            '<button type="button" class="download-btn" onclick="renameSheet()" style="background:var(--gray-500);">改名</button>' +
            '<button type="button" class="download-btn" onclick="deleteSheet()" style="background:var(--error);">删除表</button>' +
            '<button type="button" class="download-btn" onclick="exportExcel()" style="background:var(--primary);">导出</button>' +
            '<span style="font-size:12px;color:var(--gray-400);line-height:28px;" id="mergeRowCount"></span></div>';
        refreshSheetDropdown();
    } else if (isExtractMode && tabName === 'extract' && window._currentExtractResult) {
        resultActions.innerHTML =
            '<div class="extract-actions">' +
            '<button type="button" class="download-btn" onclick="saveExtractOnly()" style="background:var(--primary);"' + (document.body.classList.contains('processing-readonly') ? ' disabled' : '') + '>保存修改</button>' +
            '<button type="button" class="download-btn" onclick="saveExtractAndSync()" style="background:var(--success);"' + (document.body.classList.contains('processing-readonly') ? ' disabled' : '') + '>添加到表</button>' +
            '<span class="help-badge" onclick="showMergeHelp()" style="cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:var(--gray-300);color:#666;font-size:11px;font-weight:700;margin-left:4px;" title="添加到表说明">?</span>' +
            '</div>';
    } else if (isExtractMode && tabName === 'original') {
        resultActions.innerHTML = '';
    } else if (isExtractMode) {
        resultActions.innerHTML = '';
    }
    if (isExtractMode && tabName === 'extract' && _mergeModified && window._currentExtractResult) {
        _mergeModified = false;
        loadMergePreview();
        Promise.all([
            fetch('/api/preview_excel').then(function(r){return r.json();}),
            fetch('/api/list_sheets').then(function(r){return r.json();})
        ]).then(function(results) {
            var d = results[0];
            var rows = d.rows || [];
            var keys = d.field_keys || [];
            var labels = d.field_labels || [];
            if (rows.length > 1 && window._currentExtractResult) {
                var sections = window._currentExtractResult.extract_field_sections || [];
                var headerKeys = [];
                var itemKeys = [];
                keys.forEach(function(k, i) {
                    if (sections[i] === 'header') headerKeys.push(k);
                    else itemKeys.push(k);
                });
                var header = {};
                var items = [];
                var fieldLabels = window._currentExtractResult.extract_field_labels || labels;
                for (var ri = 1; ri < rows.length; ri++) {
                    var item = {};
                    for (var ci = 0; ci < keys.length && ci < rows[ri].length; ci++) {
                        if (sections[ci] === 'header') {
                            header[keys[ci]] = rows[ri][ci];
                        } else {
                            item[keys[ci]] = rows[ri][ci];
                        }
                    }
                    items.push(item);
                }
                window._currentExtractResult.extract_header = header;
                window._currentExtractResult.extract_items = items;
                window._currentExtractResult.item_count = items.length;
                displayExtractionResult(window._currentExtractResult);
            }
        }).catch(function(e){});
    }
}
function _getDashDisplayMode() {
    var sel = document.getElementById('dashFilterSelect').value;
    if (sel === 'auto') return document.body.classList.contains('mode-extract');
    if (sel === 'extract') return true;
    return false;
}
