// Supplemental material input and report rendering share the workbench's API client.
const materialIds = [];
let lastAuditRendered = null;
let currentNoveltyData = null;

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

const notesHtml = notes => notes && notes.length ? `<ul class="limitations">${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : '';

function viewPaper(pid) {
    if (!currentNoveltyData || !currentNoveltyData.sources) return;
    const s = currentNoveltyData.sources.find(x => x.id === pid);
    if (!s) return;

    let modal = document.getElementById('paper-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'paper-modal';
        modal.className = 'paper-modal-backdrop';
        modal.onclick = (e) => { if (e.target === modal) modal.hidden = true; };
        document.body.appendChild(modal);
    }

    const authors = (s.authors || []).join(', ') || '未知作者';
    const venue = s.venue || '未知刊物/会议';
    const year = s.year || s.published || '未知年份';
    const cit = s.citation_count != null ? s.citation_count : '-';

    const comp = (currentNoveltyData.comparisons || []).find(c => c.source_id === pid);
    let compSection = '';
    if (comp) {
        compSection = `
            <div class="modal-comp-box">
                <div class="modal-comp-header">⚡ 在本论文中作为对标文献碰撞：<b class="judgment-text">${esc(comp.judgment)}</b></div>
                <div class="modal-comp-claim">针对创新主张：<b>${esc(comp.claim)}</b></div>
                <div class="modal-comp-diff"><b>重合与 Delta 差异：</b>${esc(comp.difference)}</div>
                <button type="button" class="action-link-btn" onclick="jumpToComparison('${esc(pid)}'); document.getElementById('paper-modal').hidden = true;">跳转查看下方逐点碰撞对比卡片 ↓</button>
            </div>
        `;
    }

    modal.innerHTML = `
        <div class="paper-modal-dialog">
            <button type="button" class="modal-close-btn" onclick="document.getElementById('paper-modal').hidden = true;" title="关闭">&times;</button>
            <div class="modal-badge-row">
                <span class="paper-id-badge">${esc(s.id)}</span>
                <span class="paper-source-badge">${esc(s.source === 'semantic_scholar' ? 'Semantic Scholar Graph API' : 'Crossref')}</span>
                ${comp ? '<span class="target-collision-tag">⚡ 碰撞对标文献</span>' : ''}
            </div>
            <h3 class="modal-paper-title">${esc(s.title)}</h3>
            <div class="modal-meta-row">
                <span>👤 <b>作者：</b>${esc(authors)}</span>
                <span>📅 <b>年份：</b>${esc(year)}</span>
                <span>🏛️ <b>刊物/会议：</b>${esc(venue)}</span>
                <span>📈 <b>引用量：</b><b>${cit}</b></span>
            </div>
            ${s.doi ? `<div class="modal-doi-row"><a href="https://doi.org/${encodeURIComponent(s.doi)}" target="_blank" rel="noopener noreferrer" class="doi-btn">访问学术数据库 (DOI: ${esc(s.doi)}) ↗</a></div>` : (s.url ? `<div class="modal-doi-row"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" class="doi-btn">访问文献原链接 ↗</a></div>` : '')}
            ${compSection}
            ${s.tldr ? `<div class="modal-tldr-box"><b>💡 Semantic Scholar TLDR 核心提炼：</b><p>${esc(s.tldr)}</p></div>` : ''}
            <div class="modal-abstract-box">
                <b>📖 文献摘要（Abstract）：</b>
                <p>${esc(s.abstract || '（暂无详细摘要内容，仅提供书目索引记录）')}</p>
            </div>
        </div>
    `;
    modal.hidden = false;
};

function jumpToComparison(sourceId) {
    const el = document.getElementById(`comparison-${sourceId}`) || document.querySelector(`[data-source-id="${sourceId}"]`);
    if (el) {
        if (el.tagName === 'DETAILS') el.open = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.remove('highlight-pulse');
        void el.offsetWidth;
        el.classList.add('highlight-pulse');
    } else {
        notify('该文献在候选文献库中，但未作为主要碰撞文献展示在逐点比对卡片中。');
    }
};

function jumpToClaimCard(idx) {
    const el = document.getElementById(`claim-card-${idx}`);
    if (el) {
        el.open = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.remove('highlight-pulse');
        void el.offsetWidth;
        el.classList.add('highlight-pulse');
    }
};

function toggleAllClaims(openState) {
    const cards = document.querySelectorAll('.claim-accordion-card');
    cards.forEach(c => { c.open = openState; });
};

function filterBranch(branchIdx) {
    if (!currentNoveltyData) return;
    const table = document.getElementById('candidate-table-body');
    if (!table) return;

    const buttons = document.querySelectorAll('.branch-filter-btn');
    buttons.forEach((b, idx) => {
        b.classList.toggle('active', (branchIdx === null && idx === 0) || (branchIdx === idx - 1));
    });

    let allowedPids = null;
    if (branchIdx !== null && currentNoveltyData.taxonomy_tree?.branches?.[branchIdx]) {
        allowedPids = new Set(currentNoveltyData.taxonomy_tree.branches[branchIdx].papers || []);
    }

    const rows = table.querySelectorAll('tr[data-paper-id]');
    rows.forEach(r => {
        const pid = r.getAttribute('data-paper-id');
        if (allowedPids === null || allowedPids.has(pid)) {
            r.style.display = '';
        } else {
            r.style.display = 'none';
        }
    });

    const details = document.getElementById('candidates-details-wrapper');
    if (details) details.open = true;
};

function noveltyTone(item) {
    const j = item.judgment || '';
    const vl = (item.verdict_level || '').toLowerCase();
    if (vl === 'duplicate' || j.includes('抄袭') || j.includes('已被前人做过')) return 'danger';
    if (vl === 'incremental' || j.includes('增量')) return 'warning';
    if (vl === 'uncertain' || j.includes('信息不足') || j.includes('尚不清楚')) return 'neutral';
    return 'success';
}

function noveltyHtml(novelty) {
    if (!novelty || novelty.status === '未启用') {
        return '<p class="muted">未启用思想抄袭与创新性核查。</p>';
    }
    currentNoveltyData = novelty;
    const sources = Object.fromEntries((novelty.sources || []).map(source => [source.id, source]));
    const comparedSourceIds = new Set((novelty.comparisons || []).map(c => c.source_id).filter(Boolean));

    let dupCount = 0, incCount = 0, novCount = 0, uncCount = 0;
    (novelty.comparisons || []).forEach(c => {
        const tone = noveltyTone(c);
        if (tone === 'danger') dupCount++;
        else if (tone === 'warning') incCount++;
        else if (tone === 'neutral') uncCount++;
        else novCount++;
    });

    const st = novelty.status || '';
    const badgeClass = st.includes('抄袭') || st.includes('撞车') ? 'badge-danger' :
        (st.includes('增量') || st.includes('部分创新点信息不足') ? 'badge-warning' :
            (st.includes('信息不足') || st.includes('尚不清楚') ? 'badge-neutral' : 'badge-success'));

    let html = `
    <!-- 模块 1：审查定性与创新诊断看板 -->
    <div class="novelty-dashboard-card">
        <div class="dashboard-header">
            <div class="dashboard-title-wrap">
                <span class="dashboard-subtitle">学术创新性与思想抄袭审查结论</span>
                <h2 class="report-title ${badgeClass}">${esc(novelty.status)}</h2>
            </div>
            <div class="scorecard-grid">
                <div class="scorecard-item ${dupCount > 0 ? 'scorecard-danger' : ''}">
                    <span class="scorecard-num">${dupCount}</span>
                    <span class="scorecard-label">🔴 撞车/已做过</span>
                </div>
                <div class="scorecard-item ${incCount > 0 ? 'scorecard-warning' : ''}">
                    <span class="scorecard-num">${incCount}</span>
                    <span class="scorecard-label">🟡 增量改进</span>
                </div>
                <div class="scorecard-item ${novCount > 0 ? 'scorecard-success' : ''}">
                    <span class="scorecard-num">${novCount}</span>
                    <span class="scorecard-label">🟢 原创良好</span>
                </div>
                ${uncCount > 0 ? `<div class="scorecard-item">
                    <span class="scorecard-num">${uncCount}</span>
                    <span class="scorecard-label">⚪ 信息不足</span>
                </div>` : ''}
            </div>
        </div>
        <div class="dashboard-summary-box">
            <b>💡 专家审查综合评语：</b>
            <p>${esc(novelty.summary || novelty.basis || '')}</p>
        </div>
        <div class="dashboard-meta-bar">
            <span>📚 全网检索候选文献：<b>${(novelty.sources || []).length} 篇</b></span>
            <span>🎯 抽取核心创新主张：<b>${(novelty.comparisons || []).length} 项</b></span>
            ${novelty.taxonomy_tree?.branches ? `<span>🧭 相关技术方向归类：<b>${novelty.taxonomy_tree.branches.length} 个</b></span>` : ''}
        </div>
    </div>`;

    <!-- 模块 2：【核心结果】创新点逐项核查结论清单（一览表） -->
    if (novelty.comparisons && novelty.comparisons.length) {
        html += `
        <div class="claim-quick-table-card">
            <div class="quick-table-header">
                <div>
                    <h3 class="quick-table-title">📋 论文声称的核心创新点及创新性核查一览表</h3>
                    <span class="quick-table-hint">快速查看论文声称的各项创新主张是否足够创新、是否有他人已有工作</span>
                </div>
                <div class="quick-table-actions">
                    <button type="button" class="btn-sm-action" onclick="toggleAllClaims(true)">全部展开详情</button>
                    <button type="button" class="btn-sm-action" onclick="toggleAllClaims(false)">全部收起</button>
                </div>
            </div>
            <div style="overflow-x: auto;">
                <table class="quick-summary-table">
                    <thead>
                        <tr>
                            <th style="width: 50px; text-align: center;">序号</th>
                            <th style="min-width: 220px;">论文声明的核心创新主张</th>
                            <th style="width: 125px; text-align: center;">创新性判定</th>
                            <th style="min-width: 180px;">最接近的前人文献</th>
                            <th style="min-width: 240px;">核心差异与 Delta 分析</th>
                            <th style="width: 110px; text-align: center;">操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${novelty.comparisons.map((item, idx) => {
                            const src = sources[item.source_id] || {};
                            const pillClass = `pill-${noveltyTone(item)}`;
                            return `
                            <tr>
                                <td style="text-align: center; font-weight: bold; color: #555;">#${idx + 1}</td>
                                <td>
                                    <b>“${esc(item.claim || '核心方法')}”</b>
                                    ${item.taxonomy_branch ? `<div class="sub-branch-tag">所属方向：${esc(item.taxonomy_branch)}</div>` : ''}
                                </td>
                                <td style="text-align: center;">
                                    <span class="verdict-pill ${pillClass}">${esc(item.judgment)}</span>
                                </td>
                                <td>
                                    ${src.title ? `
                                        <a href="${esc(src.url || '#')}" target="_blank" rel="noopener noreferrer" class="prior-title-link">《${esc(src.title)}》</a>
                                        <div class="prior-sub-info">${esc(src.year || src.published || '')} · 被引: ${src.citation_count != null ? src.citation_count : '-'}</div>
                                    ` : '<span class="muted">（未检索到直接对标文献）</span>'}
                                </td>
                                <td class="delta-summary-text">${esc(item.difference || '未见明显重合')}</td>
                                <td style="text-align: center;">
                                    <button type="button" class="jump-evidence-btn" onclick="jumpToClaimCard(${idx})">展开详情与对账 ↓</button>
                                </td>
                            </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        </div>`;
    }

    <!-- 模块 3：【逐创新点详细审查卡片】（支持点开看详情：前人工作 · 攻防辩论 · 原文对账） -->
    if (novelty.comparisons && novelty.comparisons.length) {
        html += `
        <div class="section-title-wrap" style="margin-top: 32px;">
            <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px;">
                <div>
                    <h3 class="section-title">🔍 逐创新点详细审查（前人工作 · 攻防辩论 · 原文对账）</h3>
                    <p class="section-desc">每个创新点均可独立点开看详情：了解大家都做了哪些工作、是否存在与他人文章 idea 重合，并查看双栏原文证据。</p>
                </div>
                <div class="accordion-controls">
                    <button type="button" class="btn-link-action" onclick="toggleAllClaims(true)">展开全部</button>
                    <span class="muted" style="margin: 0 4px;">|</span>
                    <button type="button" class="btn-link-action" onclick="toggleAllClaims(false)">收起全部</button>
                </div>
            </div>
        </div>`;
        html += novelty.comparisons.map((item, idx) => {
            const source = sources[item.source_id] || {};
            const itemClass = `finding-${noveltyTone(item)}`;
            const metaInfo = [
                source.year || source.published ? `${source.year || source.published} 年` : '',
                source.venue ? `刊物/会议: ${source.venue}` : '',
                source.citation_count != null ? `引用量: ${source.citation_count}` : ''
            ].filter(Boolean).join(' · ');

            return `
            <details class="claim-accordion-card ${itemClass}" id="claim-card-${idx}" data-source-id="${esc(item.source_id)}" open>
                <summary class="claim-accordion-summary">
                    <div class="summary-left">
                        <span class="claim-number-pill">创新点 #${idx + 1}</span>
                        <span class="summary-claim-title">“${esc(item.claim || '论文核心方法')}”</span>
                        <span class="finding-verdict">${esc(item.judgment)}</span>
                    </div>
                    <div class="summary-right">
                        ${source.title ? `<span class="summary-prior-hint">对标: 《${esc(source.title.length > 28 ? source.title.slice(0, 28) + '…' : source.title)}》</span>` : ''}
                        <span class="accordion-arrow">▼ 点击折叠/展开</span>
                    </div>
                </summary>

                <div class="claim-accordion-body">
                    <!-- 维度 1：大家都做了哪些工作 -->
                    <div class="card-dimension-block dimension-prior">
                        <div class="dimension-header">
                            <span class="dimension-icon">📚</span>
                            <span class="dimension-title">1. 大家都做了哪些工作？（先验文献背景与基线）</span>
                        </div>
                        <div class="dimension-content">
                            <p class="prior-summary-text">${esc(item.prior_works_summary || '该技术子方向上已有前人提出的基线方法与探索。')}</p>
                            ${source.title ? `<div class="prior-art-box">
                                <div class="prior-art-header">
                                    <b>🎯 最为相近的先验文献：</b>
                                    <a href="${esc(source.url || '#')}" target="_blank" rel="noopener noreferrer" class="prior-title-link">《${esc(source.title)}》</a>
                                    <button type="button" class="mini-view-btn" onclick="viewPaper('${esc(item.source_id)}')">查看详情与 S2 TLDR ↗</button>
                                </div>
                                <div class="prior-art-meta">
                                    <span>👤 <b>作者：</b>${esc((source.authors || []).slice(0, 3).join(', ') || '未知作者')}</span>
                                    <span>${esc(metaInfo)}</span>
                                </div>
                            </div>` : '<div class="prior-art-box"><span class="muted">（当前检索库未匹配到可直接对标的先验文献）</span></div>'}
                        </div>
                    </div>

                    <!-- 维度 2：是否有和他人文章 idea 重合？（NoveltyScope 攻防分析） -->
                    <div class="card-dimension-block dimension-debate">
                        <div class="dimension-header">
                            <span class="dimension-icon">⚖️</span>
                            <span class="dimension-title">2. 是否有和他人文章 idea 重合？（攻防比对与 Delta 判定）</span>
                        </div>
                        <div class="dimension-content">
                            <div class="debate-dual-grid">
                                <div class="debate-col debate-prosecutor">
                                    <div class="debate-col-title">🔴 思想重合指控（公诉人视角：哪里雷同了？）</div>
                                    <div class="debate-text">${esc(item.prosecutor_overlap || '在核心问题设定与求解思路上与对标文献具有强相关性。')}</div>
                                </div>
                                <div class="debate-col debate-defender">
                                    <div class="debate-col-title">🟢 独特增量抗辩（辩护人视角：哪里创新了？）</div>
                                    <div class="debate-text">${esc(item.defender_novelty || '论文提出了具体的差异化算法实现、新的约束条件或应用拓展。')}</div>
                                </div>
                            </div>
                            <div class="delta-analysis-callout" style="margin-top: 12px;">
                                <div class="delta-title">💡 法官终审实质差异裁定（Delta 分析）：</div>
                                <div class="delta-content">${esc(item.difference)}</div>
                            </div>
                        </div>
                    </div>

                    <!-- 维度 3：原文证据对账 -->
                    <div class="card-dimension-block dimension-evidence">
                        <div class="dimension-header">
                            <span class="dimension-icon">📄</span>
                            <span class="dimension-title">3. 原文证据对账（待审论文原话 vs 对标文献原话）</span>
                        </div>
                        <div class="dimension-content">
                            <div class="evidence-dual-grid">
                                <div class="evidence-col evidence-paper">
                                    <div class="evidence-col-title">📄 待审论文原文陈述片段（本文说了什么）</div>
                                    <blockquote>${esc(item.paper_quote || '（未摘录）')}</blockquote>
                                </div>
                                <div class="evidence-col evidence-prior">
                                    <div class="evidence-col-title">📚 先验文献对应论述依据（前人说了什么）</div>
                                    <blockquote>${esc(item.source_quote || '（未摘录）')}</blockquote>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </details>`;
        }).join('');
    }

    <!-- 模块 4：【技术方向与背景文献归类】（通俗易懂，作为背景参考） -->
    if (novelty.taxonomy_tree && novelty.taxonomy_tree.branches && novelty.taxonomy_tree.branches.length) {
        const tree = novelty.taxonomy_tree;
        html += `
        <details class="taxonomy-tree-card" style="margin-top: 30px;" open>
            <summary style="cursor: pointer; list-style: none;">
                <div class="taxonomy-header-bar" style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h3 class="taxonomy-title" style="margin: 0;">🧭 论文技术方向与相关文献归类（背景参考）</h3>
                        <p class="taxonomy-guide-text" style="margin: 4px 0 0 0;">梳理该领域的主要技术方向，方便了解本文采用的方法前人有哪些代表性工作。</p>
                    </div>
                    <span class="summary-toggle-hint" style="font-size: 12px; color: #666;">▼ 点击可折叠/展开</span>
                </div>
            </summary>

            <div class="taxonomy-root-banner" style="margin-top: 14px;">
                <div class="root-node-title">🌐 课题所属研究领域：<b>${esc(tree.root_topic || '前沿研究课题')}</b></div>
                <div class="target-node-title">📍 本篇论文所采用的技术方向：<b>${esc(tree.target_position || '')}</b></div>
            </div>

            <div class="taxonomy-tree-layout">
                ${(tree.branches || []).map((b, idx) => `
                    <div class="tree-branch-block ${b.is_target_branch ? 'is-target-branch' : ''}">
                        <div class="branch-card-header">
                            <div class="branch-title-wrap">
                                <span class="branch-badge">方向 ${idx + 1}</span>
                                <h4 class="branch-name">${esc(b.name || '')}</h4>
                                ${b.is_target_branch ? '<span class="target-anchor-badge">★ 本篇论文采用此方向</span>' : ''}
                            </div>
                            <button type="button" class="branch-filter-action-btn" onclick="filterBranch(${idx})" title="在下方文献库中查看该方向论文">筛选文献 (${(b.papers || []).length}篇) ↗</button>
                        </div>
                        <p class="branch-description">${esc(b.description || '')}</p>
                        
                        <div class="branch-papers-container">
                            <div class="container-title">该方向收录的代表文献（点击卡片可查看详情与核心摘要）：</div>
                            <div class="tree-paper-grid">
                                ${(b.papers || []).map(pid => {
                                    const s = sources[pid] || { id: pid, title: pid };
                                    const isCompared = comparedSourceIds.has(pid);
                                    const cit = s.citation_count != null ? s.citation_count : '-';
                                    return `
                                        <div class="tree-paper-chip ${isCompared ? 'chip-compared' : ''}" onclick="viewPaper('${esc(pid)}')" title="${esc(s.title || pid)} (点击查看详情)">
                                            <div class="chip-top">
                                                <span class="chip-id">${esc(pid)}</span>
                                                ${isCompared ? `<span class="chip-status-badge">⚡ 已作对标</span>` : ''}
                                            </div>
                                            <div class="chip-title">《${esc(s.title ? (s.title.length > 55 ? s.title.slice(0, 55) + '…' : s.title) : pid)}》</div>
                                            <div class="chip-meta">
                                                <span>📅 ${esc(s.year || s.published || '-')}</span>
                                                <span>🏛️ ${esc(s.venue ? (s.venue.length > 18 ? s.venue.slice(0, 18) + '…' : s.venue) : '-')}</span>
                                                <span>📈 引用: <b>${cit}</b></span>
                                            </div>
                                            <div class="chip-footer">
                                                <span class="chip-btn-read">查看摘要与详情 ↗</span>
                                                ${isCompared ? `<span class="chip-btn-jump" onclick="event.stopPropagation(); jumpToComparison('${esc(pid)}')">定位原文对账 ↓</span>` : ''}
                                            </div>
                                        </div>
                                    `;
                                }).join('') || '<div class="muted">（暂无文献记录）</div>'}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </details>`;
    }

    <!-- 模块 4：公开学术候选文献库（支持分支联动筛选） -->
    if (novelty.sources && novelty.sources.length) {
        const branches = novelty.taxonomy_tree?.branches || [];
        html += `
        <details class="candidates-details" id="candidates-details-wrapper" style="margin-top: 25px;">
            <summary>
                <span class="summary-title">📚 已检索的公开学术候选文献库（共 ${novelty.sources.length} 篇 · 支持查看 S2 TLDR 与引用量）</span>
                <span class="summary-hint">点击展开全景文献表格</span>
            </summary>
            
            <div class="table-toolbar">
                <span class="toolbar-label">路线快速筛选：</span>
                <button type="button" class="branch-filter-btn active" onclick="filterBranch(null)">全部文献 (${novelty.sources.length})</button>
                ${branches.map((b, idx) => `
                    <button type="button" class="branch-filter-btn" onclick="filterBranch(${idx})">${esc(b.name || `分支${idx+1}`)} (${(b.papers || []).length})</button>
                `).join('')}
            </div>

            <div style="overflow-x: auto; margin-top: 10px;">
                <table class="candidate-table">
                    <thead>
                        <tr>
                            <th style="width: 55px;">编号</th>
                            <th style="min-width: 220px;">论文标题与学术链接</th>
                            <th style="width: 60px;">年份</th>
                            <th style="min-width: 130px;">刊物/会议</th>
                            <th style="width: 65px; text-align: center;">引用数</th>
                            <th style="min-width: 260px;">核心摘要 / TLDR</th>
                            <th style="width: 90px; text-align: center;">操作</th>
                        </tr>
                    </thead>
                    <tbody id="candidate-table-body">
                        ${novelty.sources.map(s => {
                            const isCompared = comparedSourceIds.has(s.id);
                            return `
                            <tr data-paper-id="${esc(s.id)}" class="${isCompared ? 'row-compared' : ''}">
                                <td><b>${esc(s.id)}</b></td>
                                <td>
                                    <a href="${esc(s.url || '#')}" target="_blank" rel="noopener noreferrer"><b>《${esc(s.title)}》</b></a>
                                    ${isCompared ? '<span class="table-collision-tag">⚡ 对标比对</span>' : ''}
                                </td>
                                <td>${esc(s.year || s.published || '-')}</td>
                                <td>${esc(s.venue || '-')}</td>
                                <td style="text-align: center;"><b>${s.citation_count != null ? s.citation_count : '-'}</b></td>
                                <td class="tldr-text">${esc(s.tldr || (s.abstract ? s.abstract.slice(0, 160) + '…' : '（仅书目索引）'))}</td>
                                <td style="text-align: center;">
                                    <button type="button" class="mini-view-btn" onclick="viewPaper('${esc(s.id)}')">详情 ↗</button>
                                </td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        </details>`;
    }

    return html + notesHtml(novelty.notes || []);
}

function citationsHtml(citations) {
    if (!citations || citations.status === '未启用') {
        return '<p class="muted">未启用参考文献防幻觉核查。</p>';
    }
    const badgeClass = citations.phantom_count > 0 ? 'badge-danger' : (citations.mismatch_count > 0 ? 'badge-warning' : 'badge-success');
    let html = `<div class="audit-summary-card">
        <h2 class="report-title ${badgeClass}">${esc(citations.status)}</h2>
        <p class="summary-text">${esc(citations.summary || '')}</p>
        <div class="metrics-row">
            <span class="metric">核查总数: <b>${citations.total_checked || 0}</b></span>
            <span class="metric success">确认真实存在: <b>${citations.verified_count || 0}</b></span>
            <span class="metric warning">元数据偏差: <b>${citations.mismatch_count || 0}</b></span>
            <span class="metric danger">疑似编造/虚构: <b>${citations.phantom_count || 0}</b></span>
        </div>
    </div>`;

    if (citations.items && citations.items.length) {
        html += `<table class="citation-table">
            <thead>
                <tr>
                    <th style="width: 50px;">序号</th>
                    <th>论文著录原文</th>
                    <th>数据库匹配结果</th>
                    <th style="width: 70px;">匹配度</th>
                    <th style="width: 140px;">判定结果</th>
                    <th>说明与建议</th>
                </tr>
            </thead>
            <tbody>` + citations.items.map(it => {
                const rowClass = it.verdict === 'PHANTOM_CITATION' ? 'row-danger' : (it.verdict === 'METADATA_MISMATCH' ? 'row-warning' : 'row-success');
                const pillClass = it.verdict === 'PHANTOM_CITATION' ? 'pill-danger' : (it.verdict === 'METADATA_MISMATCH' ? 'pill-warning' : 'pill-success');
                const matched = it.matched_title ?
                    `<div class="matched-title">《${esc(it.matched_title)}》</div>` +
                    (it.matched_doi ? `<a href="https://doi.org/${encodeURIComponent(it.matched_doi)}" target="_blank" rel="noopener noreferrer" class="doi-link">DOI: ${esc(it.matched_doi)} ↗</a>` : '') :
                    '<span class="muted">（学术数据库无收录记录）</span>';
                return `<tr class="${rowClass}">
                    <td><b>${esc(it.id)}</b></td>
                    <td class="citation-raw">${esc(it.raw)}</td>
                    <td>${matched}</td>
                    <td><b>${Math.round((it.similarity || 0) * 100)}%</b></td>
                    <td><span class="verdict-pill ${pillClass}">${esc(it.status_cn || it.verdict)}</span></td>
                    <td class="citation-note">${esc(it.note || '')}</td>
                </tr>`;
            }).join('') + `</tbody></table>`;
    }
    return html + notesHtml(citations.notes || []);
}

function experimentsHtml(experiments) {
    if (!experiments || !experiments.length) {
        return '<p class="muted">未执行实验材料一致性核查。</p>';
    }
    return experiments.map(experiment => `<section><h3>${esc(experiment.name)} · ${esc(experiment.id)}</h3>
        <p>${esc(experiment.status)}</p>
        ${experiment.repository ? `<p class="muted">仓库版本：${esc(experiment.repository.commit)}；索引 ${experiment.repository.file_count} 个文件，提取 ${(experiment.claims || []).length} 项论文宣称。</p>
        <details><summary>仓库文件与主张阅读范围</summary><pre class="source">${esc(JSON.stringify({files:experiment.repository.files, claims:experiment.claims, reading_records:experiment.reading_records}, null, 2))}</pre></details>` : ''}
        <p class="muted">同名数值字段：${esc((experiment.coverage?.numeric_fields || []).join(', ') || '无')}；完整 ID 列数据文件 ${(experiment.coverage?.id_files || []).length} 份。</p>
        ${(experiment.findings || []).map(f => `<article class="finding audit-finding"><b>${esc(f.status)}</b><p>${esc(f.issue)}</p>
            ${(f.evidence || []).map(e => `<blockquote>${esc(e.filename)} / ${esc(e.location || '')}\n${esc(e.quote ?? e.value ?? '')}</blockquote>`).join('')}
            <p>核查建议：${esc(f.suggestion)}</p></article>`).join('')}
        ${notesHtml(experiment.notes || [])}</section>`).join('');
}

const auditReportCache = new Map();

async function showAuditReport(task, tab) {
    const key = task.id + task.updated_at + tab;
    if (lastAuditRendered === key) return;
    activeReview = null;
    $('#download').hidden = true;
    if (['completed', 'partial'].includes(task.status)) {
        try {
            let report = auditReportCache.get(task.id + task.updated_at);
            if (!report) {
                report = await api(`/audits/${task.id}/report`);
                auditReportCache.set(task.id + task.updated_at, report);
            }
            if (selected !== task.id || currentTab !== tab) return;
            let content = '';
            if (tab === 'novelty') content = noveltyHtml(report.novelty);
            else if (tab === 'citations') content = citationsHtml(report.citations);
            else content = experimentsHtml(report.experiments);

            $('#report').innerHTML = content
                + `<details class="limitations-details"><summary>审查范围与限制声明</summary>${notesHtml(report.limitations || [])}</details>`;
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
