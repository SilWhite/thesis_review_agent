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
let modelAvailable = false, activeReview = null;
const reviewStates = new Map();
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
    reporting: '报告已生成',
    experiments: '实验材料核对',
    novelty: '创新性初判'
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
async function showReport(job) {
    const key = job.id + job.updated_at;
    if (lastRendered === key) return;
    $('#download').hidden = true;
    if (['completed', 'partial'].includes(job.status)) {
        let report, content, decisions;
        try {
            [report, content, decisions] = await Promise.all([
                api(`/jobs/${job.id}/report`),
                api(`/jobs/${job.id}/content`).catch(() => ({ blocks: [] })),
                api(`/jobs/${job.id}/review-decisions`)
            ]);
        } catch (e) {
            if (selected !== job.id || currentTab !== 'review') return;
            activeReview = null;
            $('#report').innerHTML = `<p class="error">加载报告失败: ${esc(e.message)}</p>`;
            return;
        }
        if (selected !== job.id || currentTab !== 'review' || lastRendered === key) return;
        let state = reviewStates.get(job.id);
        if (!state || state.digest !== decisions.source_report_sha256) {
            state = {jobId:job.id, digest:decisions.source_report_sha256, excluded:new Set(decisions.excluded_findings),
                     total:(report.findings || []).length, queue:Promise.resolve(), pending:0, revision:0, serverRevision:decisions.revision || 0, saveError:false, generating:false};
            reviewStates.set(job.id, state);
        }
        activeReview = state;

        const blocks = (content && Array.isArray(content.blocks)) ? content.blocks : [];
        const lookup = Object.fromEntries(blocks.map(b => [b.id, b]));

        const ruleMatrixHtml = (report.rule_matrix && report.rule_matrix.length) ? `
            <details style="margin: 16px 0; border: 1px solid #d4ded6; border-radius: 8px; padding: 12px; background: #fff;">
                <summary style="font-weight: 600; cursor: pointer; color: var(--accent);">
                    ${report.rule_matrix.length} 项检查结果
                </summary>
                <div style="overflow-x: auto; margin-top: 10px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                        <thead>
                            <tr style="background: #f0f4f1; border-bottom: 2px solid #d4ded6; text-align: left;">
                                <th style="padding: 6px 8px;">序号</th>
                                <th style="padding: 6px 8px;">类别</th>
                                <th style="padding: 6px 8px;">规范项名称</th>
                                <th style="padding: 6px 8px;">审查状态</th>
                                <th style="padding: 6px 8px;">检出数</th>
                                <th style="padding: 6px 8px;">说明</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${report.rule_matrix.map(rm => {
                                const isPassed = rm.status === '检查通过';
                                const isFound = rm.status === '发现问题';
                                const statusColor = isPassed ? '#2e7d32' : (isFound ? '#c62828' : '#757575');
                                const bg = isFound ? '#fff5f5' : '#fff';
                                return `<tr style="background: ${bg}; border-bottom: 1px solid #e8ede9;">
                                    <td style="padding: 6px 8px; font-weight: bold;">${rm.rule_id}</td>
                                    <td style="padding: 6px 8px; color: #555;">${esc(rm.category || '')}</td>
                                    <td style="padding: 6px 8px;">${esc(rm.rule_name || '')}</td>
                                    <td style="padding: 6px 8px; font-weight: 600; color: ${statusColor};">${esc(rm.status || '')}</td>
                                    <td style="padding: 6px 8px; text-align: center; font-weight: ${rm.findings_count > 0 ? 'bold' : 'normal'}; color: ${rm.findings_count > 0 ? '#c62828' : '#333'};">${rm.findings_count || 0}</td>
                                    <td style="padding: 6px 8px; color: #666; font-size: 11px;">${esc(rm.note || '')}</td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </details>
        ` : '';

        const findingsHtml = (report.findings && report.findings.length) ? report.findings.map((f, findingIndex) => {
            return `<article class="finding ${state.excluded.has(findingIndex) ? 'excluded' : ''}">
                <label class="finding-toggle"><input type="checkbox" data-exclude="${findingIndex}" aria-label="划除第 ${findingIndex+1} 条问题" ${state.excluded.has(findingIndex) ? 'checked' : ''}><span>划除</span></label>
                <div class="finding-content">
                <b>${esc(f.dimension || '规范与逻辑')}</b>
                <span class="muted">${f.severity === 'major' ? '<span style="color:#c62828;font-weight:bold;">重大问题</span>' : '待规范'} · ${f.status === 'supported' ? '有原文依据' : '待核实'}</span>
                <p class="finding-issue"><b>问题：</b>${esc(f.issue || '')}</p>
                <div class="muted">${esc(f.filename || '')} · ${esc(f.location || '')}</div>
                ${f.suggestion ? `<p class="finding-suggestion" style="margin-top:6px; color:#2e5b4b;"><b>修改建议：</b>${esc(f.suggestion)}</p>` : ''}
                ${ReviewEvidence.render(f, lookup, job.id, findingIndex)}
                </div></article>`;
        }).join('') : '<p class="muted">暂无问题提示。</p>';

        const priorityHtml = (report.priority_actions && report.priority_actions.length) ? `
            <h3>优先处理事项</h3>
            <ul>${report.priority_actions.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
        ` : '';

        const limitationsHtml = (report.limitations && report.limitations.length) ? `
            <details style="margin-top:16px;"><summary>审查范围</summary><ul class="limitations">${report.limitations.map(s => `<li>${esc(s.replace(/规范材料仅作为参考；本 demo 尚未实现规范发布与适用范围核定。/g, '参考规范的适用范围需结合学校要求核对。'))}</li>`).join('')}</ul></details>
        ` : '';

        const docCount = (report.coverage && report.coverage.document_count) || 1;
        $('#report').innerHTML = `
            <div class="report-body">
                <h2 class="report-title">${esc(report.verdict || '评审完成')}</h2>
                <p style="line-height:1.7;">${esc(report.summary || '')}</p>
                <div class="muted" style="margin-bottom:12px;">${docCount} 份材料 · ${report.findings ? report.findings.length : 0} 项问题</div>
                ${ruleMatrixHtml}
                <h3>关键问题清单（共 ${report.findings ? report.findings.length : 0} 处）</h3>
                ${findingsHtml}
                ${priorityHtml}
                ${limitationsHtml}
                <div class="final-report-actions"><p id="review-count" aria-live="polite"></p>
                    <p class="muted" id="review-save-status" aria-live="polite"></p>
                    <button type="button" class="primary" id="generate-final">生成最终报告 <span>→</span></button>
                    <div id="final-result" aria-live="polite"></div></div>
            </div>
        `;

        $('#download').href = `/api/v1/jobs/${job.id}/download`;
        $('#download').hidden = false;
        bindReviewControls(state, lookup);
    } else if (job.status === 'failed' || job.status === 'interrupted') {
        activeReview = null;
        $('#report').innerHTML = `<p class="error">${esc(job.error || '执行失败')}</p><p class="muted">修正配置或材料后，可从左侧重新提交。历史文件保留。</p>`;
    } else {
        activeReview = null;
        $('#report').innerHTML = `<div class="empty"><div class="empty-icon">${job.status === 'cancelled' ? '—' : '⋯'}</div><h3>${statuses[job.status] || job.status}</h3><p>${job.status === 'cancelled' ? '任务已取消，不发布结果。' : (stages[job.stage] || job.stage)}</p></div>`;
    }
    lastRendered = key;
}
