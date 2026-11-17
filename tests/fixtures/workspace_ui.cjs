// Minimal DOM/API fixture for workbench behavior tests; no browser dependency.
const fs = require('fs'), vm = require('vm');
module.exports = async function workspace(handler = () => undefined) {
    const elements = new Map(), calls = [];
    function element(id) {
        if (!elements.has(id)) elements.set(id, {value: '', files: [], checked: false, hidden: false,
            disabled: false, dataset: {}, children: [], attributes: {}, innerHTML: '', textContent: '',
            append(child) {this.children.push(child);}, remove() {},
            setAttribute(key, value) {this.attributes[key] = value;}});
        return elements.get(id);
    }
    const tabs = ['review', 'novelty', 'experiments'].map(tab => {
        const button = element('#tab-' + tab); button.dataset.tab = tab; return button;
    });
    element('#check-review').checked = true;
    element('#degree').value = 'master'; element('#material').value = 'thesis';
    element('#language').value = 'zh-CN'; element('#experiment-name').value = '主实验';
    const context = {document: {querySelector: element, querySelectorAll: query => query === '[data-tab]' ? tabs : [],
        createElement: () => ({children: [], append(child) {this.children.push(child);}, remove() {}})},
        FormData: class {constructor() {this.fields = {}} append(key, value) {this.fields[key] = value}},
        setTimeout: () => {}, setInterval: () => {}, ReviewEvidence: {render: () => ''},
        fetch: async (url, options = {}) => {
            const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
            calls.push({url, options, body});
            const custom = await handler(url, options, body);
            if (custom) return custom;
            let result = {};
            if (url.endsWith('/config')) result = {local_model_available: true};
            else if (url.endsWith('/workspace/tasks')) result = [];
            else if (url.endsWith('/documents')) result = options.method ? {id: 'doc_test'} : [];
            else if (url.endsWith('/audit-materials')) result = {id: 'mat_test', filename: 'train.csv', role: 'data', split: 'train'};
            else if (url.endsWith('/jobs')) result = {id: 'job_test'};
            else if (url.endsWith('/audits')) result = {id: 'audit_test'};
            else if (url.endsWith('/review-decisions')) result = {source_report_sha256: 'hash', excluded_findings: [], revision: options.method ? (body.revision || 0) + 1 : 0};
            else if (url.endsWith('/content')) result = {blocks: []};
            else if (url.includes('/jobs/') && url.endsWith('/report')) result = {verdict: '需修改', findings: [], rule_matrix: [], summary: '原审查结果'};
            return {ok: true, json: async () => result};
        }};
    vm.createContext(context);
    for (const file of ['review.js', 'app.js', 'audit.js', 'workspace.js'])
        vm.runInContext(fs.readFileSync('app/static/' + file, 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    calls.length = 0;
    return {el: element, calls, context, run: source => vm.runInContext(source, context)};
};
