"""Unified document representation for graduate thesis format checking."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Literal


@dataclass
class TextSpan:
    text: str
    font_size: float
    font_name: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)


@dataclass
class TextLine:
    text: str
    bbox: Tuple[float, float, float, float]
    font_size: float
    font_name: str
    spans: List[TextSpan] = field(default_factory=list)


@dataclass
class ParagraphData:
    id: str
    text: str
    page: int
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    line_count: int = 1
    height: float = 0.0
    ratio_of_page: float = 0.0
    is_heading: bool = False
    heading_level: int = 0
    font_size: float = 10.5
    font_name: str = ""
    last_line_text: str = ""
    is_caption: bool = False
    is_formula: bool = False
    is_table_cell: bool = False
    is_figure_text: bool = False
    is_footnote: bool = False
    source_pages: List[int] = field(default_factory=list)
    last_line_bbox: Tuple[float, float, float, float] = (0., 0., 0., 0.)


@dataclass
class FigureData:
    num: str
    caption: str
    page: int
    is_subfig: bool = False
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    dpi: float = 300.0


@dataclass
class TableData:
    num: str
    caption: str
    page: int
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    font_size: float = 10.5
    table_text: str = ""


@dataclass
class FormulaData:
    text: str
    has_number: bool
    num_str: str = ""
    page: int = 1
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    context_text: str = ""
    structured_text: str = ""
    definition_context: str = ""
    extraction_status: str = "provided"
    numbering_status: str = "provided"


@dataclass
class ChapterData:
    title: str
    level: int  # 1 for 第X章, 2 for X.X, 3 for X.X.X
    page: int
    end_page: int = 1
    role: str = "unknown"  # intro, survey, method, experiment, summary
    paragraphs: List[ParagraphData] = field(default_factory=list)
    figures: List[FigureData] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    formulas: List[FormulaData] = field(default_factory=list)
    summary_text: str = ""


@dataclass
class ReferenceItem:
    id_str: str  # "1", "2", etc.
    raw_text: str
    authors: str = ""
    year: str = ""
    title: str = ""
    source: str = ""
    pages: str = ""
    ref_type: str = ""  # J, C, D, M, EB/OL
    page_num: int = 1
    source_pages: List[int] = field(default_factory=list)
    segments: List[ParagraphData] = field(default_factory=list)


@dataclass
class PageData:
    page_num: int
    width: float
    height: float
    lines: List[TextLine] = field(default_factory=list)
    paragraphs: List[ParagraphData] = field(default_factory=list)
    images: List[FigureData] = field(default_factory=list)
    has_content: bool = True
    content_height_ratio: float = 0.0
    graphic_regions: List[Tuple[float, float, float, float]] = field(default_factory=list)
    largest_blank: Optional[Tuple[float, float]] = None
    is_toc: bool = False


@dataclass
class ThesisDocumentTree:
    filename: str
    degree: Literal["bachelor", "master", "doctor", "unknown"] = "master"
    total_pages: int = 0
    title_cn: str = ""
    title_en: str = ""
    abstract_cn: List[ParagraphData] = field(default_factory=list)
    abstract_en: List[ParagraphData] = field(default_factory=list)
    chapters: List[ChapterData] = field(default_factory=list)
    conclusion_chapter: Optional[ChapterData] = None
    conclusion_pages_count: float = 0.0
    references: List[ReferenceItem] = field(default_factory=list)
    all_body_paragraphs: List[ParagraphData] = field(default_factory=list)
    body_text_only: str = ""
    all_text: str = ""
    pages: List[PageData] = field(default_factory=list)
