// One material selection, existing submissions, server-side history grouped by paper.
const labels = {review: '规范与逻辑', novelty: '创新性初判', experiments: '实验材料'};
const uploadedFiles = new WeakMap(), reportChoices = new Map();
let groups = [], selectedPaper = null, currentTab = 'review', lastView = null, refreshing = false;

function selectedChecks() {
    return Object.keys(labels).filter(check => $('#check-' + check).checked);
}
function showOptions() {
    $('#review-options').hidden = !$('#check-review').checked;
    $('#novelty-options').hidden = !$('#check-novelty').checked;
    $('#experiment-options').hidden = !$('#check-experiments').checked;
}
for (const check of Object.keys(labels)) $('#check-' + check).onchange = showOptions;
$('#files').onchange = () => { if ($('#files').files.length) $('#paper-existing').value = ''; };
$('#paper-existing').onchange = () => { if ($('#paper-existing').value) $('#files').value = ''; };

async function upload(files, role) {
    const ids = [];
    for (const file of files) {
        let saved = uploadedFiles.get(file);
        if (!saved) { saved = {}; uploadedFiles.set(file, saved); }
        if (!saved[role]) {
            $('#upload-status').textContent = '正在保存 ' + file.name;
            const form = new FormData(); form.append('file', file); form.append('role', role);
            saved[role] = (await api('/documents', {method: 'POST', body: form})).id;
        }
        ids.push(saved[role]);
    }
    $('#upload-status').textContent = '';
    return ids;
}
async function loadDocuments() {
    const documents = await api('/documents');
    const chosen = $('#paper-existing').value;
    $('#paper-existing').innerHTML = '<option value="">选择已有论文，或上传新文件</option>' + documents
        .filter(d => d.role === 'primary').map(d => `<option value="${esc(d.id)}">${esc(d.filename)}</option>`).join('');
    $('#paper-existing').value = chosen;
    const checked = new Set([...document.querySelectorAll('#saved-policies input:checked')].map(e => e.value));
    $('#saved-policies').innerHTML = documents.filter(d => d.role === 'policy').map(d =>
        `<label class="check"><input type="checkbox" value="${esc(d.id)}" ${checked.has(d.id) ? 'checked' : ''}>${esc(d.filename)} <small>已保存</small></label>`).join('');
}
$('#review-form').onsubmit = async event => {
    event.preventDefault();
    $('#submit').disabled = true;
    const submitted = [];
    let prepared = false;
    try {
        if (!modelAvailable) throw new Error('评审模型暂不可用，请稍后重试。');
        const checks = selectedChecks(), files = $('#files').files;
        if (!checks.length) throw new Error('请至少选择一项审查。');
        if (!files.length && !$('#paper-existing').value) throw new Error('请上传论文文件或选择已有论文。');
        const supplemental = checks.includes('novelty') || checks.includes('experiments');
        if (supplemental && files.length > 1) throw new Error('创新性与实验材料审查每次需要一份论文。');
        const queries = checks.includes('novelty') ? $('#audit-queries').value.split('\n').map(q => q.trim()).filter(Boolean) : [];
        const quote = $('#experiment-quote').value.trim();
        if (checks.includes('novelty') && (!queries.length || queries.length > 3 || queries.some(q => q.length < 2 || q.length > 300)))
            throw new Error('请填写 1–3 条公开查询，每条 2–300 字符。');
        if (checks.includes('novelty') && !$('#audit-approved').checked) throw new Error('请先批准公开查询。');
        if (checks.includes('experiments') && !quote) throw new Error('请填写实验对应的论文原文片段。');
        const ids = files.length ? await upload(files, 'primary') : [$('#paper-existing').value];
        prepared = true;
        selectedPaper = ids[0];
        currentTab = checks[0];
        const choices = reportChoices.get(selectedPaper) || {};
        reportChoices.set(selectedPaper, choices);
        if (checks.includes('review')) {
            const policies = [...document.querySelectorAll('#saved-policies input:checked')].map(e => e.value);
            policies.push(...await upload($('#policies').files, 'policy'));
            const job = await post('/jobs', {document_ids: ids, policy_ids: [...new Set(policies)],
                material_type: $('#material').value, degree: $('#degree').value, language: $('#language').value,
                custom_prompt: $('#prompt').value, model_mode: 'local'});
            choices.review = job.id; submitted.push(labels.review);
        }
        if (supplemental) {
            const task = await post('/audits', {document_id: ids[0], model_mode: 'local', degree: $('#degree').value,
                public_queries: queries, search_approved: checks.includes('novelty') && $('#audit-approved').checked,
                literature_cutoff: checks.includes('novelty') ? $('#audit-cutoff').value || null : null,
                experiments: checks.includes('experiments') ? [{id: 'E01', name: $('#experiment-name').value,
                    paper_quote: quote, material_ids: [...materialIds]}] : []});
            for (const check of checks.filter(c => c !== 'review')) choices[check] = task.id;
            submitted.push(...checks.filter(c => c !== 'review').map(c => labels[c]));
        }
        currentTab = checks[0]; lastView = null;
        notify('已提交：' + submitted.join('、'));
    } catch (error) {
        notify((submitted.length ? '已提交' + submitted.join('、') + '；后续提交失败：' : '') + error.message);
    } finally {
        $('#submit').disabled = !modelAvailable;
        if (prepared) {
            await loadDocuments().catch(error => notify(error.message));
            await refresh().catch(error => notify(error.message));
        }
    }
};

