"""Search goals are separate from page focus and assistant wording."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

from jarvis.core.browser_commands import (
    SEARCH_ENGINES,
    browser_search,
    search_phrase,
    search_reference,
    video_topic,
)
from jarvis.core.tool_request import ToolRequest


@dataclass(frozen=True)
class SearchIntent:
    query: str
    engine: str = "google"
    answer_request: str = ""

    def request(self) -> ToolRequest:
        endpoint, parameter = SEARCH_ENGINES[self.engine]
        return ToolRequest(tool_name="open_url", arguments={"url": endpoint + "?" + urlencode({parameter: self.query})})


@dataclass(frozen=True)
class SearchCandidate:
    query: str
    engine: str
    contextual: bool = False
    combined: bool = False
    semantic: bool = False


@dataclass
class SearchMemory:
    intent: SearchIntent | None = None
    reusable: bool = False
    pending_engine: str = ""
    pending_request: str = ""
    unresolved_prompt: str = ""
    unresolved_override: str | None = None


def search_candidate(prompt: str) -> SearchCandidate | None:
    text = re.sub(r"^(?:please |(?:can|could|would) you (?:please )?)", "", prompt.strip(), flags=re.IGNORECASE)
    phrase = search_phrase(text)
    if phrase:
        engine, query = phrase
        # Existing multi-step and filesystem routing owns these requests.
        if re.search(r"\b(?:in|inside|within) (?:my |the )?(?:files|folder|directory|workspace|repository|repo)\b", query, re.IGNORECASE):
            return None
        if re.search(r"\b(?:and|then) (?:please )?(?:summari[sz]e|explain|compare|read|click|download|buy|tell|find|open|search|write|research)\b", query, re.IGNORECASE):
            return None
        topic = video_topic(query)
        if topic is not None:
            indirect = not topic or search_reference(topic) or bool(re.match(r"(?:in|with|under|over|from|shorter|longer)\b", topic, re.IGNORECASE))
            return SearchCandidate(topic, (engine or "youtube").casefold(), indirect)
        return SearchCandidate(query, (engine or "google").casefold(), search_reference(query))
    media = re.match(r"(?:show|find|look for|give)(?: me)? (.+)$", text, re.IGNORECASE)
    if media:
        topic = video_topic(media[1])
        if topic is not None:
            indirect = not topic or search_reference(topic) or bool(re.match(r"(?:in|with|under|over|from|shorter|longer)\b", topic, re.IGNORECASE))
            return SearchCandidate(topic, "youtube", indirect)
    media_action = re.search(r"\b(?:show|find|search|look for)\b.*\b(?:videos?|vids?|vds?|clips?|tutorials?)\b", text, re.IGNORECASE)
    if media_action:
        prefix = text[:media_action.start()].strip(" ,")
        prefix = re.sub(r"^(?:(?:now|maybe|also|and|please|then)\s*)+", "", prefix, flags=re.IGNORECASE).strip()
        combined = bool(prefix)
        contextual = search_reference(text) or bool(re.search(r"\b(?:shorter|longer|another|similar|same)\b", text, re.IGNORECASE))
        return SearchCandidate(text, "youtube", contextual=contextual, combined=combined, semantic=True)
    return None


def pending_topic(text: str) -> bool:
    return (bool(text.strip()) and len(text) <= 500 and not text.rstrip().endswith("?")
            and not re.match(r"(?:what|why|how|who|where|when|explain|open|launch|read|research|remember|forget|stop|cancel|don't|do not)\b", text, re.IGNORECASE)
            and text.casefold().strip(" .!") not in {"yes", "no", "okay", "ok", "sure", "first", "second", "third"})


def reusable_reference(query: str) -> bool:
    return not query or bool(re.fullmatch(
        r"(?:(?:about|on) )?(?:it|that|this|them|the same topic|the same thing)"
        r"|(?:that|which) (?:i|we|you) (?:(?:already|just) )?(?:asked(?: you)? for|requested|mentioned|discussed)(?: before| earlier)?",
        query.strip(" .!?"), re.IGNORECASE))


def literal_search_intent(prompt: str, last_url: str = "") -> SearchIntent | None:
    request = browser_search(prompt, last_url)
    if request is None:
        return None
    url = urlsplit(str(request.arguments["url"]))
    for engine, (endpoint, parameter) in SEARCH_ENGINES.items():
        expected = urlsplit(endpoint)
        if url.netloc == expected.netloc and url.path == expected.path:
            return SearchIntent(parse_qs(url.query)[parameter][0], engine)
    return None
