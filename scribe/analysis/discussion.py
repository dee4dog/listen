"""Discussion-type templates and content analysis.

Extracts action items, decisions, issues and key points from the transcript with
keyword heuristics, and flags issues that also appeared in earlier sessions
(recurring issues).
"""
import re
from difflib import SequenceMatcher

from ..models import IssueItem

# Which sections each discussion type shows in the summary and exports.
DISCUSSION_TYPES = {
    "meeting": {"label": "Meeting",
                "sections": ["actions", "decisions", "issues", "key_points"]},
    "brief": {"label": "Brief",
              "sections": ["actions", "key_points"]},
    "general": {"label": "General discussion",
                "sections": ["key_points", "issues"]},
    "interview": {"label": "Interview",
                  "sections": ["key_points"]},
}

SECTION_TITLES = {
    "actions": "Action items",
    "decisions": "Decisions",
    "issues": "Key issues",
    "key_points": "Key points",
}

_KIND_FOR_SECTION = {
    "actions": "action",
    "decisions": "decision",
    "issues": "issue",
    "key_points": "key_point",
}

# English + Afrikaans keyword patterns.
_ACTION_RE = re.compile(
    r"\b(i(?:'ll| will)|we(?:'ll| will)|you(?:'ll| will)|going to|need(?:s)? to|"
    r"has to|have to|must|should|action item|follow(?:\s|-)?up|to-?do|"
    r"take care of|get back to|send (?:me|you|them|him|her)|"
    r"by (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|"
    r"next week|next month|end of (?:the )?(?:day|week|month))|"
    r"ek sal|ons sal|jy sal|julle sal|moet|moenie vergeet|aksie(?:punt)?|opvolg|"
    r"sal (?:stuur|doen|maak|reël|re[eë]l)|"
    r"teen (?:maandag|dinsdag|woensdag|donderdag|vrydag|saterdag|sondag|"
    r"m[oô]re|volgende week|volgende maand|einde van die (?:dag|week|maand)))\b",
    re.IGNORECASE)
_DECISION_RE = re.compile(
    r"\b(decided|decision|we agreed?|agreed to|approved|signed? off|"
    r"go ahead with|confirmed|final answer|settled on|"
    r"besluit|ooreengekom|stem saam|saamgestem|goedgekeur|bevestig|afgeteken)\b",
    re.IGNORECASE)
_ISSUE_RE = re.compile(
    r"\b(issue|problem|concern(?:ed)?|risk|blocker|blocked|bug|broken|failing|"
    r"failure|delay(?:ed)?|worried|worry|challenge|complaint|stuck|behind schedule|"
    r"over budget|not working|"
    r"probleem|kwessie|risiko|fout(?:e)?|gebreek|stukkend|werk nie|"
    r"vertraag(?:ing)?|bekommer(?:d|nis)?|uitdaging|klagte|vasgeval|"
    r"agter (?:skedule|op datum)|oor (?:die )?begroting)\b",
    re.IGNORECASE)
_KEY_RE = re.compile(
    r"\b(important|key point|main (?:point|thing|goal)|goal|objective|priority|"
    r"deadline|budget|summary|in short|bottom line|takeaway|critical|"
    r"belangrik(?:ste)?|hoofpunt|hoofsaak|kernpunt|doelwit|prioriteit|"
    r"sperdatum|begroting|opsomming|kortliks|ter afsluiting|krities)\b",
    re.IGNORECASE)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "at", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "we", "i", "you", "they", "he", "she", "have", "has", "had", "do", "does", "did",
    "will", "would", "can", "could", "there", "here", "just", "very", "really",
    "about", "as", "if", "not", "no", "yes", "us", "our", "my", "your", "their",
    # Afrikaans
    "die", "en", "van", "het", "nie", "ek", "ons", "jy", "julle", "hulle", "hy",
    "sy", "dit", "was", "sal", "kan", "kon", "om", "te", "op", "vir", "met", "maar",
    "ook", "na", "by", "se", "wat", "dat", "jou", "wees", "word", "is", "'n",
}


def normalize(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(w for w in words if w not in _STOPWORDS)


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    set_a, set_b = set(a.split()), set(b.split())
    if set_a and set_b:
        jaccard = len(set_a & set_b) / len(set_a | set_b)
        if jaccard >= 0.5:
            return True
    return SequenceMatcher(None, a, b).ratio() >= 0.7


def _sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def analyze(segments, prior_issues=None):
    """Extract IssueItems from the transcript and flag recurring issues.

    `prior_issues` is [(normalized, date, title)] from earlier sessions.
    """
    items = []
    for seg in segments:
        for sent in _sentences(seg.text):
            if len(sent) < 15:
                continue
            if _ACTION_RE.search(sent):
                kind = "action"
            elif _DECISION_RE.search(sent):
                kind = "decision"
            elif _ISSUE_RE.search(sent):
                kind = "issue"
            elif _KEY_RE.search(sent):
                kind = "key_point"
            else:
                continue
            items.append(IssueItem(kind=kind, text=sent, speaker=seg.speaker,
                                   normalized=normalize(sent)))

    # Drop near-duplicate items within this session.
    unique = []
    for item in items:
        if not any(item.kind == u.kind and _similar(item.normalized, u.normalized)
                   for u in unique):
            unique.append(item)

    # Flag issues already raised in earlier sessions.
    for item in unique:
        if item.kind != "issue":
            continue
        for norm, date, _title in (prior_issues or []):
            if _similar(item.normalized, norm):
                item.recurring = True
                item.prior_date = (date or "")[:10]
                break
    return unique


def items_for_section(issues, section):
    kind = _KIND_FOR_SECTION[section]
    return [it for it in issues if it.kind == kind]
