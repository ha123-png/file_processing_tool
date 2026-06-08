// extract.js
function syncZoomTransform() {
    var img = document.getElementById('zoomImage');
    var lbl = document.getElementById('zoomLevelLabel');
    if (lbl) lbl.textContent = Math.round(zoomLevel * 100) + '%';
    if (img) img.style.transform = 'scale(' + zoomLevel + ')';
}
function openImageZoom(url) {
    if (!url) return;
    var overlay = document.getElementById('zoomOverlay');
    var img = document.getElementById('zoomImage');
    if (!overlay || !img) return;
    img.src = url;
    img.onload = function() {
        // 计算自适应缩放：刚好填满屏幕不溢出
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var iw = img.naturalWidth || img.width;
        var ih = img.naturalHeight || img.height;
        if (iw && ih) {
            var fitScale = Math.min(vw / iw, vh / ih, 1);
            zoomLevel = Math.round(fitScale * 100) / 100;
        } else {
            zoomLevel = 1;
        }
        syncZoomTransform();
    };
    // 立即显示（可能用上次的 zoomLevel 先渲染，onload 后自动校准）
    zoomLevel = 1;
    syncZoomTransform();
    overlay.style.display = 'flex';
}
function closeImageZoom() {
    var overlay = document.getElementById('zoomOverlay');
    if (overlay) overlay.style.display = 'none';
}
function zoomIn() {
    zoomLevel = Math.min(zoomLevel * 1.5, 20);
    syncZoomTransform();
}
function zoomOut() {
    zoomLevel = Math.max(zoomLevel / 1.5, 0.1);
    syncZoomTransform();
}
function zoomReset() {
    zoomLevel = 1;
    syncZoomTransform();
}
function _initResizeHandle(wrap, left) {
    var handle = wrap.querySelector('.extract-resize-handle');
    if (!handle) return;
    var isDragging = false;
    handle.addEventListener('mousedown', function(e) {
        e.preventDefault();
        isDragging = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        var wrapRect = wrap.getBoundingClientRect();
        var pct = ((e.clientX - wrapRect.left) / wrapRect.width) * 100;
        pct = Math.max(20, Math.min(80, pct));
        left.style.width = pct + '%';
    });
    document.addEventListener('mouseup', function() {
        if (isDragging) {
            isDragging = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}
function toggleExtractCompare() {
    var wrap = document.getElementById('extractWrapper');
    var panel = document.getElementById('extractPanel');
    var left = document.getElementById('extractCompareLeft');
    if (!wrap || !panel || !left) return;
    var url = panel.getAttribute('data-orig-url');
    if (!url) return;
    if (wrap.classList.contains('extract-wrap--compare')) {
        resetExtractCompare();
        return;
    }
    left.innerHTML = '<div class="extract-compare-img-wrap"><img class="extract-compare-thumb" alt="原图" /></div>';
    var im = left.querySelector('.extract-compare-thumb');
    if (im) {
        im.src = url;
        im.addEventListener('click', function() { openImageZoom(url); });
    }
    left.style.width = '50%';
    var handle = document.createElement('div');
    handle.className = 'extract-resize-handle';
    wrap.insertBefore(handle, panel);
    wrap.classList.add('extract-wrap--compare');
    _initResizeHandle(wrap, left);
    var btn = document.getElementById('extractCompareBtn');
    if (btn) btn.textContent = '退出对照';
}
function doImportExcel(file, sheetName) {
    var fd = new FormData();
    fd.append('file', file);
    var url = '/api/import_excel';
    if (sheetName) url += '?sheet=' + encodeURIComponent(sheetName);
    fetch(url, { method: 'POST', body: fd })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var inp = document.getElementById('importExcelInput');
            if (inp) inp.value = '';
            if (d.error) { addLog('error', '导入失败: ' + d.error); return; }
            var msg = '已导入工作表: ' + d.sheet_name;
            if (sheetName) msg += ' (' + sheetName + ')';
            addLog('success', msg);
            loadMergePreview();
        })
        .catch(function(err) {
            var inp = document.getElementById('importExcelInput');
            if (inp) inp.value = '';
            addLog('error', '导入失败: ' + err.message);
        });
}
function showSheetPicker(file, sheets) {
    var html = '<p style="margin-bottom:12px;color:var(--gray-600);">检测到 ' + sheets.length + ' 个工作表，请选择要导入的 sheet：</p>';
    for (var i = 0; i < sheets.length; i++) {
        var checked = i === 0 ? ' checked' : '';
        html += '<label style="display:block;padding:8px 12px;margin:4px 0;border:1px solid var(--gray-200);border-radius:6px;cursor:pointer;font-size:14px;">';
        html += '<input type="radio" name="sheetRadio" value="' + escapeHtml(sheets[i]) + '"' + checked + ' style="margin-right:8px;">' + escapeHtml(sheets[i]);
        html += '</label>';
    }
    html += '<div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end;">';
    html += '<button class="settings-btn-cancel" onclick="closeModal(); var inp=document.getElementById(\'importExcelInput\'); if(inp) inp.value=\'\';">取消</button>';
    html += '<button class="settings-btn-primary" id="sheetPickerConfirm">确定导入</button>';
    html += '</div>';
    showModal(html, '选择工作表');
    document.getElementById('sheetPickerConfirm').addEventListener('click', function() {
        var sel = document.querySelector('input[name="sheetRadio"]:checked');
        if (!sel) return;
        closeModal();
        doImportExcel(file, sel.value);
    });
}
function triggerImportExcel() {
    var inp = document.getElementById('importExcelInput');
    if (inp) inp.click();
}
function initImageZoomAndCompare() {
    var overlay = document.getElementById('zoomOverlay');
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) closeImageZoom();
        });
    }
    var zc = document.getElementById('zoomClose');
    if (zc) zc.addEventListener('click', function(e) { e.stopPropagation(); closeImageZoom(); });
    var zoomImg = document.getElementById('zoomImage');
    if (zoomImg) zoomImg.addEventListener('click', function(e) { e.stopPropagation(); closeImageZoom(); });
    var zi = document.getElementById('zoomInBtn');
    var zo = document.getElementById('zoomOutBtn');
    var zr = document.getElementById('zoomResetBtn');
    if (zi) zi.addEventListener('click', function(e) { e.stopPropagation(); zoomIn(); });
    if (zo) zo.addEventListener('click', function(e) { e.stopPropagation(); zoomOut(); });
    if (zr) zr.addEventListener('click', function(e) { e.stopPropagation(); zoomReset(); });
    var ew = document.getElementById('extractWrapper');
    if (ew) {
        ew.addEventListener('click', function(e) {
            if (e.target.id === 'extractCompareBtn') {
                e.preventDefault();
                toggleExtractCompare();
            }
        });
    }
    var rs = document.getElementById('resultSection');
    if (rs) {
        rs.addEventListener('click', function(e) {
            var t = e.target;
            if (t && t.classList && t.classList.contains('extract-orig-preview-img')) {
                e.preventDefault();
                openImageZoom(t.src);
            }
        });
    }
    var importInp = document.getElementById('importExcelInput');
    if (importInp) {
        importInp.addEventListener('change', function() {
            if (!importInp.files || !importInp.files[0]) return;
            var file = importInp.files[0];
            var isXlsx = file.name.toLowerCase().endsWith('.xlsx');
            if (isXlsx) {
                var previewFd = new FormData();
                previewFd.append('file', file);
                fetch('/api/preview_xlsx_sheets', { method: 'POST', body: previewFd })
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.error) { addLog('error', '读取工作表列表失败: ' + d.error); importInp.value = ''; return; }
                        if (!d.multi_sheet && d.sheets && d.sheets.length === 1) {
                            doImportExcel(file);
                        } else {
                            showSheetPicker(file, d.sheets);
                        }
                    })
                    .catch(function(err) {
                        importInp.value = '';
                        addLog('error', '读取工作表列表失败: ' + err.message);
                    });
            } else {
                doImportExcel(file);
            }
        });
    }
}
function showMergeHelp() {
    showModal(
        '<div style="line-height:1.8;font-size:14px;">' +
        '<p><strong>保存修改</strong>：将当前编辑的内容保存到提取结果中（不写入合成表）。修改后可在历史记录中回看。</p>' +
        '<p><strong>添加到表</strong>：将当前提取结果合并到下方的合成表（Excel）。如果合成表已有同名列则匹配，遇到新列会自动添加。同一文件多次点到表会覆盖它之前的行（不会重复追加）。</p>' +
        '</div>',
        '添加到表说明'
    );
}
function getEditedItems() {
    var inputs = extractPanel.querySelectorAll('.extract-cell-input');
    var fieldKeys = (window._currentExtractResult && window._currentExtractResult.extract_field_keys) || [];
    var fieldSections = (window._currentExtractResult && window._currentExtractResult.extract_field_sections) || [];
    var header = {};
    var items = [];
    var itemMap = {};
    inputs.forEach(function(inp) {
        var row = parseInt(inp.getAttribute('data-row'));
        var key = inp.getAttribute('data-key');
        var section = inp.getAttribute('data-section');
        var val = inp.value;
        if (section === 'header') {
            header[key] = val;
        } else {
            if (!itemMap[row]) { itemMap[row] = {}; items.push(itemMap[row]); }
            itemMap[row][key] = val;
        }
    });
    return {header: header, items: items, item_count: items.length};
}
function autoVerifyInvoice() {
    var result = getEditedItems();
    var toleranceEl = document.getElementById('settingInvoiceTolerance');
    var tolerance = toleranceEl ? parseFloat(toleranceEl.value) : 0.02;
    var rules = {
        R1: document.getElementById('settingInvRuleR1') ? document.getElementById('settingInvRuleR1').checked : true,
        R2: document.getElementById('settingInvRuleR2') ? document.getElementById('settingInvRuleR2').checked : true,
        R3: document.getElementById('settingInvRuleR3') ? document.getElementById('settingInvRuleR3').checked : true
    };
    fetch('/api/validate_invoice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({items: result.items, header: result.header, tolerance: tolerance, rules: rules})
    })
    .then(function(r) { return r.json(); })
    .then(function(val) {
        if (!window._currentExtractResult) return;
        window._currentExtractResult.invoice_validation = val;
        displayExtractionResult(window._currentExtractResult);
        showToast('校对完成');
    })
    .catch(function(e) { showToast('校对失败: ' + e.message, true); });
}
function saveExtractOnly() {
    var result = getEditedItems();
    if (window._currentExtractResult) {
        window._currentExtractResult.extract_header = result.header;
        window._currentExtractResult.extract_items = result.items;
        window._currentExtractResult.item_count = result.item_count;
    }
    showToast('已保存提取结果');
}
function saveExtractAndSync() {
    if (!window._currentExtractResult) { addLog('error', '无提取结果'); return; }
    var data = window._currentExtractResult;
    var header = data.extract_header || {};
    var items = data.extract_items || [];
    var filename = data.file || '';

    if (!filename) {
        addLog('error', '无法获取文件名，请重新提取');
        return;
    }

    fetch('/api/update_file_rows', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filename: filename, header: header, items: items})
    }).then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { addLog('error', '保存失败: ' + d.error); return; }
        addLog('success', '已保存 — 提取结果已同步更新到合成表');
        loadMergePreview();
    }).catch(function(e){
        addLog('error', '保存失败: ' + e.message);
    });
}
function exportExcel() {
    var dirtyCells = document.querySelectorAll('#mergeTable .merge-cell[data-dirty="1"]');
    if (dirtyCells.length) {
        addLog('info', '正在保存修改...');
        _flushDirtyCells().then(function() {
            _doExportExcel();
        });
    } else {
        _doExportExcel();
    }
}
function _flushDirtyCells() {
    var dirtyCells = document.querySelectorAll('#mergeTable .merge-cell[data-dirty="1"]');
    if (!dirtyCells.length) return Promise.resolve();
    var cells = [];
    dirtyCells.forEach(function(inp){
        cells.push({
            row_index: parseInt(inp.getAttribute('data-row')),
            col_index: parseInt(inp.getAttribute('data-col')),
            value: inp.value
        });
        delete inp.dataset.dirty;
    });
    return fetch('/api/excel_batch_update', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({cells: cells})
    }).then(function(r){return r.json();}).then(function(d){
        if (d.error) addLog('error', '保存失败: ' + d.error);
    }).catch(function(e){addLog('error', '保存失败: ' + e.message);});
}
function _doExportExcel() {
    fetch('/api/list_sheets').then(function(r){return r.json();}).then(function(sheetsData){
        var defName = sheetsData.active || '提取结果';
        var name = prompt('导出文件名（可留空使用当前表名，无需加 .xlsx）:', defName);
        if (name === null) return;
        name = (name || defName).trim();
        fetch('/api/export_excel', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filename: name })
        }).then(function(r){return r.json();})
        .then(function(d){
            if (d.error) { addLog('error', '导出失败: ' + d.error); }
            else {
                addLog('success', 'Excel已导出: ' + d.filename);
                var link = document.createElement('a');
                link.href = '/api/download/' + encodeURIComponent(d.filename);
                link.download = d.filename;
                link.click();
            }
        })
        .catch(function(e){addLog('error', '导出失败: ' + e.message);});
    }).catch(function(e){addLog('error', '获取表名失败: ' + e.message);});
}
function newExcelSheet() {
    fetch('/api/new_excel_session', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})
    .then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { addLog('error', d.error); return; }
        addLog('info', '已创建新表: ' + d.sheet_name);
        refreshSheetDropdown();
        loadMergePreview();
    })
    .catch(function(e){addLog('error', '创建失败: ' + e.message);});
}
function renameSheet() {
    var sel = document.getElementById('sheetSelect');
    if (!sel || !sel.value) return;
    var old = sel.value;
    var newName = prompt('请输入新表名:', old);
    if (!newName || newName === old) return;
    fetch('/api/rename_sheet', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({old_name:old, new_name:newName})})
    .then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { addLog('error', d.error); return; }
        addLog('info', '表已重命名');
        refreshSheetDropdown();
        loadMergePreview();
    })
    .catch(function(e){addLog('error', '重命名失败: ' + e.message);});
}
function deleteSheet() {
    var sel = document.getElementById('sheetSelect');
    if (!sel || !sel.value) return;
    var name = sel.value;
    if (!confirm('确定要删除表「' + name + '」吗？此操作不可撤销。')) return;
    fetch('/api/delete_sheet', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})})
    .then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { addLog('error', d.error); return; }
        addLog('info', '表已删除: ' + name);
        refreshSheetDropdown();
        loadMergePreview();
    })
    .catch(function(e){addLog('error', '删除失败: ' + e.message);});
}
function refreshSheetDropdown() {
    fetch('/api/list_sheets').then(function(r){return r.json();}).then(function(d){
        var sel = document.getElementById('sheetSelect');
        if (!sel) return;
        var cur = sel.value;
        sel.innerHTML = '';
        (d.sheets || []).forEach(function(s){
            var opt = document.createElement('option');
            opt.value = s; opt.textContent = s;
            if (s === d.active) opt.selected = true;
            sel.appendChild(opt);
        });
        if (_urlSheetParam && d.sheets && d.sheets.indexOf(_urlSheetParam) >= 0 && _urlSheetParam !== d.active) {
            var toSwitch = _urlSheetParam;
            _urlSheetParam = null;
            fetch('/api/switch_sheet', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name: toSwitch})})
            .then(function(r){return r.json();})
            .then(function(d2){ addLog('info', 'URL参数自动切换: ' + toSwitch); loadMergePreview(); });
        }
    });
}
function switchSheet() {
    var sel = document.getElementById('sheetSelect');
    if (!sel) return;
    var name = sel.value;
    if (!name) return;
    fetch('/api/switch_sheet', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})})
    .then(function(r){return r.json();})
    .then(function(d){
        addLog('info', '已切换到: ' + name);
        loadMergePreview();
    })
    .catch(function(e){addLog('error', '切换失败: ' + e.message);});
}
function addMergeRow() {
    var table = document.getElementById('mergeTable');
    if (!table) { addLog('error', '表格未加载'); return; }
    var tbody = table.querySelector('tbody');
    var visibleCnt = tbody ? Array.from(tbody.querySelectorAll('tr')).filter(function(r){ return r.style.display !== 'none'; }).length : 0;
    if (visibleCnt >= PAGE_SIZE) {
        _flushDirtyCells().then(function(){
            fetch('/api/excel_add_row', {method:'POST'}).then(function(r){return r.json();}).then(function(d){
                if (d.error) { addLog('error', d.error); return; }
                loadMergePreview(_mergeTotalPages + 1);
            });
        });
        return;
    }
    var nextRow = _mergeTotalRows + 1;
    var labels = window._mergeState ? window._mergeState.labels : [];
    var isRo = document.body.classList.contains('processing-readonly');
    var tr = document.createElement('tr');
    tr.setAttribute('data-merge-row', nextRow);
    tr.innerHTML = '<td><input type="checkbox" class="merge-row-cb" value="' + nextRow + '"' + (isRo ? ' disabled' : '') + '></td>';
    for (var ci = 0; ci < labels.length; ci++) {
        tr.innerHTML += '<td><input class="extract-cell-input merge-cell" value="" data-row="' + nextRow + '" data-col="' + (ci+1) + '" data-dirty="1"></td>';
    }
    tbody.appendChild(tr);
    _mergeTotalRows++;
    var rcEl = document.getElementById('mergeRowCount');
    if (rcEl) rcEl.textContent = '共 ' + _mergeTotalRows + ' 条';
    tr.querySelectorAll('.merge-cell').forEach(function(inp){
        inp.addEventListener('change', function(){
            this.dataset.dirty = '1';
            _scheduleMergeAutoSave();
        });
    });
    fetch('/api/excel_add_row', {method:'POST'}).then(function(r){return r.json();}).then(function(d){
        if (d.error) { addLog('error', d.error); }
    }).catch(function(){});
    addLog('info', '已新增一行');
}
function toggleFilterColumn(ci) {
    var key = 'col_' + ci;
    if (_filterState[key]) delete _filterState[key];
    else _filterState[key] = true;
    renderMergeFiltered();
}
function renderMergeFiltered() {
    var state = window._mergeState;
    if (!state) return;
    var hiddenCols = {};
    for (var k in _filterState) { if (_filterState[k]) hiddenCols[k] = true; }
    var visibleLabels = [];
    var visibleIndices = [];
    for (var i = 0; i < state.labels.length; i++) {
        if (!hiddenCols['col_' + i]) {
            visibleLabels.push(state.labels[i]);
            visibleIndices.push(i);
        }
    }
    var html = '<div style="margin-bottom:8px;display:flex;gap:4px;flex-wrap:wrap;align-items:center;">';
    for (var i = 0; i < state.labels.length; i++) {
        var checked = !hiddenCols['col_' + i];
        html += '<label style="font-size:11px;display:flex;align-items:center;gap:3px;cursor:pointer;padding:2px 6px;background:' + (checked ? 'var(--primary-bg)' : 'var(--gray-100)') + ';border-radius:4px;">' +
            '<input type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="toggleFilterColumn(' + i + ')" style="width:12px;height:12px;accent-color:var(--primary);">' +
            escapeHtml(state.labels[i]) + '</label>';
    }
    html += '<button class="download-btn" onclick="exportFilteredExcel()" style="font-size:11px;padding:3px 10px;background:var(--primary);">导出筛选视图</button></div>';
    if (visibleIndices.length === 0) {
        html += '<div style="padding:20px;text-align:center;color:var(--gray-400);">未选择任何字段</div>';
    } else {
        html += '<div class="table-scroll-wrap"><table class="extract-full-table" id="filteredTable" style="font-size:12px;"><thead><tr>';
        visibleLabels.forEach(function(l){ html += '<th>' + escapeHtml(l) + '</th>'; });
        html += '</tr></thead><tbody>';
        var previewLimit = Math.min(6, state.rows.length);
        for (var ri = 1; ri < previewLimit; ri++) {
            html += '<tr>';
            visibleIndices.forEach(function(ci){
                var val = state.rows[ri][ci] || '';
                html += '<td style="padding:6px 8px;">' + escapeHtml(val) + '</td>';
            });
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        var totalDataRows = state.rows.length - 1;
        html += '<div style="font-size:12px;color:var(--gray-400);margin-top:6px;">预览前 <strong>' + (previewLimit - 1) + '</strong> 行，共 <strong>' + totalDataRows + '</strong> 条记录</div>';
    }
    var fp = document.getElementById('filteredPreview');
    if (fp) { fp.innerHTML = html; enableResizableColumns('#filteredTable'); }
}
function exportFilteredExcel() {
    var state = window._mergeState;
    if (!state || state.rows.length <= 1) { addLog('warning', '没有数据可导出'); return; }
    var hiddenCols = {};
    for (var k in _filterState) { if (_filterState[k]) hiddenCols[k] = true; }
    var visibleLabels = [];
    var visibleIndices = [];
    for (var i = 0; i < state.labels.length; i++) {
        if (!hiddenCols['col_' + i]) {
            visibleLabels.push(state.labels[i]);
            visibleIndices.push(i);
        }
    }
    if (visibleLabels.length === 0) { addLog('warning', '请至少选择一个字段'); return; }
    var visibleRows = [];
    for (var ri = 1; ri < state.rows.length; ri++) {
        var row = [];
        for (var vi = 0; vi < visibleIndices.length; vi++) {
            row.push(state.rows[ri][visibleIndices[vi]] || '');
        }
        visibleRows.push(row);
    }
    fetch('/api/export_filtered_excel', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ labels: visibleLabels, rows: visibleRows, sheet_name: state.activeSheet || '筛选结果' })
    }).then(function(r){return r.json();}).then(function(d){
        if (d.error) { addLog('error', '导出失败: ' + d.error); return; }
        var link = document.createElement('a');
        link.href = '/api/download/' + encodeURIComponent(d.filename);
        link.download = d.filename;
        link.click();
        addLog('info', '已导出XLSX: ' + d.filename);
    }).catch(function(e){addLog('error', '导出失败: ' + e.message);});
}
function loadMergePreview(page) {
    if (page === undefined) { _mergePage = 1; page = 1; }
    else { _mergePage = page; }
    page = page || _mergePage;
    _flushDirtyCells().then(function() {
    var url = '/api/preview_excel?page=' + page + '&page_size=' + PAGE_SIZE;
    Promise.all([
        fetch(url).then(function(r){return r.json();}),
        fetch('/api/list_sheets').then(function(r){return r.json();})
    ]).then(function(results) {
        var d = results[0];
        var sheets = results[1];
        var rows = d.rows || [];
        var keys = d.field_keys || [];
        var labels = d.field_labels || [];
        _mergePage = d.page || page;
        _mergeTotalPages = d.total_pages || 1;
        _mergeTotalRows = d.total_rows || 0;
        window._mergeState = {rows: rows, keys: keys, labels: labels, activeSheet: sheets.active, total_rows: _mergeTotalRows};
        var rcEl = document.getElementById('mergeRowCount');
        if (rcEl) rcEl.textContent = '共 ' + _mergeTotalRows + ' 条';
        var isRo = document.body.classList.contains('processing-readonly');
        if (_mergePage > _mergeTotalPages && _mergeTotalPages > 0) {
            loadMergePreview(_mergeTotalPages);
            return;
        }
        if (!rows.length || rows.length <= 1) {
            mergePanel.innerHTML = '<div class="result-empty" style="padding:30px 0;"><div class="result-empty-text">暂无合成数据</div></div>';
            refreshSheetDropdown();
            return;
        }
        var html = '<div style="margin-bottom:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">';
        if (!isRo) {
            html += '<button type="button" class="download-btn" onclick="deleteSelectedRows()" style="background:var(--error);">删除选中</button>' +
                '<button type="button" class="download-btn" onclick="addMergeRow()" style="background:var(--success);">新增一行</button>';
            html += '<button type="button" class="download-btn" onclick="showFilteredView()" style="background:var(--gray-500);">字段筛选</button>';
        }
        html += '</div>';
        html += '<div class="table-scroll-wrap"><table class="extract-full-table" id="mergeTable" style="font-size:12px;"><thead><tr>' +
            '<th style="width:28px;"><input type="checkbox" id="mergeSelectAll" onchange="toggleAllMergeRows(this)"' + (isRo ? ' disabled' : '') + '></th>';
        for (var i = 0; i < labels.length; i++) {
            html += '<th>' + escapeHtml(labels[i]) + '</th>';
        }
        html += '</tr></thead><tbody>';
        var baseIndex = (_mergePage - 1) * PAGE_SIZE;
        for (var ri = 1; ri < rows.length; ri++) {
            var realRow = baseIndex + ri;
            html += '<tr data-merge-row="' + realRow + '">';
            html += '<td><input type="checkbox" class="merge-row-cb" value="' + realRow + '"' + (isRo ? ' disabled' : '') + '></td>';
            for (var ci = 0; ci < rows[ri].length && ci < labels.length; ci++) {
                var val = rows[ri][ci] || '';
                if (isRo) {
                    html += '<td style="padding:6px 8px;font-size:12px;">' + escapeHtml(val) + '</td>';
                } else {
                    html += '<td><input class="extract-cell-input merge-cell" value="' + escapeHtml(val) + '" data-row="' + realRow + '" data-col="' + (ci+1) + '"></td>';
                }
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';

        if (_mergeTotalPages > 1) {
            html += '<div style="display:flex;justify-content:center;align-items:center;gap:6px;margin-top:10px;flex-wrap:wrap;">';
            html += '<button class="history-btn" onclick="loadMergePreview(1)"' + (_mergePage <= 1 ? ' disabled' : '') + '>首页</button>';
            html += '<button class="history-btn" onclick="loadMergePreview(' + (_mergePage - 1) + ')"' + (_mergePage <= 1 ? ' disabled' : '') + '>上一页</button>';
            var pageStart = Math.max(1, _mergePage - 2);
            var pageEnd = Math.min(_mergeTotalPages, _mergePage + 2);
            for (var pi = pageStart; pi <= pageEnd; pi++) {
                html += '<button class="history-btn" onclick="loadMergePreview(' + pi + ')" style="' + (pi === _mergePage ? 'background:var(--primary);color:white;border-color:var(--primary);' : '') + '">' + pi + '</button>';
            }
            html += '<button class="history-btn" onclick="loadMergePreview(' + (_mergePage + 1) + ')"' + (_mergePage >= _mergeTotalPages ? ' disabled' : '') + '>下一页</button>';
            html += '<button class="history-btn" onclick="loadMergePreview(' + _mergeTotalPages + ')"' + (_mergePage >= _mergeTotalPages ? ' disabled' : '') + '>末页</button>';
            html += '<span style="font-size:12px;color:var(--gray-400);margin:0 4px;">第</span>';
            html += '<input type="number" id="mergeJumpPage" value="' + _mergePage + '" min="1" max="' + _mergeTotalPages + '" style="width:50px;padding:4px 6px;border:1px solid var(--gray-300);border-radius:4px;font-size:12px;text-align:center;" onkeydown="if(event.key===\'Enter\')jumpMergePage()">';
            html += '<span style="font-size:12px;color:var(--gray-400);">/ ' + _mergeTotalPages + ' 页</span>';
            html += '<button class="history-btn" onclick="jumpMergePage()">跳转</button>';
            html += '</div>';
        }

        mergePanel.innerHTML = html;
        if (!isRo) {
              mergePanel.querySelectorAll('.merge-cell').forEach(function(inp){
                  inp.addEventListener('change', function(){
                      this.dataset.dirty = '1';
                      _scheduleMergeAutoSave();
                  });
              });
              enableResizableColumns('#mergeTable');
          }
        refreshSheetDropdown();
    })
    .catch(function(e){addLog('error', '加载合成表异常: ' + e.message);});
    });
}
function jumpMergePage() {
    var inp = document.getElementById('mergeJumpPage');
    if (!inp) return;
    var p = parseInt(inp.value);
    if (isNaN(p) || p < 1) p = 1;
    if (p > _mergeTotalPages) p = _mergeTotalPages;
    loadMergePreview(p);
}
function showFilteredView() {
    _flushDirtyCells().then(function() {
    addLog('info', '正在加载全量数据...');
    fetch('/api/preview_excel')
    .then(function(r){return r.json();})
    .then(function(d){
        var rows = d.rows || [];
        var keys = d.field_keys || [];
        var labels = d.field_labels || [];
        if (!rows.length || rows.length <= 1) { addLog('warning', '没有数据'); return; }
        fetch('/api/list_sheets').then(function(r){return r.json();}).then(function(sheets){
            window._mergeState = {rows: rows, keys: keys, labels: labels, activeSheet: sheets.active, total_rows: d.total_rows || 0};
            var html = '<div id="filteredPreview"></div>';
            showModal(html, '字段筛选 - ' + (sheets.active || ''));
            renderMergeFiltered();
        });
    })
    .catch(function(e){ addLog('error', '加载数据失败: ' + e.message); });
    });
}
function toggleAllMergeRows(cb) {
    document.querySelectorAll('.merge-row-cb').forEach(function(c){c.checked = cb.checked;});
}
function deleteSelectedRows() {
    var checked = document.querySelectorAll('.merge-row-cb:checked');
    if (!checked.length) { addLog('warning', '请先勾选要删除的行'); return; }
    var indices = [];
    checked.forEach(function(cb){
        var tr = cb.closest('tr');
        if (tr) tr.style.display = 'none';
        indices.push(parseInt(cb.value));
    });
    _mergeTotalRows -= indices.length;
    var rcEl = document.getElementById('mergeRowCount');
    if (rcEl) rcEl.textContent = '共 ' + _mergeTotalRows + ' 条';
    fetch('/api/excel_batch_delete_rows', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({row_indices: indices})
    }).then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { addLog('error', '删除失败: ' + d.error); return; }
        addLog('info', d.message);
        var tbody = document.querySelector('#mergeTable tbody');
        var anyVisible = tbody && Array.from(tbody.querySelectorAll('tr')).some(function(tr){ return tr.style.display !== 'none'; });
        if (!anyVisible) { loadMergePreview(_mergePage > 1 ? _mergePage - 1 : 1); }
    }).catch(function(e){ addLog('error', '删除失败: ' + e.message); });
}
function enableResizableColumns(tableSelector) {
    var tables = document.querySelectorAll(tableSelector);
    tables.forEach(function(table) {
        var headers = table.querySelectorAll('th');
        headers.forEach(function(th) {
            if (th.querySelector('.col-resize-handle')) return;
            var handle = document.createElement('div');
            handle.className = 'col-resize-handle';
            th.style.position = 'relative';
            handle.style.cssText = 'position:absolute;right:0;top:0;bottom:0;width:5px;cursor:col-resize;z-index:5;';
            th.appendChild(handle);
            var startX = 0, startWidth = 0;
            handle.addEventListener('mousedown', function(e) {
                e.preventDefault();
                e.stopPropagation();
                startX = e.clientX;
                startWidth = th.getBoundingClientRect().width;
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                function onMove(ev) {
                    var diff = ev.clientX - startX;
                    var newWidth = Math.max(40, startWidth + diff);
                    th.style.width = newWidth + 'px';
                    th.style.minWidth = newWidth + 'px';
                    var sameHeaders = table.querySelectorAll('th:nth-child(' + (Array.from(th.parentNode.children).indexOf(th) + 1) + ')');
                    sameHeaders.forEach(function(h) {
                        h.style.width = newWidth + 'px';
                        h.style.minWidth = newWidth + 'px';
                    });
                }
                function onUp() {
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                }
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
        });
    });
}
function enableExtractResize() {
    var labels = document.querySelectorAll('.extract-header-label');
    if (!labels.length) return;
    var firstLabel = labels[0];
    if (firstLabel.querySelector('.ext-resize-handle')) return;
    var currentLabelWidth = firstLabel.getBoundingClientRect().width;
    labels.forEach(function(lbl) {
        var handle = document.createElement('div');
        handle.className = 'ext-resize-handle';
        handle.style.cssText = 'position:absolute;right:-1px;top:0;bottom:0;width:6px;cursor:col-resize;z-index:10;';
        lbl.style.position = 'relative';
        lbl.appendChild(handle);
        var startX = 0, startWidth = 0;
        var onResizeStart = function(e) {
            e.preventDefault();
            e.stopPropagation();
            startX = e.clientX;
            startWidth = currentLabelWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onResizeMove);
            document.addEventListener('mouseup', onResizeUp);
        };
        var onResizeMove = function(ev) {
            var diff = ev.clientX - startX;
            var newWidth = Math.max(80, startWidth + diff);
            currentLabelWidth = newWidth;
            document.querySelectorAll('.extract-header-label').forEach(function(l) {
                l.style.width = newWidth + 'px';
            });
        };
        var onResizeUp = function() {
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onResizeMove);
            document.removeEventListener('mouseup', onResizeUp);
        };
        handle.addEventListener('mousedown', onResizeStart);
    });
}
function _resetMergeState() {
    window._mergeState = null;
    _mergePage = 1;
    _mergeTotalRows = 0;
    _mergeModified = false;
    if (_mergeAutoSaveTimer) { clearTimeout(_mergeAutoSaveTimer); _mergeAutoSaveTimer = null; }
}
