"""PDF export via reportlab."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..analysis.discussion import DISCUSSION_TYPES, SECTION_TITLES, items_for_section
from ..models import fmt_ts


def _escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def export_pdf(session, path):
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    heading = styles["Heading2"]
    recurring_style = ParagraphStyle(
        "Recurring", parent=body, textColor=colors.HexColor("#b30000"))
    speaker_style = ParagraphStyle(
        "SpeakerLine", parent=body, spaceBefore=4)

    dtype = DISCUSSION_TYPES.get(session.dtype, DISCUSSION_TYPES["general"])
    story = [
        Paragraph(_escape(session.title), styles["Title"]),
        Paragraph(
            f"{dtype['label']} &nbsp;|&nbsp; {session.started_at.replace('T', ' ')} "
            f"&nbsp;|&nbsp; Duration: {fmt_ts(session.duration)} "
            f"&nbsp;|&nbsp; Participants: {_escape(', '.join(session.speaker_names()) or '—')}",
            body),
        Spacer(1, 6 * mm),
    ]

    for section in (session.sections_override or dtype["sections"]):
        items = items_for_section(session.issues, section)
        if not items:
            continue
        story.append(Paragraph(SECTION_TITLES[section], heading))
        for item in items:
            prefix = f"<b>{_escape(item.speaker)}:</b> " if item.speaker else ""
            if item.recurring:
                flag = f" <b>[RECURRING — first raised {item.prior_date or 'earlier'}]</b>"
                story.append(Paragraph(f"• {prefix}{_escape(item.text)}{flag}",
                                       recurring_style))
            else:
                story.append(Paragraph(f"• {prefix}{_escape(item.text)}", body))
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Transcript", heading))
    for seg in session.segments:
        story.append(Paragraph(
            f"<font color='#666666'>[{fmt_ts(seg.start)}]</font> "
            f"<b>{_escape(seg.speaker)}:</b> {_escape(seg.text)}",
            speaker_style))

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            title=session.title, author="Listen")
    doc.build(story)
    return path
