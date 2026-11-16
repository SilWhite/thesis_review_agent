"""Small labelled controls using the existing model, with raw responses retained."""
import json
import os
import hashlib
from threading import Lock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.checkers.document_model import ThesisDocumentTree, ChapterData, ParagraphData
from app.checkers.semantic_checker import SemanticChecker
from app.checkers.semantic_coverage import review_intro, review_body

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
checker = SemanticChecker(Settings(model_url='http://127.0.0.1:8122/v1', model_name='Qwen3.8-27B', model_timeout=600))
import app.checkers.semantic_checker as semantic_module
parser = semantic_module._parse_model_response
raw_outputs = []
trace_lock = Lock()
def parse(content):
    with trace_lock:
        raw_outputs.append(content)
        (out/'raw-model-outputs.json').write_text(json.dumps(raw_outputs,ensure_ascii=False,indent=2))
    return parser(content)
semantic_module._parse_model_response = parse
original = checker._call_llm
records, calls = [], []
replay_path = os.getenv('SEMANTIC_REPLAY_CALLS')
replay = {}
if replay_path:
    replay_source = Path(replay_path)
    for item in json.loads(replay_source.read_text()):
        replay.setdefault(item['prompt'], []).append(item)
    (out/'replay-source.json').write_text(json.dumps({'path':str(replay_source),
        'sha256':hashlib.sha256(replay_source.read_bytes()).hexdigest()}))
def call(prompt, mode):
    if replay_path:
        with trace_lock:
            assert replay.get(prompt), 'No recorded model response for this exact prompt'
            item = replay[prompt].pop(0)
        result, error = item['result'], item['error']
    else:
        result, error = original(prompt, mode)
    with trace_lock:
        calls.append({'prompt': prompt, 'result': result, 'error': error})
        (out/'model-calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2))
    return result, error
checker._call_llm = call

def make(texts, title, role='method'):
    ps = [ParagraphData(str(i), text, i+1) for i, text in enumerate(texts)]
    return ThesisDocumentTree('control', chapters=[ChapterData(title,1,1,role=role,paragraphs=ps)], all_body_paragraphs=ps)

def save(name, rule, expected, fs, a):
    row = {'name':name,'rule':rule,'expected':expected,'found':bool(fs),'audit':a.model_dump(),
           'findings':[f.model_dump() for f in fs]}
    row['correct'] = bool(fs)==expected and a.status in ('发现问题','检查通过')
    records.append(row)
    (out/'controls.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    print(name, rule, row['correct'], a.status,flush=True)

good = ['在低照度条件下，已有图像分类系统的识别结果会明显下降。已有研究使用亮度增强，但放大了噪声，导致弱光细节丢失。',
        '本研究构建保留微弱边缘的特征提取网络，恢复低照度图像中容易消失的类别信息，并通过噪声抑制减少亮度增强带来的干扰。',
        '第二章分析低照度噪声特点，给出噪声模型；第三章使用第二章的噪声模型设计特征提取网络；第四章通过弱光分类实验检验第三章网络能否恢复类别信息。']
bad = ['已有图像分类系统在低照度下识别率低，亮度增强还会放大噪声。',
       '本文拟解决关键问题，突破核心挑战，形成重要贡献，解决瓶颈问题。',
       '本文章节安排如下：第一章绪论，第二章相关技术，第三章方法介绍，第四章实验结果，第五章总结。']
for name, texts, expected in [('paraphrase_and_links',good,False), ('empty_keywords_and_list',bad,True)]:
    t=make(texts,'第一章 绪论','intro')
    fs, aa=review_intro(checker,t,t.chapters[0],'local')
    for rule in (8,9):
        save(name,rule,expected,[f for f in fs if f.rule_id==rule],next(a for a in aa if a.rule_id==rule))

normal = ['本章构建卷积网络完成图像分类。输入图像经多层卷积提取边缘和纹理，再使用分类器预测类别。',
          '虽然训练样本较少，但是数据增强提高了测试集准确率。因为增加了低照度样本，所以模型学会了区分弱光噪声和真实边缘。']
wrong = ['玫瑰需要疏松土壤。栽培者春季修剪老枝，夏季及时浇水。土壤中的腐殖质能够改善根部通气。',
         '番茄栽培应选择排水良好的地块，施肥时应根据植株生长情况控制氮肥。育苗期间需要保持适宜温度。',
         '虽然所有电源已经断开，但是设备因此停止运行。']
for name, texts, title, expected in [('normal_relations',normal,'第三章 图像分类网络',False),
                                     ('sustained_mismatch',wrong,'第三章 图像分类网络',True)]:
    result=review_body(checker,make(texts,title),'local')
    for rule,(fs,a) in result.items():save(name,rule,expected,fs,a)

late = normal[:1]*32 + ['虽然所有电源已经断开，但是设备因此停止运行。']
fs,a=review_body(checker,make(late,'实验运行与供电检查'),'local',(38,))[38]
save('late_error_beyond_24',38,True,fs,a)
grammar=['TCM-m3 模型和TCM-Rerank-v2-m3 模型的训练是Windows11 系统上的 Docker 容器中运行，具体的实验环境配置如表3-1所示。']
fs,a=review_body(checker,make(grammar,'实验环境配置'),'local',(38,))[38]
save('grammar_is_not_logical_connective',38,False,fs,a)
print(json.dumps({'correct':sum(r['correct'] for r in records),'total':len(records)}),flush=True)
