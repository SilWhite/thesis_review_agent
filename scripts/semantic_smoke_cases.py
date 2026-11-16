"""Small labeled semantic smoke test; results are not a quality estimate."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.checkers.document_model import ChapterData, ParagraphData, ThesisDocumentTree
from app.checkers.semantic_checker import SemanticChecker


def para(text):
    return ParagraphData(id='p1', text=text, page=2)


def cases():
    result = []
    for name, cn, en, expected in [
        ('title_match', '基于深度学习的图像分类研究', 'Research on Image Classification Based on Deep Learning', False),
        ('title_mismatch', '基于深度学习的图像分类研究', 'A Study of Marine Fish Population Dynamics', True),
    ]:
        result.append((name, 3, expected, ThesisDocumentTree(filename=name, title_cn=cn, title_en=en), 'bilingual'))
    for name, cn, en, expected in [
        ('abstract_match', '本文研究图像分类，提出卷积网络，在测试集取得90%的准确率。', 'We study image classification and propose a convolutional network that achieves 90% accuracy on the test set.', False),
        ('abstract_mismatch', '本文研究图像分类，提出卷积网络，在测试集取得90%的准确率。', 'We study ocean temperatures and report a decline in fish populations.', True),
    ]:
        result.append((name, 4, expected, ThesisDocumentTree(filename=name, abstract_cn=[para(cn)], abstract_en=[para(en)]), 'bilingual'))
    chapters = [
        ('chapter_good', '第二章 图像分类方法', '为解决小样本图像分类准确率不足的问题，本章提出迁移学习方法。由于从零训练需要大量标注数据，我们采用预训练网络以减少数据需求。', {10: False, 11: False, 37: False}),
        ('chapter_missing', '第二章 图像分类方法', '网络包含三个卷积层。每层后接归一化和激活函数。随后使用池化层。各层的通道数依次为32、64和128。', {10: True, 11: True, 37: False}),
        ('chapter_wrong_topic', '第二章 图像分类方法', '本章研究海洋鱼类种群数量变化。为解释过度捕捞对鱼类数量的影响，本章建立海洋生态种群模型并分析鱼群繁殖率和捕捞量。', {10: False, 11: False, 37: True}),
    ]
    for name, title, body, expected in chapters:
        ch = ChapterData(title=title, level=1, page=2, role='method', paragraphs=[para(body)])
        result.append((name, expected, None, ThesisDocumentTree(filename=name, chapters=[ch]), 'chapters'))
    return result


def main():
    output = Path(sys.argv[1])
    checker = SemanticChecker(Settings())
    with output.open('w', encoding='utf-8') as out:
        for name, rule, expected, tree, task in cases():
            if len(sys.argv) > 2 and name != sys.argv[2]:
                continue
            start = time.time()
            if task == 'bilingual':
                findings, audits = checker._run_task_1_bilingual_abstract(tree, 'local')
                labels = {rule: expected}
            else:
                findings, audits = checker._run_task_3_core_chapters(tree, 'local')
                labels = rule
            for rid, label in labels.items():
                audit = next(a for a in audits if a.rule_id == rid)
                record = {'case': name, 'rule': rid, 'expected_finding': label,
                          'status': audit.status, 'note': audit.note,
                          'findings': [f.model_dump() for f in findings if f.rule_id == rid],
                          'seconds': round(time.time() - start, 2)}
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                out.flush()
                print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
