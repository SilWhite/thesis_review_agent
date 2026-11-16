// Human review selection and final-report interaction.
function updateReviewControls(state) {
    if (activeReview !== state || !$('#review-count')) return;
    $('#review-count').textContent = `保留 ${state.total-state.excluded.size} 项 · 已划除 ${state.excluded.size} 项`;
    $('#review-save-status').textContent = state.pending ? '正在保存…' : state.saveError ? '保存失败，可重试生成报告。' : '选择已保存';
    $('#generate-final').disabled = Boolean(state.pending || state.generating);
    document.querySelectorAll('[data-exclude]').forEach(input => input.disabled = Boolean(state.generating));
}

function saveReviewSelection(state) {
    const body = {source_report_sha256:state.digest, excluded_findings:[...state.excluded].sort((a,b)=>a-b)};
    state.pending++;
    updateReviewControls(state);
    state.queue = state.queue.catch(()=>{}).then(() => post(`/jobs/${state.jobId}/review-decisions`, {...body,revision:state.serverRevision || 0}))
        .then(saved => { state.serverRevision = saved.revision; state.saveError = false; })
        .catch(error => { state.saveError = true; throw error; })
        .finally(() => { state.pending--; updateReviewControls(state); });
    return state.queue;
}

function bindReviewControls(state, lookup) {
    document.querySelectorAll('[data-exclude]').forEach(input => input.onchange = () => {
        const index = Number(input.dataset.exclude);
        if (input.checked) state.excluded.add(index); else state.excluded.delete(index);
        input.closest('.finding').classList.toggle('excluded', input.checked);
        $('#final-result').innerHTML = '';
        state.revision++;
        saveReviewSelection(state).catch(error => notify(error.message));
    });
    $('#generate-final').onclick = async () => {
        state.generating = true;
        const revision = state.revision;
        updateReviewControls(state);
        try {
            const result = await post(`/jobs/${state.jobId}/final-report`, {
                source_report_sha256:state.digest, excluded_findings:[...state.excluded].sort((a,b)=>a-b), revision:state.serverRevision || 0
            });
            state.serverRevision = result.revision;
            state.saveError = false;
            if (activeReview !== state || selected !== state.jobId || revision !== state.revision) return;
            const final = result.report;
            $('#final-result').innerHTML = `<h3>最终报告</h3><p><b>${esc(final.verdict)}</b></p><p>${esc(final.summary)}</p>
                <a class="secondary download-final" href="${esc(result.download_url)}">下载最终报告 ↗</a>
                <details class="final-preview"><summary>查看最终问题清单（${final.findings.length} 项）</summary>
                ${final.findings.map(f => `<article class="finding final-finding"><div class="finding-content"><p><b>问题：</b>${esc(f.issue)}</p>
                    ${f.suggestion ? `<p><b>修改建议：</b>${esc(f.suggestion)}</p>` : ''}
                    ${ReviewEvidence.render(f, lookup, state.jobId, f.source_finding_index)}</div></article>`).join('') || '<p>无保留问题。</p>'}</details>`;
        } catch (error) {
            notify(error.message);
        } finally {
            state.generating = false;
            updateReviewControls(state);
        }
    };
    updateReviewControls(state);
}

