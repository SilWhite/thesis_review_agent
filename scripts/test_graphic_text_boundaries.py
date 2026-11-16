"""Graphic labels stay out of prose checks; adjacent real prose stays in."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from app.checkers.layout_regions import figure_text_regions
from app.checkers.document_model import ThesisDocumentTree,ParagraphData
from app.checkers import DeterministicChecker,LayoutChecker

def line(text,box,size=12):return {'bbox':box,'spans':[{'text':text,'bbox':box,'size':size,'font':'test'}]}
def block(text,box,size=12):return {'type':0,'bbox':box,'lines':[line(text,box,size)]}
class Page:
 rect=fitz.Rect(0,0,600,850)
 def cluster_drawings(self):return [fitz.Rect(x) for x in self.drawings]
 def get_images(self,**kwargs):return []
p=Page();p.drawings=[(90,110,250,230),(280,110,440,230),(90,290,250,410),(280,290,440,410)]
blocks=[block('图2-1 四组实验对比',(150,445,440,460)),block('图2-1 所示。',(85,75,300,92)),block('下一段正常正文。',(85,480,300,496)),block('0 100 200 300',(75,400,250,420),8)]
rs=figure_text_regions(p,blocks);assert len(rs)==1
assert all(rs[0].contains(fitz.Rect(b)) for b in p.drawings)
assert not rs[0].intersects(fitz.Rect(blocks[1]['bbox'])) and not rs[0].intersects(fitz.Rect(blocks[2]['bbox']))
# A prose paragraph between disconnected figures prevents merging upward.
blocks.insert(0,block('这里是两个图片之间的完整正文说明。',(85,245,500,262)))
rs=figure_text_regions(p,blocks);assert rs and rs[0].y0>262
assert not rs[0].contains(fitz.Rect(p.drawings[0]))
c=DeterministicChecker();t=ThesisDocumentTree('axis',all_body_paragraphs=[ParagraphData('a','100 200 300 400 500 600 700 800 900 1000',1),ParagraphData('b','100 200 300 400 500 600 700 800 900 1000',2)])
assert not c._check_rule_2_duplicate_sentences(t)[0]
phrase='The quick brown fox jumps over the lazy dog every morning'
t.all_body_paragraphs=[ParagraphData('a',phrase,1),ParagraphData('b',phrase,2)];assert c._check_rule_2_duplicate_sentences(t)[0]
l=LayoutChecker()
for flag in [True,False]:
 t.all_body_paragraphs=[ParagraphData(str(i),'这是一个单独的短段落。',1,is_figure_text=flag) for i in range(11)]
 assert bool(l._check_rule_31_short_paragraphs(t)[0]) != flag
print('Multi-panel merge, prose boundaries, numeric-axis rejection and real-defect controls passed')
