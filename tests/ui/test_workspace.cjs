const assert = require('assert'), workspace = require('../fixtures/workspace_ui.cjs');
const response = result => ({ok: true, json: async () => result});
const auditReport = {novelty: {status: '信息不足', basis: '有限检索', sources: [], comparisons: [], notes: []},
    experiments: [{id: 'E01', name: '实验结果', status: '需核实', coverage: {numeric_fields: [], id_files: []}, findings: [], notes: []}], limitations: []};
(async () => {
    const first = await workspace();
    const {el, calls} = first;
    el('#files').files = [{name: 'paper.pdf'}];
    el('#check-novelty').checked = el('#check-experiments').checked = true;
    el('#audit-queries').value = 'public topic'; el('#audit-approved').checked = true;
    el('#experiment-quote').value = '训练集共3条。';
    await el('#review-form').onsubmit({preventDefault() {}});
    assert.equal(calls.filter(c => c.url === '/api/v1/documents' && c.options.method).length, 1);
    const review = calls.find(c => c.url === '/api/v1/jobs').body, audit = calls.find(c => c.url === '/api/v1/audits').body;
    assert.equal(review.document_ids[0], audit.document_id);
    assert.equal(audit.experiments.length, 1); assert.equal(audit.public_queries.length, 1);
    await el('#review-form').onsubmit({preventDefault() {}});
    assert.equal(calls.filter(c => c.url === '/api/v1/documents' && c.options.method).length, 1, 'repeat submit must reuse original upload');
    calls.length = 0; el('#check-review').checked = el('#check-novelty').checked = el('#check-experiments').checked = false;
    await el('#review-form').onsubmit({preventDefault() {}}); assert.equal(calls.length, 0);

    const tasks = [{id: 'audit_new', kind: 'audit', checks: ['experiments'], status: 'completed', stage: 'reporting', created_at: '2026-11-16T12:00:00Z', updated_at: 'new', document_ids: ['doc_one']},
        {id: 'audit_old', kind: 'audit', checks: ['novelty', 'experiments'], status: 'completed', stage: 'reporting', created_at: '2026-11-15T12:00:00Z', updated_at: 'old', document_ids: ['doc_one']},
        {id: 'job_old', kind: 'review', checks: ['review'], status: 'completed', created_at: '2026-11-14T12:00:00Z', updated_at: 'old', document_ids: ['doc_one']}];
    const history = await workspace(url => url.endsWith('/workspace/tasks') ? response([{document_id: 'doc_one', title: '论文', tasks}]) : url.includes('/audits/') && url.endsWith('/report') ? response(auditReport) : undefined);
    assert(history.el('#jobs').innerHTML.includes('job_old') && history.el('#jobs').innerHTML.includes('audit_old'));
    await history.run("currentTab='novelty'; renderSelection()");
    assert.equal(history.el('#report-history').value, 'audit_old');
    await history.run("currentTab='experiments'; renderSelection()");
    assert.equal(history.el('#report-history').value, 'audit_new');
    history.el('#report-history').value = 'audit_old'; await history.el('#report-history').onchange();
    // The handler returns immediately; drain the JSON response microtasks.
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(history.el('#report-history').value, 'audit_old');
    assert(history.el('#report').innerHTML.includes('实验结果'));
    const reloaded = await workspace(url => url.endsWith('/workspace/tasks') ? response([{document_id: 'doc_one', title: '论文', tasks}]) : url.includes('/audits/') && url.endsWith('/report') ? response(auditReport) : undefined);
    assert(reloaded.el('#jobs').innerHTML.includes('audit_new'), 'history must reload without browser-local IDs');

    const failure = await workspace(url => url === '/api/v1/audits' ? {ok: false, json: async () => ({detail: 'fixture failure'})} : undefined);
    failure.el('#files').files = [{name: 'paper.pdf'}]; failure.el('#check-novelty').checked = true;
    failure.el('#audit-queries').value = 'public topic'; failure.el('#audit-approved').checked = true;
    await failure.el('#review-form').onsubmit({preventDefault() {}});
    assert(failure.el('#toast').textContent.includes('已提交规范与逻辑；后续提交失败'));
    assert.equal(failure.calls.filter(c => c.url === '/api/v1/jobs').length, 1);
    let release;
    const slow = await workspace(url => url.endsWith('/audits/slow/report') ?
        new Promise(resolve => {release = () => resolve(response(auditReport));}) :
        url.endsWith('/audits/fast/report') ? response(auditReport) : undefined);
    const pending = slow.run("selected='slow';currentTab='novelty';showAuditReport({id:'slow',status:'completed',updated_at:'one'},'novelty')");
    await slow.run("selected='fast';currentTab='experiments';showAuditReport({id:'fast',status:'completed',updated_at:'two'},'experiments')");
    release(); await pending;
    assert(slow.el('#report').innerHTML.includes('实验结果') && !slow.el('#report').innerHTML.includes('有限检索'));
    console.log('Workbench: upload once, selective dispatch, server history, per-tab versions and partial submission preserved');
})().catch(e => {console.error(e); process.exitCode = 1;});
