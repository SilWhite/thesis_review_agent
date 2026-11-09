const $ = s => document.querySelector(s);
const esc = value => String(value).replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [c]));
let selected = null,
    lastRendered = null;
const statuses = {
    queued: '排队中',
    running: '执行中',
    completed: '已完成',
    partial: '有限范围结果',
    failed: '失败',
    cancelled: '已取消',
    interrupted: '已中断'
};
const stages = {
    queued: '等待执行',
    parsing: '文档解析',
    reviewing: '生成意见',
    verifying: '校验证据',
    reporting: '报告已生成'
};
async function api(path, options = {}) {
    const response = await fetch('/api/v1' + path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    return data;
}
const post = (path, body) => api(path, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
});

function notify(message) {
    $('#toast').textContent = message;
    $('#toast').hidden = false;
    setTimeout(() => $('#toast').hidden = true, 6000);
}
async function upload(files, role) {
    const ids = [];
    for (const file of files) {
        $('#upload-status').textContent = '正在保存 ' + file.name;
        const form = new FormData();
        form.append('file', file);
        form.append('role', role);
        ids.push((await api('/documents', {
            method: 'POST',
            body: form
        })).id);
    }
    $('#upload-status').textContent = '';
    return ids;
}
async function loadPolicies() {
    const docs = await api('/documents');
    $('#saved-policies').innerHTML = docs.filter(d => d.role === 'policy').map(d => `<label class="check"><input type="checkbox" value="${d.id}">${esc(d.filename)} <small>已保存</small></label>`).join('');
}
$('#example').onclick = () => {
    $('#text').value = '题目：面向文档的实验方法研究\n摘要：本研究比较两种方法在公开数据集上的效果。\n实验设置：TODO 补充训练集与测试集划分。\n结果：基线准确率为80%，本方法为84%。\n消融实验：待补充。\n结论：当前证据需要进一步完善。';
};
$('#review-form').onsubmit = async event => {
    event.preventDefault();
    $('#submit').disabled = true;
    try {
        const ids = await upload($('#files').files, 'primary');
        if ($('#text').value.trim()) ids.push((await post('/documents/text', {
            title: '文本材料',
            text: $('#text').value
        })).id);
        if (!ids.length) throw new Error('请上传材料或粘贴文本。');
        const policies = [...document.querySelectorAll('#saved-policies input:checked')].map(e => e.value);
        policies.push(...await upload($('#policies').files, 'policy'));
        const job = await post('/jobs', {
            document_ids: ids,
            policy_ids: policies,
            material_type: $('#material').value,
            degree: $('#degree').value,
            language: $('#language').value,
            custom_prompt: $('#prompt').value,
            model_mode: $('#mode').value
        });
        selected = job.id;
        lastRendered = null;
        await refresh();
        await loadPolicies();
    } catch (error) {
        notify(error.message);
    } finally {
        $('#submit').disabled = false;
    }
};
async function showReport(job) {
    const key = job.id + job.updated_at;
    if (lastRendered === key) return;
    $('#download').hidden = true;
    if (['completed', 'partial'].includes(job.status)) {
        const [report, content] = await Promise.all([api(`/jobs/${job.id}/report`), api(`/jobs/${job.id}/content`)]);
        if (selected !== job.id) return;
        const lookup = Object.fromEntries(content.blocks.map(b => [b.id, b]));
        $('#report').innerHTML = `<div class="report-body"><span class="report-tag">${report.mode==='mock'?'模拟输出 · 仅供流程验证':'模型输出 · 限定已提取文本'}</span><h2 class="report-title">${esc(report.verdict)}</h2><p>${esc(report.summary)}</p><div class="muted">${report.coverage.document_count} 份材料 · ${report.coverage.block_count} 个文本块</div><h3>关键问题</h3>${report.findings.length?report.findings.map(f=>`<article class="finding"><b>${esc(f.dimension)}</b> <span class="muted">${f.severity==='major'?'主要问题':'一般问题'} · ${f.status==='supported'?'有原文依据':'待核实'}</span><p>${esc(f.issue)}</p><blockquote>${esc(f.quote)}</blockquote><div class="muted">${esc(f.filename)} · ${esc(f.location)}</div><p>建议：${esc(f.suggestion)}</p><details><summary>展开所在原文</summary><div class="source">${esc(lookup[f.block_id].text)}</div></details></article>`).join(''):'<p class="muted">当前范围内未输出有依据的问题，不等于全部核验通过。</p>'}<h3>优先处理事项</h3><ul>${report.priority_actions.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><details><summary>审查范围与限制</summary><ul class="limitations">${report.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></details></div>`;
        $('#download').href = `/api/v1/jobs/${job.id}/download`;
        $('#download').hidden = false;
    } else if (job.status === 'failed' || job.status === 'interrupted') {
        $('#report').innerHTML = `<p class="error">${esc(job.error)}</p><p class="muted">修正配置或材料后，可从左侧重新提交。历史文件保留。</p>`;
    } else {
        $('#report').innerHTML = `<div class="empty"><div class="empty-icon">${job.status==='cancelled'?'—':'⋯'}</div><h3>${statuses[job.status]}</h3><p>${job.status==='cancelled'?'任务已取消，不发布结果。':stages[job.stage]}</p></div>`;
    }
    lastRendered = key;
}
async function refresh() {
    const jobs = await api('/jobs');
    if (!selected && jobs.length) selected = jobs[0].id;
    $('#jobs').innerHTML = jobs.length ? jobs.map(j => `<div class="job ${j.id===selected?'selected':''}"><button data-job="${j.id}"><strong>${esc(j.title)}</strong><small>${new Date(j.created_at).toLocaleString()} · ${j.mode==='mock'?'模拟':'内网模型'}</small></button><span class="status ${j.status}">${statuses[j.status]}</span>${['queued','running'].includes(j.status)?`<button class="text-button" data-cancel="${j.id}">取消</button>`:''}</div>`).join('') : '<p class="muted">还没有任务。从左侧添加一份材料开始。</p>';
    document.querySelectorAll('[data-job]').forEach(b => b.onclick = () => {
        selected = b.dataset.job;
        refresh().catch(e => notify(e.message));
    });
    document.querySelectorAll('[data-cancel]').forEach(b => b.onclick = async () => {
        try {
            await post(`/jobs/${b.dataset.cancel}/cancel`, {});
            await refresh();
        } catch (e) {
            notify(e.message);
        }
    });
    const job = jobs.find(j => j.id === selected);
    if (job) await showReport(job);
}
$('#refresh').onclick = () => refresh().catch(e => notify(e.message));
$('#search').onclick = async () => {
    $('#search').disabled = true;
    try {
        const record = await post('/search', {
            query: $('#query').value,
            approved: $('#approved').checked
        });
        $('#search-results').innerHTML = record.results.map(r => `<article><b>${esc(r.title)}</b><br><a href="https://doi.org/${encodeURIComponent(r.doi||'')}" target="_blank" rel="noopener noreferrer">${esc(r.doi||'无 DOI')}</a> · 仅书目信息</article>`).join('') || '<p>未检索到结果；不表示文献不存在。</p>';
    } catch (e) {
        notify(e.message);
    } finally {
        $('#search').disabled = false;
    }
};
async function init() {
    const config = await api('/config');
    if (config.local_model_available) {
        const option = $('#mode option[value=local]');
        option.disabled = false;
        option.textContent = '内网模型 · ' + config.model_name;
    }
    await loadPolicies();
    await refresh();
}
init().catch(e => notify(e.message));
setInterval(() => refresh().catch(error => {
    $('#upload-status').textContent = '服务连接异常：' + error.message;
}), 1500);
