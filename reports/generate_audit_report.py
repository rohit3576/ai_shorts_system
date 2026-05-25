"""Generate the AI Media Platform audit report as Markdown and PDF.

The report is intentionally evidence-based: it reflects the current local
repository state, not only the product vision.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports"
PDF_PATH = OUT_DIR / "AI_Media_Platform_Audit_Report.pdf"
MD_PATH = OUT_DIR / "AI_Media_Platform_Audit_Report.md"

PALETTE = {
    "ink": colors.HexColor("#111827"),
    "muted": colors.HexColor("#475569"),
    "line": colors.HexColor("#CBD5E1"),
    "soft": colors.HexColor("#F8FAFC"),
    "soft2": colors.HexColor("#EEF2FF"),
    "cyan": colors.HexColor("#0891B2"),
    "violet": colors.HexColor("#7C3AED"),
    "green": colors.HexColor("#059669"),
    "amber": colors.HexColor("#D97706"),
    "red": colors.HexColor("#DC2626"),
    "dark": colors.HexColor("#0B1120"),
}


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "AuditTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=33,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "Subtitle": ParagraphStyle(
            "AuditSubtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=11,
            leading=17,
            textColor=colors.HexColor("#D7E5F5"),
            alignment=TA_CENTER,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=PALETTE["dark"],
            spaceBefore=10,
            spaceAfter=8,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=PALETTE["cyan"],
            spaceBefore=10,
            spaceAfter=5,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=PALETTE["ink"],
            spaceAfter=6,
        ),
        "Small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10.5,
            textColor=PALETTE["muted"],
            spaceAfter=4,
        ),
        "Callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#E0F2FE"),
            borderPadding=8,
            leftIndent=0,
            rightIndent=0,
            spaceBefore=6,
            spaceAfter=8,
        ),
        "Code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=6.7,
            leading=8.2,
            textColor=colors.HexColor("#1E293B"),
            backColor=colors.HexColor("#F1F5F9"),
            borderPadding=6,
        ),
        "TOC": ParagraphStyle(
            "TOC",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=PALETTE["ink"],
            spaceAfter=2,
        ),
    }


class CoverPage(Flowable):
    def __init__(self, width: float, height: float) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, _avail_width: float, _avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setFillColor(PALETTE["dark"])
        c.rect(-inch, -inch, self.width + 2 * inch, self.height + 2 * inch, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#07111F"))
        c.circle(self.width * 0.18, self.height * 0.80, 180, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#12213D"))
        c.circle(self.width * 0.86, self.height * 0.18, 220, stroke=0, fill=1)
        c.setFillColor(PALETTE["cyan"])
        c.roundRect(0.3 * inch, self.height - 1.0 * inch, 2.2 * inch, 0.28 * inch, 7, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(1.4 * inch, self.height - 0.91 * inch, "STARTUP TECHNICAL AUDIT")
        c.setFont("Helvetica-Bold", 29)
        c.drawCentredString(self.width / 2, self.height * 0.62, "AI Shorts / AI Media Platform")
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(self.width / 2, self.height * 0.55, "Full CTO, Product, Growth, and Risk Review")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#D7E5F5"))
        c.drawCentredString(self.width / 2, self.height * 0.48, "Local-first autonomous media network audit")
        c.drawCentredString(self.width / 2, self.height * 0.44, "Prepared from repository inspection, runtime artifacts, and current YouTube policy references")
        c.setStrokeColor(colors.HexColor("#38BDF8"))
        c.setLineWidth(1.2)
        c.line(1.0 * inch, self.height * 0.38, self.width - 1.0 * inch, self.height * 0.38)
        c.setFillColor(colors.HexColor("#E2E8F0"))
        c.setFont("Helvetica", 9)
        c.drawCentredString(self.width / 2, 1.15 * inch, "Audit date: May 25, 2026")
        c.drawCentredString(self.width / 2, 0.92 * inch, "Workspace: ai_shorts_system")
        c.restoreState()


class FlowDiagram(Flowable):
    def __init__(
        self,
        labels: list[str],
        *,
        title: str,
        columns: int = 1,
        box_fill: colors.Color = colors.HexColor("#F8FAFC"),
        accent: colors.Color = PALETTE["cyan"],
        width: float = 6.8 * inch,
    ) -> None:
        super().__init__()
        self.labels = labels
        self.title = title
        self.columns = columns
        self.box_fill = box_fill
        self.accent = accent
        self.width = width
        self.height = self._height()

    def _height(self) -> float:
        if self.columns == 1:
            return 0.36 * inch + len(self.labels) * 0.42 * inch + 0.22 * inch
        rows = (len(self.labels) + self.columns - 1) // self.columns
        return 0.45 * inch + rows * 0.58 * inch + 0.25 * inch

    def wrap(self, _avail_width: float, _avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setFillColor(PALETTE["dark"])
        c.setFont("Helvetica-Bold", 10)
        c.drawString(0, self.height - 0.18 * inch, self.title)
        if self.columns == 1:
            x = 0.45 * inch
            y = self.height - 0.65 * inch
            bw = self.width - 0.9 * inch
            bh = 0.30 * inch
            for index, label in enumerate(self.labels):
                c.setFillColor(self.box_fill)
                c.setStrokeColor(self.accent)
                c.roundRect(x, y - index * 0.42 * inch, bw, bh, 8, stroke=1, fill=1)
                c.setFillColor(PALETTE["ink"])
                c.setFont("Helvetica-Bold", 7.7)
                c.drawCentredString(x + bw / 2, y - index * 0.42 * inch + 0.10 * inch, label)
                if index < len(self.labels) - 1:
                    ax = x + bw / 2
                    ay = y - index * 0.42 * inch - 0.01 * inch
                    c.setStrokeColor(PALETTE["muted"])
                    c.line(ax, ay, ax, ay - 0.11 * inch)
                    c.line(ax, ay - 0.11 * inch, ax - 4, ay - 0.07 * inch)
                    c.line(ax, ay - 0.11 * inch, ax + 4, ay - 0.07 * inch)
        else:
            margin = 0.18 * inch
            gutter = 0.14 * inch
            bw = (self.width - 2 * margin - gutter * (self.columns - 1)) / self.columns
            bh = 0.34 * inch
            top = self.height - 0.70 * inch
            for index, label in enumerate(self.labels):
                col = index % self.columns
                row = index // self.columns
                x = margin + col * (bw + gutter)
                y = top - row * 0.58 * inch
                c.setFillColor(self.box_fill)
                c.setStrokeColor(self.accent)
                c.roundRect(x, y, bw, bh, 8, stroke=1, fill=1)
                c.setFillColor(PALETTE["ink"])
                c.setFont("Helvetica-Bold", 6.9)
                c.drawCentredString(x + bw / 2, y + 0.12 * inch, label[:38])
                if index < len(self.labels) - 1:
                    next_col = (index + 1) % self.columns
                    next_row = (index + 1) // self.columns
                    if next_row == row:
                        c.setStrokeColor(PALETTE["muted"])
                        c.line(x + bw, y + bh / 2, x + bw + gutter * 0.75, y + bh / 2)
                    elif col == self.columns - 1:
                        c.setStrokeColor(PALETTE["muted"])
                        c.line(x + bw / 2, y, x + bw / 2, y - 0.18 * inch)
        c.restoreState()


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def bullet_list(items: list[str], sty: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, sty["Body"]), bulletColor=PALETTE["cyan"]) for item in items],
        bulletType="bullet",
        leftIndent=14,
        bulletFontName="Helvetica-Bold",
        bulletFontSize=6,
    )


def make_table(rows: list[list[str]], col_widths: list[float] | None = None, header: bool = True) -> Table:
    data = [[Paragraph(str(cell), styles()["Small"]) for cell in row] for row in rows]
    table = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, PALETTE["line"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), PALETTE["dark"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    for row_idx in range(1 if header else 0, len(rows)):
        if row_idx % 2 == 0:
            commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC")))
    table.setStyle(TableStyle(commands))
    return table


def risk_color(score: int) -> colors.Color:
    if score >= 85:
        return PALETTE["red"]
    if score >= 65:
        return PALETTE["amber"]
    if score >= 45:
        return colors.HexColor("#EAB308")
    return PALETTE["green"]


class RiskBar(Flowable):
    def __init__(self, rows: list[tuple[str, int]], width: float = 6.8 * inch) -> None:
        super().__init__()
        self.rows = rows
        self.width = width
        self.height = 0.26 * inch + len(rows) * 0.32 * inch

    def wrap(self, _avail_width: float, _avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        label_w = 2.7 * inch
        bar_w = self.width - label_w - 0.25 * inch
        y = self.height - 0.25 * inch
        c.setFont("Helvetica-Bold", 8)
        for label, score in self.rows:
            c.setFillColor(PALETTE["ink"])
            c.drawString(0, y, label)
            c.setFillColor(colors.HexColor("#E2E8F0"))
            c.roundRect(label_w, y - 0.02 * inch, bar_w, 0.12 * inch, 3, stroke=0, fill=1)
            c.setFillColor(risk_color(score))
            c.roundRect(label_w, y - 0.02 * inch, bar_w * score / 100, 0.12 * inch, 3, stroke=0, fill=1)
            c.setFillColor(PALETTE["muted"])
            c.setFont("Helvetica", 7)
            c.drawRightString(self.width, y, f"{score}/100")
            y -= 0.32 * inch
        c.restoreState()


def add_header_footer(canvas, doc) -> None:
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(PALETTE["muted"])
        canvas.drawString(doc.leftMargin, LETTER[1] - 0.36 * inch, "AI Media Platform Technical Audit")
        canvas.drawRightString(LETTER[0] - doc.rightMargin, 0.32 * inch, f"Page {doc.page}")
        canvas.setStrokeColor(PALETTE["line"])
        canvas.line(doc.leftMargin, LETTER[1] - 0.43 * inch, LETTER[0] - doc.rightMargin, LETTER[1] - 0.43 * inch)
    canvas.restoreState()


CORE_PIPELINE = [
    "YouTube source monitoring",
    "yt-dlp download",
    "FFmpeg audio extraction",
    "whisper.cpp transcription",
    "Ollama clip detection",
    "Retention scoring",
    "ASS subtitles + FFmpeg render",
    "Upload queue",
    "Analytics capture",
    "Learning dataset export",
]

RETENTION_ENGINE = [
    "Transcript excerpt",
    "Hook template variants",
    "Keyword/emotion heuristics",
    "Dead-zone transcript scan",
    "Persona prior",
    "Retention/viral probability",
    "Review/render/auto-schedule decision",
]

LEARNING_LOOP = [
    "Generated Short",
    "Human review",
    "Upload + analytics",
    "LearningEvent row",
    "JSONL dataset",
    "Hook/trend priors",
    "Future scoring",
]

MULTI_CHANNEL = [
    "Managed channel",
    "ChannelProfile persona",
    "SourceFeed",
    "Shared local pipeline",
    "ClipIntelligence",
    "UploadRecommendation",
    "RevenueSnapshot",
    "Network dashboard",
]

FUTURE_SCALE = [
    "FastAPI control plane",
    "Worker queue",
    "Media storage lifecycle",
    "PostgreSQL",
    "GPU/CPU worker pools",
    "Analytics warehouse",
    "Rights/compliance gate",
    "Creator SaaS workspace",
]

UPLOAD_REVIEW = [
    "Generated clip",
    "Human review",
    "Approve",
    "Regenerate hook",
    "Rerender",
    "Reject as negative sample",
    "Upload recommendation",
    "Schedule / dry-run upload",
    "Analytics snapshot",
]

TREND_FLOW = [
    "Video titles + descriptions",
    "Clip titles + hooks",
    "Hashtags",
    "Analytics weighting",
    "TrendSignal table",
    "Rising / overused heat",
    "Upload intelligence",
]

AI_DECISION = [
    "Transcript candidate",
    "Ollama score",
    "Persona prior",
    "Hook variants",
    "Dead-zone report",
    "Retention score",
    "Decision gate",
]

ANALYTICS_FLOW = [
    "Uploaded Short",
    "YouTube Data API",
    "YouTube Analytics API",
    "AnalyticsSnapshot",
    "RevenueSnapshot",
    "LearningEvent",
    "Dashboard insights",
]


def report_markdown() -> str:
    return dedent(
        """
        # AI Shorts / AI Media Platform - Full Deep Audit

        **Audit date:** May 25, 2026  
        **Project:** `ai_shorts_system`  
        **Scope:** architecture, scalability, reliability, retention intelligence, dashboard UX, product strategy, monetization, YouTube survivability, technical debt, and SaaS potential.

        ## Executive Summary

        The system is a credible local-first prototype for automating the mechanics of Shorts creation. It has a real pipeline boundary: monitor source channels, download with `yt-dlp`, extract audio through FFmpeg, transcribe with whisper.cpp, detect clips with Ollama plus heuristics, generate captions/subtitles, render a vertical MP4, queue uploads, and show a React/Tailwind dashboard. That is meaningful.

        The hard truth: it is not yet a true self-improving retention engine. The current database contains one channel and one channel profile, but zero persisted videos, clips, clip intelligence records, analytics snapshots, uploads, revenue snapshots, trend signals, or learning events. The local `data/training/*.jsonl` files are empty. The successful `final_short.mp4` exists on disk, but it is not represented in the database learning loop. As a result, most current "learning" dashboards are priors, fallback examples, demo rows, or heuristic estimates rather than validated performance intelligence.

        The project can become valuable, but only if it pivots from "autonomous repost machine" toward "permissioned creator content operating system." The highest risk is not compute. It is YouTube survivability: reused-content monetization risk, copyright/Content ID exposure, repetitive mass-produced channel patterns, and low originality signals.

        ## Evidence Snapshot

        - Repository application code inspected across `app/`, `database/`, dashboard frontend, and `test_pipeline.py`.
        - Approximate local source footprint: 14,308 lines across 81 files.
        - Runtime artifact present: `data/clips/final_short.mp4` (5.8 MB).
        - Training dataset exports present but empty: `clip_outcomes.jsonl`, `successful_clips.jsonl`, `failed_clips.jsonl`, `hook_performance.jsonl`, `dead_zone_patterns.jsonl`.
        - SQLite database state observed: `channels=1`, `channel_profiles=1`, all clip/analytics/learning/revenue/upload/trend tables at `0`.

        ## Core Shorts Pipeline

        ```mermaid
        flowchart TD
          A[YouTube Source] --> B[Monitor RSS / SourceFeed]
          B --> C[yt-dlp Download]
          C --> D[FFmpeg Audio Extract]
          D --> E[whisper.cpp Transcript]
          E --> F[Ollama Viral Clip Detection]
          F --> G[Retention + Dead-Zone Scoring]
          G --> H[ASS Captions + Hook]
          H --> I[FFmpeg Vertical Render]
          I --> J[Upload Queue]
          J --> K[YouTube Analytics]
          K --> L[Learning Dataset]
          L --> F
        ```

        ## Retention Intelligence Engine

        ```mermaid
        flowchart LR
          A[Transcript Window] --> B[Keyword and Pacing Signals]
          A --> C[Dead-Zone Detector]
          A --> D[Hook Template Engine]
          E[Channel Persona] --> B
          F[Ollama Candidate Score] --> G[RetentionScorer]
          B --> G
          C --> G
          D --> G
          G --> H[ClipIntelligence]
          H --> I[Decision: review / render / auto_schedule]
        ```

        ## Learning Feedback Loop

        ```mermaid
        flowchart TD
          A[Generated Short] --> B[Human Review]
          B --> C[Upload / Schedule]
          C --> D[Analytics Snapshot]
          D --> E[LearningEvent]
          E --> F[JSONL Training Dataset]
          F --> G[Hook Ranking + Pattern Memory]
          G --> H[Future Clip Scoring]
          H --> A
        ```

        ## Multi-Channel Architecture

        ```mermaid
        flowchart TD
          A[Gaming Channel] --> D[Shared Local Pipeline]
          B[Nature / Survival Channel] --> D
          C[Podcast Clips Channel] --> D
          D --> E[Per-Channel Persona]
          E --> F[Clip Intelligence]
          F --> G[Upload Recommendations]
          G --> H[Analytics + Revenue]
          H --> I[Learning Engine]
        ```

        ## Dashboard System

        ```mermaid
        flowchart LR
          A[FastAPI Routes] --> B[Dashboard Services]
          B --> C[SQLite ORM]
          B --> D[Media Files]
          A --> E[Jinja Bootstrap]
          E --> F[React/Tailwind App]
          F --> G[Charts + Clip Review UI]
          F --> H[Dashboard APIs]
          H --> B
        ```

        ## Upload / Review Workflow

        ```mermaid
        flowchart TD
          A[Generated Clip] --> B[Human Review]
          B --> C{Decision}
          C -->|Approve| D[Upload Recommendation]
          C -->|Regenerate| E[Hook / Subtitle / Rerender]
          C -->|Reject| F[Negative Learning Sample]
          D --> G[Schedule or Dry Run]
          G --> H[Analytics Snapshot]
          H --> I[LearningEvent]
        ```

        ## Trend Detection Flow

        ```mermaid
        flowchart LR
          A[Source Metadata] --> D[Local Token Mining]
          B[Clip Hooks / Titles] --> D
          C[Analytics Weighting] --> D
          D --> E[TrendSignal]
          E --> F[Rising Topics]
          E --> G[Overused Trends]
          F --> H[Upload Intelligence]
        ```

        ## Revenue Estimation Flow

        ```mermaid
        flowchart LR
          A[Views] --> B[Retention Avg]
          B --> C[Estimated Watch Hours]
          A --> D[RPM Assumption]
          D --> E[Estimated Revenue]
          C --> F[ROI / Forecast]
          E --> F
        ```

        ## AI Decision Engine

        ```mermaid
        flowchart TD
          A[Transcript Candidate] --> B[Ollama Score]
          A --> C[Hook Variants]
          A --> D[Dead-Zone Scan]
          E[Channel Persona] --> F[RetentionScorer]
          B --> F
          C --> F
          D --> F
          F --> G{Decision}
          G -->|High| H[Auto Schedule Candidate]
          G -->|Medium| I[Render / Review]
          G -->|Low| J[Reject or Defer]
        ```

        ## Future Scaling Architecture

        ```mermaid
        flowchart TD
          A[FastAPI Control Plane] --> B[Durable Job Queue]
          B --> C[Download Worker]
          B --> D[Transcription Worker]
          B --> E[Render Worker]
          C --> F[Media Storage Lifecycle]
          D --> G[PostgreSQL]
          E --> G
          G --> H[Analytics Warehouse]
          H --> I[Retention Learning]
        ```

        ## Database Relationship Diagram

        ```mermaid
        erDiagram
          Channel ||--o{{ Video : has
          Video ||--o{{ Clip : produces
          Clip ||--o{{ Upload : queues
          Clip ||--o{{ AnalyticsSnapshot : measures
          Channel ||--|| ChannelProfile : strategy
          Clip ||--|| ClipIntelligence : scores
          Clip ||--o{{ LearningEvent : trains
          Channel ||--o{{ SourceFeed : monitors
          Clip ||--o{{ RevenueSnapshot : estimates
          Clip ||--o{{ UploadRecommendation : recommends
        ```

        ## Key Verdict

        This is best viewed today as a strong local automation prototype and a promising internal tool for repurposing owned or permissioned long-form content. It is not yet safe or economically proven as an autonomous AI media company, and it is not ready as a SaaS product until it has job isolation, authentication, migrations, validated analytics feedback, explicit rights/originality workflows, and a less misleading intelligence dashboard.

        ## Official Policy Sources Used

        - YouTube channel monetization policies: https://support.google.com/youtube/answer/1311392
        - YouTube Shorts monetization policies: https://support.google.com/youtube/answer/12504220
        - YouTube Partner Program overview and eligibility: https://support.google.com/youtube/answer/72851
        - YouTube spam/deceptive practices policies: https://support.google.com/youtube/answer/2801973
        - Fair use on YouTube: https://support.google.com/youtube/answer/9783148
        - YouTube Data API videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert
        - YouTube Data API quota calculator: https://developers.google.com/youtube/v3/determine_quota_cost
        """
    ).strip() + "\n"


def section(story: list, title: str, body: list, sty: dict[str, ParagraphStyle]) -> None:
    story.append(p(title, sty["H1"]))
    for item in body:
        if isinstance(item, str):
            story.append(p(item, sty["Body"]))
        else:
            story.append(item)
    story.append(Spacer(1, 0.08 * inch))


def build_pdf() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sty = styles()
    doc = BaseDocTemplate(
        str(PDF_PATH),
        pagesize=LETTER,
        leftMargin=0.62 * inch,
        rightMargin=0.62 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.55 * inch,
        title="AI Media Platform Audit Report",
        author="Codex",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=add_header_footer)])

    story: list = []
    story.append(CoverPage(doc.width, doc.height))
    story.append(PageBreak())

    story.append(p("Table of Contents", sty["H1"]))
    toc_items = [
        "1. Executive summary",
        "2. Architecture and pipeline review",
        "3. AI quality and retention-engine audit",
        "4. Learning-loop and dataset audit",
        "5. Dashboard and product workflow review",
        "6. Multi-channel and scaling review",
        "7. YouTube policy, copyright, and automation risk",
        "8. Monetization and business model review",
        "9. Risk, priority, technical debt, and SWOT matrices",
        "10. Roadmaps and final strategic verdict",
    ]
    for item in toc_items:
        story.append(p(item, sty["TOC"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(p("Audit Thesis", sty["H2"]))
    story.append(
        p(
            "The project has crossed the important line from idea to working prototype. "
            "The next line is harder: turning generated videos into a measurable, defensible, policy-safe media operation. "
            "Right now the automation is more real than the learning.",
            sty["Callout"],
        )
    )
    story.append(PageBreak())

    section(
        story,
        "1. Executive Summary",
        [
            "Overall grade: prototype engineering 6.5/10, retention intelligence 3.0/10, YouTube survivability 3.5/10, SaaS readiness 3.0/10, internal creator-tool potential 7.0/10.",
            "The local pipeline is credible. `ShortsPipeline` coordinates scanning, downloading, transcription, clip detection, retention scoring, subtitle generation, rendering, upload recommendation, and optional upload in `app/pipeline.py:51-184`. The database now contains a broad schema for videos, clips, analytics, channel profiles, source feeds, clip intelligence, trend signals, learning events, revenue snapshots, and upload recommendations in `database/models.py:30-294`.",
            "The largest weakness is not architecture ambition; it is evidence quality. The system claims learning, but the observed database has zero persisted clips, zero analytics snapshots, zero clip intelligence records, and zero learning events. Training exports exist but are empty. The successful `final_short.mp4` is a file-system artifact, not a learning sample.",
            "The largest business risk is platform policy. A system optimized to scrape other creators and mass-produce Shorts has high reused-content, copyright, spam, and demonetization exposure. It becomes much more viable when positioned around owned or licensed long-form content, creator repurposing, human review, and original commentary or narration.",
            RiskBar(
                [
                    ("YouTube reused-content / copyright risk", 94),
                    ("Fake learning / unvalidated scores", 90),
                    ("Heavy jobs inside web process", 82),
                    ("No durable job queue or migrations", 76),
                    ("Revenue model overdependence on Shorts RPM", 73),
                    ("Local laptop resource bottleneck", 68),
                ]
            ),
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "2. Architecture Review",
        [
            FlowDiagram(CORE_PIPELINE, title="Core Shorts Pipeline", columns=2),
            "Strength: the module boundaries are understandable and map to real operational stages: scraper, downloader, transcription, clip detector, captions, editor, uploader, analytics, scheduler, dashboard, and intelligence modules.",
            "Weakness: orchestration is synchronous and centralized. A single `process_video` call walks through every expensive step in one session path. This is fine for a laptop proof of concept but brittle for unattended multi-channel operation.",
            "The current API uses FastAPI `BackgroundTasks` to start processing (`app/api.py:130-141`). That is convenient, but it is not a durable job queue. If the process exits, the work is gone. There is no persisted job heartbeat, cancellation, retry policy per stage, or concurrency budget.",
            "Database initialization uses `Base.metadata.create_all` (`database/init_db.py:14`). This is good for a greenfield local database, but it is not a migration system. Any production or SaaS path needs Alembic before schema changes become dangerous.",
            "Important code defect: `SourceIngestionService._ensure_source_channel` passes `metadata_json` into `Channel` at `app/intelligence/sources.py:137`, but `Channel` has no `metadata_json` column in `database/models.py:30-43`. Playlist/source ingestion can fail at runtime when creating a synthetic channel.",
        ],
        sty,
    )

    section(
        story,
        "2A. Required System Diagrams",
        [
            FlowDiagram(UPLOAD_REVIEW, title="Upload / Review Workflow", columns=3, accent=PALETTE["green"]),
            FlowDiagram(TREND_FLOW, title="Trend Detection Flow", columns=2, accent=PALETTE["violet"]),
            FlowDiagram(ANALYTICS_FLOW, title="Analytics Flow", columns=2, accent=PALETTE["cyan"]),
            FlowDiagram(AI_DECISION, title="AI Decision Engine", columns=2, accent=PALETTE["amber"]),
            FlowDiagram(FUTURE_SCALE, title="Future Scaling Architecture", columns=2, accent=PALETTE["red"]),
        ],
        sty,
    )

    section(
        story,
        "3. Pipeline Bottlenecks and Reliability Risks",
        [
            make_table(
                [
                    ["Area", "Current State", "Risk", "Recommendation"],
                    ["Download", "yt-dlp subprocess downloads highest quality via `app/downloader/service.py:21-47`.", "Network failures, throttling, filename variance, long-running calls.", "Persist per-stage attempts and raw error class; add stage-level resume/skip controls."],
                    ["Audio", "FFmpeg extracts 16 kHz mono WAV, despite method name `extract_mp3`.", "README says MP3 in places; implementation uses WAV. Confusion can break downstream docs.", "Rename method/docs later; keep WAV because whisper.cpp likes it."],
                    ["Transcription", "whisper.cpp JSON is normalized in `app/transcription/service.py:42-126`.", "Tiny/base models may produce weak word timings; silence and sentence boundaries affect clips.", "Store confidence, WER proxy, language, and word timestamp coverage."],
                    ["Clip Detection", "Ollama JSON with fallback heuristics in `app/clip_detector/service.py:31-315`.", "LLM outputs are uncalibrated; fallback can pick generic moments.", "Always store rejected candidates and reasons, not only winners."],
                    ["Rendering", "FFmpeg render and OpenCV focus estimation in `app/editor/service.py:25-165`.", "CPU bottleneck; one bad filter/path stalls job; no progress reporting.", "Move render jobs to worker queue; store ffmpeg stderr tail and duration."],
                    ["Upload", "Dry-run by default; OAuth uploader in `app/uploader/service.py`.", "OAuth local browser flow is awkward on servers; unverified API projects can restrict upload privacy.", "Keep human approval and policy gate before upload."],
                ],
                [0.95 * inch, 1.95 * inch, 1.75 * inch, 2.05 * inch],
            ),
            "Storage growth will become a real constraint before database scale does. Source videos, WAV files, transcripts, rendered clips, previews, subtitles, and logs need retention rules. A laptop-first system should add a media lifecycle policy before multi-channel monitoring is left unattended.",
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "4. AI Quality and Retention Engine Audit",
        [
            FlowDiagram(RETENTION_ENGINE, title="Retention Intelligence Engine", columns=1, accent=PALETTE["violet"]),
            "The retention engine is useful as an editorial prior, but it should not yet be treated as predictive AI. `RetentionScorer.score_text` combines model score, keyword buckets, pacing, hook strength, emotion, surprise, conflict, payoff, and a dead-zone penalty (`app/intelligence/retention.py:137-214`). This is deterministic heuristic scoring, not learned prediction.",
            "Current risks: keyword matching overweights obvious words, misses visual context, misses actual first-frame and first-two-second behavior, and cannot distinguish genuine narrative payoff from clickbait wording. The viral probability formula is mathematically neat but uncalibrated: `(retention / 100) ** 1.18` at `app/intelligence/retention.py:181`.",
            "Dead-zone detection is transcript-first. `DeadZoneDetector` scores silence gaps, low pacing, low emotion, and filler terms (`app/intelligence/deadzone.py:34-101`). This is directionally useful, but low-motion is currently `None`, so one of the requested quality signals is not truly measured.",
            "Hook generation is template-based, not generative experimentation. The `HookTemplateEngine` has useful categories (curiosity, fear, surprise, emotional, conflict, authority), but the templates are generic. Without A/B outcomes, the system will converge on templates that score well internally, not necessarily hooks that retain viewers.",
            p("Brutal read: the current scoring layer can help rank obvious candidate clips. It cannot yet predict retention with investor-grade confidence.", sty["Callout"]),
        ],
        sty,
    )

    section(
        story,
        "5. Learning Loop and Dataset Audit",
        [
            FlowDiagram(LEARNING_LOOP, title="Learning Feedback Loop", columns=1, accent=PALETTE["green"]),
            "The learning architecture exists: `LearningEvent`, JSONL exports, hook performance aggregation, best/avoid patterns, and viral pattern memory. But the observed dataset is empty, and `_outcome_score` falls back to predicted score when analytics are absent (`app/intelligence/learning.py:124-135`). That creates a circular loop: the model learns from its own guesses.",
            "Real learning requires ground truth that is independent of the scorer: actual views over time, swipe-away or average view percentage, retention curve, first 3-second hold, rewatch rate, likes per view, comments per view, subscriber conversion, and upload timing. The current system mostly stores totals and averages.",
            "The biggest missing feedback loop is candidate-level negatives. The system should store not only rendered clips, but all candidate windows considered and rejected. Otherwise it only learns from winners it already believed in.",
            make_table(
                [
                    ["Signal", "Current Availability", "Value", "Gap"],
                    ["Views / likes / comments", "Schema exists through analytics snapshots.", "Useful but noisy.", "Needs time-windowed deltas, not only latest totals."],
                    ["Average retention", "Optional YouTube Analytics field.", "Very valuable.", "Often missing; no retention curve or first 3 seconds."],
                    ["Hook type", "Stored in clip/intelligence metadata.", "Useful if A/B tested.", "Currently template-derived and sparsely validated."],
                    ["Dead-zone score", "Stored when transcript exists.", "Useful for avoiding boring clips.", "No actual motion score, no audio energy."],
                    ["Human review", "Approve/reject/rerender endpoints exist.", "High-value editorial label.", "Needs mandatory reason taxonomy, not free text only."],
                    ["Rights/originality", "Not modeled.", "Critical.", "Must be a first-class gate before upload."],
                ],
                [1.35 * inch, 1.75 * inch, 1.3 * inch, 2.15 * inch],
            ),
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "6. Dashboard and Workflow Review",
        [
            FlowDiagram(
                ["FastAPI dashboard routes", "Dashboard services", "Jinja bootstrap", "React/Tailwind app", "Chart.js views", "Review controls", "Media preview"],
                title="Dashboard System",
                columns=2,
            ),
            "The dashboard is visually strong for a prototype: dark UI, React/Tailwind, charts, clip cards, AI insights, trends, revenue, upload intelligence, learning, logs, and settings. It gives the project a product surface instead of only scripts.",
            "The biggest UX risk is credibility. Dashboard services use filesystem fallbacks and demo data (`app/dashboard/services.py:63`, `app/dashboard/services.py:576`, `app/intelligence/revenue.py:133`). That is useful for empty states, but dangerous if presented as real intelligence. The UI should label demo/fallback data explicitly.",
            "Several dashboard API GET routes mutate state indirectly by refreshing trends, revenue, upload recommendations, or exporting learning data. Example: learning payload exports datasets on read. This can surprise users and slow page loads. GET should generally read; POST should refresh.",
            "Missing product controls: job cancellation, retry failed stage, clear artifact, mark rights status, select source license, compare hooks, side-by-side candidate scoring, and approve with required reason labels.",
        ],
        sty,
    )

    section(
        story,
        "7. Multi-Channel Scaling Review",
        [
            FlowDiagram(MULTI_CHANNEL, title="Multi-Channel Architecture", columns=2, accent=PALETTE["violet"]),
            "Channel personas are a smart, lightweight abstraction. The presets in `app/intelligence/profiles.py` let gaming, nature/survival, podcast, documentary, and general channels use different pacing, subtitles, hooks, schedules, and emotional priors.",
            "Where it breaks: all channels share one local pipeline, one database, one scheduler, and one set of CPU-heavy tools. Multi-channel monitoring will collapse quality before it collapses storage: rushing output volume increases reused-content risk, generic hooks, repetitive templates, and brand dilution.",
            "A local-first multi-channel system should scale by throughput budgets: clips per channel per day, max render minutes per day, review queue capacity, storage cap, upload cap, and quality floor. Without those controls, automation will produce more weak content faster.",
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "8. YouTube Risk Review",
        [
            "Official YouTube monetization policy emphasizes original and authentic content, and says borrowed content must be changed significantly to become your own. It also says mass-produced or repetitive content can affect channel-level monetization. YouTube Shorts monetization excludes non-original Shorts such as unedited clips, reuploads, or compilations with no original content added. Spam policy also calls out massively uploading scraped content and autogenerated content posted without regard for quality or viewer experience.",
            "This creates a direct strategic warning: an autonomous system that monitors other creators, clips viral moments, adds subtitles, and uploads at scale is structurally exposed to reused-content and spam interpretations unless it adds meaningful original commentary, narration, analysis, licensing, or creator participation.",
            make_table(
                [
                    ["Risk", "Severity", "Why It Matters", "Mitigation"],
                    ["Copyright / Content ID", "Critical", "Claims can block, monetize for rightsholder, or create strikes.", "Use owned, licensed, public-domain, or clearly fair-use commentary workflows."],
                    ["Reused-content monetization", "Critical", "Permission alone does not guarantee monetization suitability.", "Add visible creator commentary, voiceover, analysis, storyline, and transformative framing."],
                    ["Mass-produced repetitive content", "High", "Template-like Shorts across channels may look inauthentic.", "Limit volume; vary formats; require human review; track uniqueness."],
                    ["Misleading metadata", "High", "Strong hooks can cross into clickbait if payoff is absent.", "Validate hook/payoff alignment before upload."],
                    ["Automation detection / spam", "High", "Unreviewed high-volume posting creates platform trust risk.", "Keep manual approval, cadence caps, and quality thresholds."],
                    ["API project restrictions", "Medium", "Unverified upload projects may be restricted; quota is finite.", "Plan for verification and quota governance before scale."],
                ],
                [1.15 * inch, 0.8 * inch, 2.0 * inch, 2.4 * inch],
            ),
            p("Policy-safe direction: build for creators clipping their own content first. Treat third-party clipping as a rights-managed editorial workflow, not a default automation path.", sty["Callout"]),
        ],
        sty,
    )

    section(
        story,
        "9. Monetization and Business Model Review",
        [
            FlowDiagram(
                ["Views", "Engaged views", "RPM assumption", "Estimated revenue", "Monthly projection", "Channel ROI"],
                title="Revenue Estimation Flow",
                columns=2,
                accent=PALETTE["green"],
            ),
            "Shorts ad revenue alone is a weak business foundation unless the system reaches huge volume with strong originality. The current revenue estimator is useful as a dashboard placeholder, but RPM assumptions are manually configured and default to very low values (`ChannelProfile.estimated_shorts_rpm`, default 0.06).",
            "Better monetization paths: (1) internal agency tool for clients with permissioned long-form content, (2) SaaS for creators/podcasters/gamers who need repurposing workflows, (3) licensing-safe content studio around owned channels, (4) retention analytics and hook testing product, (5) managed service where AI accelerates editors rather than replaces them.",
            "Investor-grade value will not come from claiming autonomous viral content. It will come from defensible data, rights-safe workflow, creator ROI, retention lift, and repeatable production economics.",
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "10. Risk Matrix",
        [
            make_table(
                [
                    ["Risk", "Probability", "Impact", "Severity", "Owner Action"],
                    ["Reused-content / copyright policy failure", "High", "Critical", "P0", "Add rights/originality gate before every upload."],
                    ["Learning loop trains on predictions, not outcomes", "High", "High", "P0", "Persist actual analytics, negatives, and human labels."],
                    ["Background jobs lost on crash", "Medium", "High", "P1", "Introduce durable local queue or persisted job table."],
                    ["No migrations", "High", "Medium", "P1", "Add Alembic before next schema changes."],
                    ["Dashboard demo data mistaken for real analytics", "High", "Medium", "P0", "Label or remove demo fallbacks in production mode."],
                    ["Generic hooks reduce retention", "Medium", "Medium", "P1", "A/B hook testing and payoff validation."],
                    ["Storage fills laptop", "Medium", "Medium", "P1", "Media retention rules and cleanup UI."],
                    ["OAuth/upload failures", "Medium", "Medium", "P2", "Better token state and upload retry UX."],
                ],
                [1.75 * inch, 0.85 * inch, 0.75 * inch, 0.55 * inch, 2.75 * inch],
            )
        ],
        sty,
    )

    section(
        story,
        "11. Technical Debt Matrix",
        [
            make_table(
                [
                    ["Debt", "Evidence", "Why It Matters", "Fix"],
                    ["No durable pipeline state", "`BackgroundTasks` starts process, scheduler only interval-based.", "Jobs are not resilient to restart.", "Persist stage state, attempt count, duration, stderr, and next action."],
                    ["No schema migrations", "`create_all` only.", "Schema drift will break existing databases.", "Add Alembic with baseline migration."],
                    ["GET routes with side effects", "Dashboard payloads can refresh/export.", "Slow, surprising, hard to cache.", "Split read endpoints from refresh POSTs."],
                    ["Demo/fallback analytics", "`filesystem_clips`, `demo_timeline`, `_demo_rows`.", "Misleads product decisions.", "Show explicit demo badge or remove in production."],
                    ["SourceFeed bug", "`Channel(metadata_json=...)` without column.", "Playlist ingestion runtime error.", "Remove arg or add column intentionally."],
                    ["Metadata JSON overuse", "Many important fields stored in JSON blobs.", "Hard to query, migrate, validate.", "Promote stable strategy/performance fields to columns."],
                    ["Pipeline not capturing test output", "`final_short.mp4` bypasses DB.", "Successful run cannot train system.", "Import test outputs as Clip rows or run canonical pipeline."],
                ],
                [1.25 * inch, 1.55 * inch, 1.85 * inch, 2.25 * inch],
            )
        ],
        sty,
    )

    section(
        story,
        "12. Priority Matrix",
        [
            make_table(
                [
                    ["Priority", "Item", "ROI", "Complexity", "Why Now"],
                    ["P0", "Rights/originality gate", "Very high", "Medium", "Prevents the project from becoming unsafe at scale."],
                    ["P0", "Real outcome dataset", "Very high", "Medium", "Turns intelligence from placebo into measurable learning."],
                    ["P0", "Remove/label demo data", "High", "Low", "Protects operator trust."],
                    ["P1", "Durable local job queue", "High", "Medium", "Needed before unattended multi-channel runs."],
                    ["P1", "Candidate negative sampling", "High", "Medium", "Required for learning why clips fail."],
                    ["P1", "Retention metric calibration", "High", "Medium", "Makes scores useful for decisions."],
                    ["P2", "Postgres migration path", "Medium", "Medium", "Needed later, not before data truth."],
                    ["P2", "Advanced trend scraping", "Medium", "High", "Less urgent than internal performance learning."],
                ],
                [0.65 * inch, 1.85 * inch, 0.75 * inch, 0.85 * inch, 2.8 * inch],
            )
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "13. SWOT Analysis",
        [
            make_table(
                [
                    ["Strengths", "Weaknesses"],
                    ["Working local media pipeline; modular Python/FastAPI architecture; local AI stack; attractive dashboard; clear creator workflow direction.", "Learning data is empty; scoring is heuristic; jobs are not durable; no migrations; dashboard fallbacks can mislead; policy/originality workflow absent."],
                    ["Opportunities", "Threats"],
                    ["Own-content repurposing SaaS; creator/agency tool; retention analytics layer; licensed niche media networks; local-first privacy positioning.", "YouTube reused-content enforcement; copyright claims; low Shorts RPM; generic AI content saturation; local hardware bottlenecks; competitors with better analytics access."],
                ],
                [3.25 * inch, 3.25 * inch],
            )
        ],
        sty,
    )

    section(
        story,
        "14. Things To Stop Building For Now",
        [
            bullet_list(
                [
                    "Stop adding new dashboards until the existing intelligence metrics are grounded in real outcomes.",
                    "Stop optimizing auto-upload until rights/originality review and quality gates exist.",
                    "Stop treating trend keywords as market truth; local metadata counts are not external trend intelligence.",
                    "Stop expanding channel count before throughput, review capacity, and storage limits are enforced.",
                    "Stop investing in revenue forecasting until actual monetized analytics exist.",
                ],
                sty,
            )
        ],
        sty,
    )

    section(
        story,
        "15. Highest ROI Improvements",
        [
            bullet_list(
                [
                    "Persist the successful `final_short.mp4` run into the canonical database objects: Video, Clip, ClipIntelligence, LearningEvent.",
                    "Add a mandatory rights/originality status to every source and clip before upload.",
                    "Capture all candidates, including rejected windows, with transcript, duration, score components, and reason.",
                    "Convert human review into structured labels: bad hook, no payoff, boring, unclear context, weak subtitles, policy concern, duplicate, good clip.",
                    "Add time-windowed analytics snapshots: 1 hour, 6 hours, 24 hours, 72 hours, 7 days.",
                    "Calibrate retention_score against actual performance and show confidence intervals, not only one decimal score.",
                    "Move heavy jobs out of the API request lifecycle into a persisted local worker queue.",
                ],
                sty,
            )
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "16. 30-Day Roadmap",
        [
            make_table(
                [
                    ["Week", "Focus", "Deliverables"],
                    ["1", "Truth and safety", "Rights/originality model; demo-data labels; import final_short into DB; fix SourceFeed metadata_json bug."],
                    ["2", "Learning data", "Store all candidates; structured human labels; non-empty JSONL exports; first 20 owned-content examples."],
                    ["3", "Analytics feedback", "Time-windowed snapshots; upload outcome dashboard; score-vs-result comparison."],
                    ["4", "Quality loop", "Hook A/B workflow; dead-zone/motion/audio energy scoring; quality gate before upload."],
                ],
                [0.65 * inch, 1.45 * inch, 4.55 * inch],
            )
        ],
        sty,
    )

    section(
        story,
        "17. 90-Day Roadmap",
        [
            make_table(
                [
                    ["Month", "Focus", "Deliverables"],
                    ["1", "Reliability", "Durable local queue; job retries; per-stage logs; media cleanup policies; Alembic baseline."],
                    ["2", "Retention validation", "Calibration dataset; candidate negative examples; per-channel priors; confidence intervals."],
                    ["3", "Productization", "Auth, workspaces, creator source permissions, export/share workflows, SaaS packaging decision."],
                ],
                [0.8 * inch, 1.55 * inch, 4.3 * inch],
            )
        ],
        sty,
    )

    section(
        story,
        "18. Long-Term Scaling Architecture",
        [
            FlowDiagram(FUTURE_SCALE, title="Future Scaling Architecture", columns=2, accent=PALETTE["amber"]),
            "Keep the current local-first philosophy. The next architecture step is not Kubernetes; it is a boring reliable worker split: FastAPI as control plane, SQLite/Postgres as state, local worker process for download/transcribe/render, file storage lifecycle, and explicit queue state. Cloud can come later if the business proves demand.",
        ],
        sty,
    )

    story.append(PageBreak())
    section(
        story,
        "19. Final Strategic Verdict",
        [
            p(
                "Is this project realistically capable of becoming a profitable creator system, a SaaS product, an AI media business, or just an overengineered automation toy?",
                sty["H2"],
            ),
            "Honest answer: it can become a profitable creator system or creator-ops SaaS, but it is not yet a defensible autonomous AI media business. If it stays focused on scraping and reposting other creators, it is likely to become an overengineered automation toy with high platform risk. If it shifts toward owned/permissioned content, measurable retention lift, human-in-the-loop review, and rights-safe workflows, it can become valuable.",
            "Most likely near-term win: an internal agency/content repurposing tool that helps produce better clips faster from content you own or have permission to use.",
            "Most valuable SaaS wedge: retention-aware clip selection and review workflow for creators, podcasters, streamers, educators, and agencies. The buyer does not need an autonomous media empire. They need a faster way to find, package, approve, and learn from clips.",
            "Biggest kill risk: policy failure and fake intelligence. A beautiful dashboard that reports unvalidated confidence scores will not survive contact with YouTube or customers.",
            "Biggest opportunity: build the data moat. If the system accumulates real candidate windows, human labels, render settings, hook variants, upload timings, and outcome curves across permissioned content, it becomes much more than an FFmpeg wrapper.",
        ],
        sty,
    )

    section(
        story,
        "20. Sources",
        [
            "YouTube channel monetization policies: https://support.google.com/youtube/answer/1311392",
            "YouTube Shorts monetization policies: https://support.google.com/youtube/answer/12504220",
            "YouTube Partner Program overview and eligibility: https://support.google.com/youtube/answer/72851",
            "YouTube spam/deceptive practices policies: https://support.google.com/youtube/answer/2801973",
            "Fair use on YouTube: https://support.google.com/youtube/answer/9783148",
            "YouTube Data API videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert",
            "YouTube Data API quota calculator: https://developers.google.com/youtube/v3/determine_quota_cost",
        ],
        sty,
    )

    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text(report_markdown(), encoding="utf-8")
    build_pdf()
    print(PDF_PATH)
    print(MD_PATH)


if __name__ == "__main__":
    main()
