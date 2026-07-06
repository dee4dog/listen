"""Deduce speaker names from self-introductions in their own speech."""
import re

_INTRO_RE = re.compile(
    r"\b(?:my name is|my name's|this is|i am|i'm"
    r"|my naam is|ek is|ek heet|dis ek,?)\s+([A-Za-z][a-zA-Z'’-]{1,20})\b",
    re.IGNORECASE,
)

# Words that commonly follow the intro phrases but are not names.
_NOT_NAMES = {
    "not", "so", "sure", "here", "just", "going", "gonna", "sorry", "the", "a", "an",
    "really", "very", "calling", "from", "in", "on", "at", "glad", "happy", "good",
    "fine", "okay", "ok", "done", "back", "still", "now", "trying", "afraid", "aware",
    "thinking", "wondering", "confident", "also", "all", "always", "actually", "about",
    "excited", "pleased", "ready", "right", "wrong", "late", "new", "old", "one",
    # Afrikaans words that can follow "ek is" but are not names
    "bly", "jammer", "seker", "gereed", "hier", "nou", "baie", "moeg", "laat",
    "reg", "klaar", "besig", "bang", "honger", "dankbaar", "opgewonde", "die",
    "van", "nie", "so", "ook", "amper", "terug", "weg", "haastig", "gelukkig",
}


def deduce_names(segments):
    """Return {generic_label: deduced_name} for labels still named 'Speaker N'."""
    deduced, taken = {}, set()
    for seg in segments:
        label = seg.speaker
        if not label.startswith("Speaker ") or label in deduced:
            continue
        for match in _INTRO_RE.finditer(seg.text):
            name = match.group(1).strip("'’-")
            if name.lower() in _NOT_NAMES or not name[0].isupper():
                continue
            name = name.capitalize() if name.isupper() else name
            if name in taken:
                continue
            deduced[label] = name
            taken.add(name)
            break
    return deduced
