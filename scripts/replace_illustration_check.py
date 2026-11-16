from pathlib import Path
p=Path('app/checkers/deterministic_checker.py');s=p.read_text(encoding='utf-8');start=s.index('        # Search in body_text_only',s.index('    def _check_rule_24'))
end=s.index('\n        status = CheckStatus.FINDING.value',start)
s=s[:start]+'''        from .illustration_citations import references, number_key
        cited = references(tree.body_text_only)
        seen = set()
        for kind, label, objects in [('figure', '图', all_figs), ('table', '表', all_tbls)]:
            for item in objects:
                key = number_key(item.num)
                if (kind, key) in seen or (kind == 'figure' and item.is_subfig):
                    continue
                seen.add((kind, key))
                if key in cited[kind]:
                    continue
                findings.append(Finding(
                    rule_id=24, rule_category='确定性检查', dimension='规范与逻辑',
                    severity='major', status='pending_verification', block_id=f'{kind}_{item.num}',
                    quote=item.caption,
                    locations=[EvidenceLocation(page=item.page, quote=item.caption, bbox=list(item.bbox),
                                                description=f'{label}题所在位置')],
                    evidence_note=f'已检查识别出的正文，未找到{label}{item.num}的引用；请重点核对相关段落。图题和目录不计作正文引用。',
                    measurement=f'查找编号：{label}{item.num}（兼容点号、连接号及成组引用）',
                    issue=f'{label} {item.num} 在已识别正文中未找到显式引用。',
                    suggestion=f'请核对相关正文是否引用了{label}{item.num}；确认缺失后补充引用和分析。'))
''' +s[end:];p.write_text(s,encoding='utf-8')