async function renderSelection() {
    const group = groups.find(g => g.document_id === selectedPaper);
    $('#report-paper').textContent = group ? group.title : '';
    document.querySelectorAll('[data-tab]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.tab === currentTab)));
    $('#report').setAttribute('aria-labelledby', 'tab-' + currentTab);
    const tasks = group ? group.tasks.filter(task => task.checks.includes(currentTab)) : [];
    const choices = reportChoices.get(selectedPaper) || {};
    reportChoices.set(selectedPaper, choices);
    const task = tasks.find(task => task.id === choices[currentTab]) || tasks[0];
    const view = `${selectedPaper}:${currentTab}:${task?.id || ''}`;
    if (view !== lastView) {
        lastRendered = null; lastAuditRendered = null; activeReview = null;
        $('#report').innerHTML = '<p class="muted">正在加载…</p>'; lastView = view;
    }
    const options = tasks.map(task => `<option value="${esc(task.id)}">${esc(new Date(task.created_at).toLocaleString())} · ${esc(statuses[task.status] || task.status)} · ${esc(task.id)}</option>`).join('');
    if ($('#report-history').innerHTML !== options) $('#report-history').innerHTML = options;
    $('#report-history').disabled = !tasks.length;
    $('#report-task').textContent = task ? `任务 ${task.id} · ${statuses[task.status] || task.status} · 各页签保留各自的任务时间与结果。` : '';
    selected = task?.id || null;
    if (!task) {
        $('#download').hidden = true;
        $('#report').innerHTML = `<p class="muted">${group ? '该论文尚未提交此类审查。' : '请选择任务或提交所选审查。'}</p>`;
        return;
    }
    choices[currentTab] = task.id; $('#report-history').value = task.id;
    if (currentTab === 'review') {
        $('#download').textContent = '下载原始报告 ↗';
        await showReport(task);
    } else await showAuditReport(task, currentTab);
}
function chooseTask(id) {
    for (const group of groups) {
        const task = group.tasks.find(t => t.id === id);
        if (!task) continue;
        selectedPaper = group.document_id;
        const choices = reportChoices.get(selectedPaper) || {};
        for (const check of task.checks) choices[check] = id;
        reportChoices.set(selectedPaper, choices);
        currentTab = task.checks[0];
        return renderSelection();
    }
}
async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
        groups = await api('/workspace/tasks');
        if (!selectedPaper && groups.length) selectedPaper = groups[0].document_id;
        $('#jobs').innerHTML = groups.map(group => `<section class="task-group ${group.document_id === selectedPaper ? 'selected' : ''}"><h3>${esc(group.title)}</h3>${group.tasks.map(task =>
            `<div class="job"><button type="button" data-task="${esc(task.id)}">${esc(task.checks.map(c => labels[c]).join('＋'))}<small>${esc(new Date(task.created_at).toLocaleString())}${task.document_ids.length > 1 ? ' · ' + task.document_ids.length + ' 份论文' : ''}</small></button>
            <span class="status ${esc(task.status)}">${esc(statuses[task.status] || task.status)}</span>${['queued', 'running'].includes(task.status) ? `<button type="button" class="text-button" data-cancel="${esc(task.id)}" data-kind="${task.kind}">取消</button>` : ''}</div>`).join('')}</section>`).join('') || '<p class="muted">尚无任务。</p>';
        document.querySelectorAll('[data-task]').forEach(button => button.onclick = () => chooseTask(button.dataset.task).catch(error => notify(error.message)));
        document.querySelectorAll('[data-cancel]').forEach(button => button.onclick = async () => {
            try {
                await post(`/${button.dataset.kind === 'review' ? 'jobs' : 'audits'}/${button.dataset.cancel}/cancel`, {});
                await refresh();
            } catch (error) { notify(error.message); }
        });
        await renderSelection();
    } finally { refreshing = false; }
}
for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => {
    currentTab = button.dataset.tab; renderSelection().catch(error => notify(error.message));
};
$('#report-history').onchange = () => {
    const choices = reportChoices.get(selectedPaper) || {};
    choices[currentTab] = $('#report-history').value; reportChoices.set(selectedPaper, choices);
    renderSelection().catch(error => notify(error.message));
};
$('#refresh').onclick = () => refresh().catch(error => notify(error.message));
$('#search').onclick = async () => {
    $('#search').disabled = true;
    try {
        const record = await post('/search', {query: $('#query').value, approved: $('#approved').checked});
        $('#search-results').innerHTML = record.results.map(r => `<article><b>${esc(r.title)}</b><br><a href="https://doi.org/${encodeURIComponent(r.doi || '')}" target="_blank" rel="noopener noreferrer">${esc(r.doi || '无 DOI')}</a> · 仅书目信息</article>`).join('') || '<p>未检索到结果；不表示文献不存在。</p>';
    } catch (error) { notify(error.message); }
    finally { $('#search').disabled = false; }
};
async function init() {
    const config = await api('/config');
    modelAvailable = Boolean(config.local_model_available);
    $('#mode option[value=local]').textContent = modelAvailable ? '模型评审' : '模型暂不可用';
    $('#submit').disabled = !modelAvailable;
    showOptions(); await loadDocuments(); await refresh();
}
init().catch(error => notify(error.message));
setInterval(() => refresh().catch(error => notify('服务连接异常：' + error.message)), 1500);
