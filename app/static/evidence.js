/* Render exact locations without substituting an unrelated page-sized block. */
window.ReviewEvidence = (() => {
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function highlight(text, phrases) {
        text = String(text || '');
        const intervals = [];
        let normalized = '', starts = [], ends = [], offset = 0;
        for (const char of text) {
            for (const unit of char.normalize('NFKC')) {
                if (/\s/.test(unit)) continue;
                normalized += unit;
                for (let i=0; i<unit.length; i++) { starts.push(offset); ends.push(offset+char.length); }
            }
            offset += char.length;
        }
        for (const phrase of phrases || []) {
            if (!phrase) continue;
            const needle = phrase.normalize('NFKC').replace(/\s/g,'');
            if (!needle) continue;
            let start = 0, count = 0;
            while ((start = normalized.indexOf(needle, start)) !== -1 && count++ < 30) {
                intervals.push([starts[start], ends[start+needle.length-1]]);
                start += needle.length;
            }
        }
        intervals.sort((a,b) => a[0]-b[0]);
        const merged = [];
        for (const range of intervals) {
            if (merged.length && range[0] <= merged[merged.length-1][1]) merged[merged.length-1][1] = Math.max(range[1], merged[merged.length-1][1]);
            else merged.push(range);
        }
        let out = '', cursor = 0;
        for (const [start,end] of merged) {
            out += escape(text.slice(cursor,start)) + '<mark>' + escape(text.slice(start,end)) + '</mark>';
            cursor = end;
        }
        return out + escape(text.slice(cursor));
    }
    function render(finding, lookup, jobId, index) {
        const note = finding.evidence_note ? `<p><b>核对重点：</b>${escape(finding.evidence_note)}</p>` : '';
        const measure = finding.measurement ? `<p><b>检查结果：</b>${escape(finding.measurement)}</p>` : '';
        const locations = finding.locations || [];
        let sources = locations.map((loc, locationIndex) => {
            const text = loc.context || loc.quote || '';
            const compact = value => String(value || '').normalize('NFKC').replace(/\s/g,'');
            const phrases = finding.quote && compact(text).includes(compact(finding.quote)) ? [finding.quote] : (loc.highlight_texts?.length ? loc.highlight_texts : [loc.quote || finding.quote]);
            const page = loc.page ? `PDF 第 ${escape(loc.page)} 页` : '原文位置';
            const url = `/api/v1/jobs/${encodeURIComponent(jobId)}/evidence/${index}/${locationIndex}`;
            const image = loc.page && (finding.filename || '').toLowerCase().endsWith('.pdf') ? `
                <details style="margin-top:8px"><summary>查看原页截图${loc.bbox ? '（红框标出核对区域）' : ''}</summary>
                <a href="${url}?full_page=true" target="_blank" rel="noopener">打开完整页面 ↗</a>
                <a href="${url}?full_page=true" target="_blank" rel="noopener"><img loading="lazy" src="${url}" alt="${page}原页" style="display:block;width:100%;height:auto;margin-top:8px;border:1px solid #ddd"></a></details>` : '';
            return `<section style="margin-top:10px;padding:10px;border:1px solid #d4ded6;border-radius:6px"><b>${page}</b>${loc.description ? ` · ${escape(loc.description)}` : ''}
                ${text ? `<div class="source" style="margin-top:6px">${highlight(text, phrases)}</div>` : ''}${image}</section>`;
        }).join('');
        if (!sources) {
            const block = lookup[finding.block_id]?.text || '';
            const quote = finding.quote || '';
            const position = quote ? block.indexOf(quote) : -1;
            const text = position >= 0 ? block.slice(Math.max(0, position-160), position+quote.length+160) : quote;
            sources = text ? `<div class="source">${highlight(text,[quote])}</div>` : '<p class="muted">这条提示暂无精确原文位置，请结合问题说明核对。</p>';
        }
        return note + measure + sources;
    }
    return {highlight, render};
})();
