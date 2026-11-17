// Supplemental material input and report rendering share the workbench's API client.
const materialIds = [];
let lastAuditRendered = null;
$('#audit-queries').oninput = () => { $('#audit-approved').checked = false; };

$('#add-material').onclick = async () => {
    const button = $('#add-material');
    button.disabled = true;
    try {
        const file = $('#material-file').files[0];
        if (!file) throw new Error('请选择配套文件。');
        const form = new FormData();
        form.append('file', file);
        form.append('role', $('#material-role').value);
        form.append('split', $('#material-split').value);
        form.append('id_column', $('#material-id-column').value.trim());
        const material = await api('/audit-materials', {method: 'POST', body: form});
        materialIds.push(material.id);
        const row = document.createElement('li');
        row.textContent = `${material.filename} · ${material.role} · ${material.split} `;
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'text-button'; remove.textContent = '移出本次审查';
        remove.onclick = () => { materialIds.splice(materialIds.indexOf(material.id), 1); row.remove(); };
        row.append(remove); $('#material-list').append(row);
        $('#material-file').value = '';
    } catch (error) { notify(error.message); }
    finally { button.disabled = false; }
};

const notesHtml = notes => notes.length ? `<ul class="limitations">${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : '';
function noveltyHtml(novelty) {
    const sources = Object.fromEntries(novelty.sources.map(source => [source.id, source]));
    return `<h2 class="report-title">${esc(novelty.status)}</h2><p>${esc(novelty.basis)}</p>`
        + novelty.comparisons.map(item => {
            const source = sources[item.source_id];
            return `<article class="finding audit-finding"><b>${esc(source.title)}</b>
                <p>${esc(item.judgment)} · ${esc(source.scope)}</p><p>${esc(item.difference)}</p>
                <blockquote>论文：${esc(item.paper_quote)}\n相关工作：${esc(item.source_quote)}</blockquote></article>`;
        }).join('')
        + `<details><summary>候选文献（${novelty.sources.length}）</summary><ul>${novelty.sources.map(s =>
            `<li><a href="https://doi.org/${encodeURIComponent(s.doi)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a> · ${esc(s.published || '日期未知')} · ${esc(s.scope)}</li>`).join('')}</ul></details>`
        + notesHtml(novelty.notes);
}
function experimentsHtml(experiments) {
    return experiments.map(experiment => `<section><h3>${esc(experiment.name)} · ${esc(experiment.id)}</h3>
        <p>${esc(experiment.status)}</p>
        <p class="muted">同名数值字段：${esc(experiment.coverage.numeric_fields.join(', ') || '无')}；完整 ID 列数据文件 ${experiment.coverage.id_files.length} 份。</p>
        ${experiment.findings.map(f => `<article class="finding audit-finding"><b>${esc(f.status)}</b><p>${esc(f.issue)}</p>
            ${f.evidence.map(e => `<blockquote>${esc(e.filename)} / ${esc(e.location || '')}\n${esc(e.quote ?? e.value ?? '')}</blockquote>`).join('')}
            <p>核查建议：${esc(f.suggestion)}</p></article>`).join('')}
        ${notesHtml(experiment.notes)}</section>`).join('');
}
async function showAuditReport(task, tab) {
    const key = task.id + task.updated_at + tab;
    if (lastAuditRendered === key) return;
    activeReview = null;
    $('#download').hidden = true;
    if (['completed', 'partial'].includes(task.status)) {
        try {
            const report = await api(`/audits/${task.id}/report`);
            if (selected !== task.id || currentTab !== tab) return;
            $('#report').innerHTML = (tab === 'novelty' ? noveltyHtml(report.novelty) : experimentsHtml(report.experiments))
                + `<details><summary>范围与限制</summary>${notesHtml(report.limitations)}</details>`;
            $('#download').href = `/api/v1/audits/${task.id}/download`;
            $('#download').textContent = '下载补充报告 ↗';
            $('#download').hidden = false;
        } catch (error) {
            if (selected === task.id && currentTab === tab) $('#report').innerHTML = `<p class="error">加载报告失败：${esc(error.message)}</p>`;
            return;
        }
    } else {
        $('#report').innerHTML = `<p class="${task.error ? 'error' : 'muted'}">${esc(task.error || statuses[task.status] || task.status)} · ${esc(stages[task.stage] || task.stage)}</p>`;
    }
    lastAuditRendered = key;
}
