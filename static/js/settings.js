// settings.js
function loadTemplates(activeTemplateIndex) {
    fetch('/api/templates').then(function(r){return r.json();}).then(function(data){
        var sel = document.getElementById('settingTemplateSelect');
        var templates = data.templates || [];
        var oldListener = sel._templateChangeListener;
        if (oldListener) sel.removeEventListener('change', oldListener);
        sel.innerHTML = '';
        templates.forEach(function(t, i){
            var opt = document.createElement('option');
            opt.value = i;
            var prefix = (i === activeTemplateIndex) ? '[激活] ' : '';
            opt.textContent = prefix + (t.name || '未命名');
            sel.appendChild(opt);
        });
        var showIdx = (typeof activeTemplateIndex === 'number' && activeTemplateIndex >= 0) ? activeTemplateIndex : 0;
        sel.value = showIdx;
        renderTemplateFields(templates, showIdx);
        updateActiveTemplateHint(activeTemplateIndex);
        var listener = function(){
            var idx = parseInt(this.value);
            if (!isNaN(idx) && window._templates && window._templates[idx]) {
                renderTemplateFields(window._templates, idx);
                updateActiveTemplateHint(window._activeTemplateIndex);
            }
        };
        sel.addEventListener('change', listener);
        sel._templateChangeListener = listener;
        window._templates = templates;
        window._activeTemplateIndex = activeTemplateIndex;
    });
}
function updateActiveTemplateHint(activeIdx) {
    var hint = document.getElementById('activeTemplateHint');
    if (hint && window._templates && typeof activeIdx === 'number') {
        var current = document.getElementById('settingTemplateSelect').value;
        var selIdx = parseInt(current);
        if (selIdx === activeIdx) {
            hint.style.display = '';
            hint.textContent = '[激活] 当前激活模板：' + (window._templates[activeIdx] ? window._templates[activeIdx].name : '未命名') + '（提取结果和合成表将使用此模板字段）';
        } else {
            hint.style.display = '';
            hint.textContent = '当前查看模板：' + (window._templates[selIdx] ? window._templates[selIdx].name : '') + '，激活模板：' + (window._templates[activeIdx] ? window._templates[activeIdx].name : '') + ' — 切换后需点击「应用此模板」生效';
            hint.style.background = 'var(--warning-bg)';
            hint.style.color = '#92400e';
        }
    }
}
function renderTemplateFields(templates, idx) {
    var container = document.getElementById('templateFieldsContainer');
    var tpl = templates[idx];
    if (!tpl) { container.innerHTML = '<div style="color:var(--gray-400);font-size:13px;">请选择或新增模板</div>'; return; }
    var isSystem = tpl.is_system === true;
    var nameInput = document.getElementById('settingTemplateName');
    if (nameInput) {
        nameInput.value = tpl.name || '';
        nameInput.readOnly = isSystem;
        nameInput.style.background = isSystem ? 'var(--gray-100)' : '';
        var oldNameListener = nameInput._tplNameListener;
        if (oldNameListener) nameInput.removeEventListener('input', oldNameListener);
        if (!isSystem) {
            var nameListener = function(){
                if (window._templates && window._templates[idx]) {
                    window._templates[idx].name = nameInput.value;
                    var sel = document.getElementById('settingTemplateSelect');
                    if (sel && sel.options[idx]) {
                        sel.options[idx].textContent = nameInput.value || '未命名';
                    }
                }
                markDirty();
            };
            nameInput.addEventListener('input', nameListener);
            nameInput._tplNameListener = nameListener;
        }
    }
    var fields = tpl.fields || [];
    var html = '<div style="font-size:12px;font-weight:600;color:var(--gray-600);margin-bottom:6px;">';
    html += '字段列表 (' + fields.length + ' 个)';
    if (isSystem) html += ' <span style="color:var(--primary);font-weight:400;">— 系统模板（只读）</span>';
    html += '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr auto auto;gap:4px;font-size:12px;color:var(--gray-400);margin-bottom:4px;">' +
        '<span>中文标签</span><span>类型</span><span></span></div>';
    var ro = isSystem ? ' readonly' : '';
    var roStyle = isSystem ? 'background:var(--gray-50);color:var(--gray-600);' : '';
    var roSelect = isSystem ? ' disabled' : '';
    fields.forEach(function(f, fi){
        html += '<div style="display:grid;grid-template-columns:1fr auto auto;gap:4px;align-items:center;margin-bottom:3px;">' +
            '<input class="settings-input" style="font-size:12px;padding:4px 8px;' + roStyle + '" value="' + escapeHtml(f.label || '') + '" placeholder="字段名" data-fidx="' + fi + '" data-field="label"' + ro + '>' +
            '<select style="font-size:11px;padding:4px;border:1px solid var(--gray-300);border-radius:4px;' + roStyle + '" data-fidx="' + fi + '" data-field="section"' + roSelect + '>' +
            '<option value="header"' + (f.section === 'header' ? ' selected' : '') + '>抬头</option>' +
            '<option value="item"' + (f.section === 'item' ? ' selected' : '') + '>明细</option>' +
            '</select>';
        if (!isSystem) {
            html += '<button class="tpl-field-del-btn" data-fidx="' + fi + '" title="删除此字段">×</button>';
        } else {
            html += '<span></span>';
        }
        html += '</div>';
    });
    if (!isSystem) {
        html += '<button class="settings-btn-cancel" id="templateFieldAddBtn" style="width:100%;margin-top:4px;font-size:12px;">+ 添加字段</button>';
    } else {
        html += '<button class="settings-btn-primary" id="templateCopyBtn" style="width:100%;margin-top:8px;">复制此模板为可编辑版本</button>';
    }
    container.innerHTML = html;
    if (!isSystem) {
        container.querySelectorAll('input,select').forEach(function(el){
            el.addEventListener('change', function(){
                var fidx = parseInt(el.getAttribute('data-fidx'));
                var field = el.getAttribute('data-field');
                if (window._templates && window._templates[idx]) {
                    if (field === 'section') {
                        window._templates[idx].fields[fidx].section = el.value;
                    } else {
                        window._templates[idx].fields[fidx][field] = el.value;
                    }
                }
                markDirty();
            });
        });
        container.querySelectorAll('.tpl-field-del-btn').forEach(function(btn){
            btn.addEventListener('click', function(){
                var fidx = parseInt(this.getAttribute('data-fidx'));
                if (window._templates && window._templates[idx]) {
                    window._templates[idx].fields.splice(fidx, 1);
                    renderTemplateFields(window._templates, idx);
                }
                markDirty();
            });
        });
        var addBtn = document.getElementById('templateFieldAddBtn');
        if (addBtn) {
            addBtn.addEventListener('click', function(){
                if (window._templates && window._templates[idx]) {
                    window._templates[idx].fields.push({label:'', section:'item'});
                    renderTemplateFields(window._templates, idx);
                    markDirty();
                }
            });
        }
    }
    var copyBtn = document.getElementById('templateCopyBtn');
    if (copyBtn) {
        copyBtn.addEventListener('click', function(){
            var newName = (tpl.name || '模板') + ' (副本)';
            var copy = JSON.parse(JSON.stringify(tpl));
            copy.name = newName;
            delete copy.is_system;
            window._templates.push(copy);
            var sel = document.getElementById('settingTemplateSelect');
            var opt = document.createElement('option');
            opt.value = window._templates.length - 1;
            opt.textContent = newName;
            sel.appendChild(opt);
            sel.value = window._templates.length - 1;
            renderTemplateFields(window._templates, window._templates.length - 1);
            showToast('已复制模板: ' + newName);
        });
    }
}
function togglePromptFold() {
    var body = document.getElementById('promptFoldBody');
    var icon = document.getElementById('promptFoldIcon');
    if (body.style.display === 'none') {
        body.style.display = '';
        icon.textContent = '▼';
    } else {
        body.style.display = 'none';
        icon.textContent = '▶';
    }
}
function toggleCard(header) {
    var body = header.nextElementSibling;
    body.classList.toggle('collapsed');
    header.classList.toggle('collapsed');
}
function updatePromptVisibility() {
    var depth = document.getElementById('settingDepth').value;
    var secondGroup = document.getElementById('secondPassGroup');
    if (secondGroup) {
        secondGroup.style.display = (depth === 'deep') ? '' : 'none';
    }
}
function loadSettings() {
    Promise.all([
        fetch('/api/config').then(function(r) { return r.json(); }),
        fetch('/api/prompt').then(function(r) { return r.json(); })
    ]).then(function(results) {
        var cfg = results[0];
        var pcfg = results[1];
        var llm = cfg.llm || {};
        document.getElementById('settingProvider').value = llm.provider || 'lm_studio';
        document.getElementById('settingBaseURL').value = llm.base_url || 'http://127.0.0.1:1234/v1';
        document.getElementById('settingLMApiKey').value = llm.api_key || '';
        document.getElementById('settingModel').value = llm.model || '';
        document.getElementById('settingMaxTokens').value = llm.max_tokens || '2048';
        document.getElementById('settingTemperature').value = llm.temperature || '0.3';
        document.getElementById('settingTimeout').value = llm.timeout || '';
        document.getElementById('settingMultimodal').value = (llm.multimodal !== false) ? 'true' : 'false';
        document.getElementById('settingServerPort').value = cfg.server ? cfg.server.port : '5000';
        var et = llm.enable_thinking;
        document.getElementById('settingEnableThinking').value = (et === false || et === 'false') ? 'false' : 'true';
        updateCloudWarning();
        loadProfiles();
        document.getElementById('settingPlaceholder').value = cfg.desensitization.placeholder || 'xxx';
        document.getElementById('settingDateFormat').value = cfg.desensitization.date_format || 'YYYY年MM月DD日';
        document.getElementById('settingDepth').value = cfg.desensitization.depth || 'standard';
        updatePromptVisibility();
        document.getElementById('settingPromptFirst').value = pcfg.overrides.first_pass || pcfg.defaults.first_pass || '';
        document.getElementById('settingPromptSecond').value = pcfg.overrides.second_pass || pcfg.defaults.second_pass || '';
        document.getElementById('settingAutoMerge').checked = cfg.extraction ? cfg.extraction.auto_merge === true : false;
        var docxImgExtract = cfg.extraction ? cfg.extraction.docx_image_extract === true : false;
        document.getElementById('settingDocxImageExtract').checked = docxImgExtract;
        var invTol = cfg.extraction ? (cfg.extraction.invoice_tolerance !== undefined ? cfg.extraction.invoice_tolerance : 0.02) : 0.02;
        document.getElementById('settingInvoiceTolerance').value = invTol;
        document.getElementById('invoiceToleranceVal').textContent = Number(invTol).toFixed(2) + '元';
        var invRules = cfg.extraction ? cfg.extraction.invoice_rules : null;
        document.getElementById('settingInvRuleR1').checked = invRules ? invRules.R1 !== false : true;
        document.getElementById('settingInvRuleR2').checked = invRules ? invRules.R2 !== false : true;
        document.getElementById('settingInvRuleR3').checked = invRules ? invRules.R3 !== false : true;
        document.getElementById('docxImageWarning').style.display = docxImgExtract ? '' : 'none';
        var activeTplIdx = cfg.extraction ? cfg.extraction.active_template_index : 0;
        loadTemplates(typeof activeTplIdx === 'number' ? activeTplIdx : 0);
    }).catch(function(e) { showToast('加载配置失败: ' + e.message, true); });
}
function updateCloudWarning() {
    var p = document.getElementById('settingProvider').value;
    var warn = document.getElementById('cloudWarning');
    if (p === 'openai' || p === 'openai_compatible') {
        warn.style.display = '';
    } else {
        warn.style.display = 'none';
    }
}
function fillFormFromProfile(p) {
    document.getElementById('settingProvider').value = p.provider || 'lm_studio';
    document.getElementById('settingBaseURL').value = p.base_url || '';
    document.getElementById('settingLMApiKey').value = p.api_key || '';
    document.getElementById('settingModel').value = p.model || '';
    document.getElementById('settingMaxTokens').value = p.max_tokens || 2048;
    document.getElementById('settingTemperature').value = p.temperature || 0.3;
    document.getElementById('settingTimeout').value = p.timeout || 300;
    document.getElementById('settingMultimodal').value = (p.multimodal !== false) ? 'true' : 'false';
    document.getElementById('settingEnableThinking').value = (p.enable_thinking !== false) ? 'true' : 'false';
    updateCloudWarning();
}
function applyProfile() {
    var sel = document.getElementById('settingProfileSelect');
    if (!sel || !sel.value) { showToast('请先选择一个方案', true); return; }
    var profiles = window._llmProfiles || [];
    var p = profiles.find(function(x) { return x.name === sel.value; });
    if (!p) { showToast('方案不存在', true); return; }
    var isCloud = (p.provider === 'openai' || p.provider === 'openai_compatible');
    var doApply = function() {
        fillFormFromProfile(p);
        sel.value = '';
        markDirty();
        showToast('方案「' + p.name + '」已应用，表单已填充' + (isCloud ? '（云端）' : '') + '，请点击底部"保存设置"生效');
    };
    if (isCloud) {
        showCloudConfirm(function(confirmed) {
            if (confirmed) { doApply(); }
            else { sel.value = ''; showToast('已取消应用云端方案', true); }
        });
    } else {
        doApply();
    }
}
function showCloudConfirm(callback) {
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
    var box = document.createElement('div');
    box.style.cssText = 'background:#fff;border-radius:12px;max-width:460px;width:90%;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,0.25);';
    box.innerHTML = ''
        + '<div style="background:#dc2626;padding:20px 24px;color:#fff;">'
        + '<div style="font-size:20px;font-weight:bold;margin-bottom:4px;">云端大模型警告</div>'
        + '<div style="font-size:14px;opacity:0.9;">您正在应用云端服务配置，请仔细阅读</div>'
        + '</div>'
        + '<div style="padding:20px 24px;font-size:14px;color:#333;line-height:1.8;">'
        + '<p style="margin:0 0 12px;">此配置将使用<b style="color:#dc2626;">云端大模型</b>，您的文件<b style="color:#dc2626;">将被上传至第三方服务器</b>进行处理。</p>'
        + '<div style="background:#fff0f0;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin-bottom:12px;">'
        + '<div style="color:#dc2626;font-weight:bold;margin-bottom:6px;">请逐条确认：</div>'
        + '<div style="font-size:13px;color:#666;">- 文件中不含高度敏感的个人隐私、商业机密或涉密信息</div>'
        + '<div style="font-size:13px;color:#666;">- 我了解数据将离开本地环境传输至云端</div>'
        + '<div style="font-size:13px;color:#666;">- 建议先用 quick 模式预处理后再使用云端</div>'
        + '</div>'
        + '<p style="margin:0;font-size:13px;color:#999;">此警告旨在保护您的数据安全，请慎重选择。</p>'
        + '</div>'
        + '<div style="padding:16px 24px;display:flex;gap:10px;justify-content:flex-end;border-top:1px solid #e5e7eb;">'
        + '<button id="cloudCancelBtn" style="padding:10px 24px;border:1px solid #d1d5db;border-radius:8px;background:#fff;color:#666;font-size:14px;cursor:pointer;">取消</button>'
        + '<button id="cloudConfirmBtn" style="padding:10px 24px;border:none;border-radius:8px;background:#dc2626;color:#fff;font-size:14px;font-weight:bold;cursor:pointer;">我确认，使用云端服务</button>'
        + '</div>';
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    function cleanup() { document.body.removeChild(overlay); }
    document.getElementById('cloudCancelBtn').addEventListener('click', function(){ cleanup(); callback(false); });
    document.getElementById('cloudConfirmBtn').addEventListener('click', function(){ cleanup(); callback(true); });
    overlay.addEventListener('click', function(e){ if (e.target === overlay) { cleanup(); callback(false); } });
}

