"""Conservative symbol checks using preserved subscripts and earlier definitions."""
import re
import unicodedata

TOKEN = re.compile(r'(?:[A-Z]{2,}|[A-Za-zα-ωΑ-Ω])(?:_\{[^{}]+\})?')
FUNCTIONS = re.compile(r'transformer_block|MultiHead|Concat|LayerNorm|Attention|Softmax|softmax|ReLU|sigmoid|tanh|sign|sin|cos|tan|log|ln|exp|arg\s*max|arg\s*min|max|min|Pr(?=[_(])|FFN(?=\()|LLM(?=\()')


def normalize(text):
    text = unicodedata.normalize('NFKC', text).replace('−', '-')
    text = text.replace('\u2061', '').replace('\u200b', '')
    text = re.sub(r'_\{√([A-Za-zα-ωΑ-Ω])\}\s*_\{([^{}]*)\}', r'√\1_{\2}', text)
    for _ in range(4):
        text = re.sub(r'_\{([^{}]*)\}\s*_\{([^{}]*)\}', r'_{\1\2}', text)
    return text


def symbols(text):
    text = normalize(text)
    text = re.sub(r'\bs\s*\.\s*t\s*\.', ' ', text)
    text = re.sub(r'P\s+r(?=_\{)', 'Pr', text)
    text = re.sub(r'\([0-9]+[.\-][0-9]+\)\s*$', '', text)
    text = re.sub(r'\\[A-Za-z]+', ' ', text)
    text = re.sub(r'Pr(?:_\{[^{}]*\})*(?=\s*\()', ' ', text)
    text = re.sub(r'[A-Za-z]{2,}(?:_\{[^{}]*\})*(?=\s*\()', ' ', text)
    # A word in a subscript (sys, plan, atk) is part of the symbol's name.
    pieces = re.split(r'(_\{[^{}]*\})', text)
    for i in range(0, len(pieces), 2):
        pieces[i] = FUNCTIONS.sub(' ', pieces[i])
        pieces[i] = re.sub(r'[A-Za-z]{2,}', lambda m: m.group() if
                          m.group().isupper() or re.fullmatch(r'[a-z][A-Z]', m.group()) else ' ', pieces[i])
    text = ''.join(pieces)
    text = re.sub(r'\^\{[^{}]+\}', '', text)
    found = set(TOKEN.findall(text))
    # Summation/integration indices declared in the expression are bound variables.
    bound = set(re.findall(r'[∑∫∏]\s*_\{([A-Za-z])', text))
    if re.search(r'[∑∏]', text):
        bound.update(re.findall(r'(?<![A-Za-z])([A-Za-z])\s*=\s*1\b', text))
    bound.update(re.findall(r'∀\s*([A-Za-z])', text))
    return {s for s in found if s not in bound and not re.search(r'_\{[^}]*[()]', s)}


def base(symbol):
    return symbol.split('_{')[0]


def declared_element_families(context):
    """A stated input set U={u_1,...,u_n} introduces the indexed u family."""
    found = set()
    for sentence in re.split(r'[。；;\n]', normalize(context)):
        if not re.search(r'给定|设|输入|语料|样本|定义|记为', sentence):
            continue
        declaration = re.search(r'=\s*[\{(\[]((?:[^{}]|_\{[^{}]*\}){1,160})[\})\]]', sentence)
        if declaration:
            found.update(base(token) for token in TOKEN.findall(declaration.group(1)) if '_{' in token)
    return found


def assigned_outputs(text):
    text = normalize(text)
    if '=' not in text or re.search(r'[\u4e00-\u9fff]', text):
        return set()
    left = text.split('=', 1)[0].strip()
    # A single output or function on the left is defined by this equation.
    match = TOKEN.match(left)
    if match and (match.end() == len(left) or left[match.end():].lstrip().startswith('(')):
        return {base(match.group())}
    return set()


def has_definition(symbol, context):
    context = normalize(context)
    escaped = re.escape(symbol)
    pattern = rf'(?<![A-Za-z]){escaped}(?![A-Za-z_])'
    for sentence in re.split(r'[。；;\n]', context):
        for match in re.finditer(pattern, sentence):
            after = sentence[match.end():match.end() + 55]
            before = sentence[max(0, match.start() - 14):match.start()]
            if re.search(r'(?:表示|代表|定义为|记为|分别为|为|是|指)', after):
                return True
            if re.search(r'(?:表示|代表|定义为|记为|设|令)\s*$', before):
                return True
            if re.search(r'(?:给定|设|令|记|输入|输出|序列|历史|上下文|参数|样本|集合|矩阵|向量|权重|偏置|维度|模型为|生成器为)\s*$', before):
                return True
            if re.search(r'给定.{0,12}(?:由|含有)\s*$', before) and re.match(r'\s*个', after):
                return True
    return False


def unreadable(text):
    return bool(re.search(r'[\ufffd\ud800-\udfff\ue000-\uf8ff\u0d80-\u0dff]', text))