function saveProfile() {
    var name = prompt('请输入方案名称（如：公司OpenAI、家里Ollama）：');
    if (!name || !name.trim()) return;
    var profile = {
        name: name.trim(),
        provider: document.getElementById('settingProvider').value,
        base_url: document.getElementById('settingBaseURL').value.trim(),
        api_key: document.getElementById('settingLMApiKey').value.trim(),
        model: document.getElementById('settingModel').value.trim(),
        max_tokens: parseInt(document.getElementById('settingMaxTokens').value) || 2048,
        temperature: parseFloat(document.getElementById('settingTemperature').value) || 0.3,
        timeout: parseInt(document.getElementById('settingTimeout').value) || 300,
        multimodal: document.getElementById('settingMultimodal').value === 'true',
        enable_thinking: document.getElementById('settingEnableThinking').value === 'true'
    };
    var profiles = window._llmProfiles || [];
    var existing = profiles.findIndex(function(x) { return x.name === profile.name; });
    if (existing >= 0) {
        if (!confirm('方案「' + profile.name + '」已存在，覆盖吗？')) return;
        profiles[existing] = profile;
    } else {
        profiles.push(profile);
    }
    fetch('/api/llm_profiles', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profiles:profiles})})
    .then(function(r){return r.json();})
    .then(function(d){
        if (d.error) { showToast(d.error, true); return; }
        window._llmProfiles = d.profiles;
        refreshProfileDropdown();
        showToast('方案「' + profile.name + '」已保存');
    })
    .catch(function(e){ showToast('保存方案失败: ' + e.message, true); });
}
function deleteProfile() {
    var sel = document.getElementById('settingProfileSelect');
    var profiles = window._llmProfiles || [];
    if (!profiles.length) { showToast('没有可删除的方案', true); return; }
    var names = profiles.map(function(x) { return x.name; });
    var html = '<p style="margin-bottom:12px;">选择要删除的配置方案：</p>';
    for (var i = 0; i < names.length; i++) {
        html += '<label style="display:block;padding:8px 12px;margin:4px 0;border:1px solid var(--gray-200);border-radius:6px;cursor:pointer;font-size:14px;">';
        html += '<input type="radio" name="delProfile" value="' + escapeHtml(names[i]) + '"> ' + escapeHtml(names[i]);
        html += '</label>';
    }
    html += '<div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end;">';
    html += '<button class="settings-btn-cancel" onclick="closeModal()">取消</button>';
    html += '<button class="settings-btn-primary" id="delProfileConfirm" style="background:var(--error);">删除</button>';
    html += '</div>';
    showModal(html, '删除方案');
    document.getElementById('delProfileConfirm').addEventListener('click', function(){
        var sel2 = document.querySelector('input[name="delProfile"]:checked');
        if (!sel2) return;
        var name = sel2.value;
        var newProfiles = profiles.filter(function(x) { return x.name !== name; });
        fetch('/api/llm_profiles', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profiles:newProfiles})})
        .then(function(r){return r.json();})
        .then(function(d){
            if (d.error) { showToast(d.error, true); return; }
            window._llmProfiles = d.profiles;
            refreshProfileDropdown();
            showToast('方案「' + name + '」已删除');
            closeModal();
        })
        .catch(function(e){ showToast('删除失败: ' + e.message, true); });
    });
}
function refreshProfileDropdown() {
    var sel = document.getElementById('settingProfileSelect');
    if (!sel) return;
    var profiles = window._llmProfiles || [];
    sel.innerHTML = '<option value="">-- 选择方案 --</option>';
    profiles.forEach(function(p){
        var opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.name + ' (' + (p.provider || 'lm_studio') + ' | ' + (p.model || '?') + ')';
        sel.appendChild(opt);
    });
}
function loadProfiles() {
    fetch('/api/llm_profiles')
    .then(function(r){return r.json();})
    .then(function(d){
        window._llmProfiles = d.profiles || [];
        refreshProfileDropdown();
    })
    .catch(function(){});
}
