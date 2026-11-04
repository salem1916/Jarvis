"""Recognize explicit browser searches without asking a model to invent tools."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from jarvis.core.tool_request import ToolRequest

SEARCH_ENGINES = {
    "google": ("https://www.google.com/search", "q"),
    "bing": ("https://www.bing.com/search", "q"),
    "duckduckgo": ("https://duckduckgo.com/", "q"),
    "youtube": ("https://www.youtube.com/results", "search_query"),
}


def search_reference(text: str) -> bool:
    """A reference is not a literal search query; resolve it before navigation."""
    value = text.strip()
    if len(value) > 2 and ((value[0] == value[-1] and value[0] in {'"', "'"}) or (value[0], value[-1]) == ("“", "”")):
        return False  # A fully quoted title/query is explicitly literal.
    return bool(re.search(
        r"\b(?:that|which) (?:i|we|you) (?:\w+ ){0,3}(?:asked|requested|mentioned|discussed|wanted|said)\b"
        r"|\b(?:i|we) (?:asked|requested|mentioned|discussed|talked)\b"
        r"|\b(?:from before|earlier|previous(?:ly)?|same (?:topic|thing|subject)|about (?:it|that|this)|on (?:it|that|this))\b",
        text, re.IGNORECASE)) or text.casefold().strip(" .!?") in {"it", "that", "this", "them", "those", "again"}


def search_phrase(prompt: str) -> tuple[str | None, str] | None:
    text = " ".join(prompt.strip().split())
    text = re.sub(r"^(?:please |(?:can|could|would) you (?:please )?)", "", text, flags=re.IGNORECASE)
    match = re.fullmatch(r"(?:search|look up|google)(?: (google|bing|duckduckgo|youtube))?(?: for)? (.+)", text, re.IGNORECASE)
    if not match:
        match = re.fullmatch(r"open (google|bing|duckduckgo|youtube) and search(?: for)? (.+)", text, re.IGNORECASE)
    return (match[1], match[2].strip()) if match else None


def video_topic(query: str) -> str | None:
    match = re.fullmatch(r"(?:(?:a|the|some|another|that|this) )?(?:videos?|vids?|vds?|clips?|tutorials?)(?: (?:about|on|of|for))?(?: (.*))?", query, re.IGNORECASE)
    if not match:
        return None
    # Unqualified 'video encoding' is a subject, not a request for a video.
    if not re.match(r"(?:a |the |some |another |that |this |videos? (?:about|on|of|for) |vids?\b|vds?\b|tutorials? (?:about|on|of|for) )", query, re.IGNORECASE) and match[1]:
        return None
    return (match[1] or "").strip()


def browser_search(prompt: str, last_url: str = "") -> ToolRequest | None:
    parsed = search_phrase(prompt)
    if parsed is None:
        return None
    engine, query = parsed
    if search_reference(query):
        return None
    topic = video_topic(query)
    if topic is not None:
        if not topic or search_reference(topic):
            return None
        if engine is None:
            engine, query = "youtube", topic
    # Research/synthesis and filesystem searches belong to the agent, not URL navigation.
    if re.search(r"\b(?:and|then) (?:please )?(?:summari[sz]e|explain|compare|read|click|download|buy|tell|find|open|search|write|research)\b", query, re.IGNORECASE):
        return None
    if re.search(r"\b(?:in|inside|within) (?:my |the )?(?:files|folder|directory|workspace|repository|repo)\b", query, re.IGNORECASE):
        return None
    suffix = re.search(r" (?:on|in|using) (?:the )?(google|bing|duckduckgo|youtube)(?: (?:you (?:just )?opened|that you opened|tab|browser))?[.!]?$", query, re.IGNORECASE)
    if suffix:
        engine, query = suffix[1], query[:suffix.start()].strip()
    contextual = re.search(r" (?:in|on) (?:the |that )?(?:browser|tab|page|website)(?: (?:you (?:just )?opened|that you opened))?[.!]?$", query, re.IGNORECASE)
    if contextual:
        hostname = urlsplit(last_url).hostname or ""
        matched = next((e for e in SEARCH_ENGINES if hostname == e + ".com" or hostname == "www." + e + ".com"), None)
        if not matched:
            return None
        engine, query = matched, query[:contextual.start()].strip()
    if not query or query.casefold().strip(".!?") in {"it", "that", "this", "them"}:
        return None
    endpoint, parameter = SEARCH_ENGINES[(engine or "google").casefold()]
    return ToolRequest(tool_name="open_url", arguments={"url": endpoint + "?" + urlencode({parameter: query})})


def search_description(url: str) -> str | None:
    parsed = urlsplit(url)
    for engine, (endpoint, parameter) in SEARCH_ENGINES.items():
        expected = urlsplit(endpoint)
        if parsed.netloc == expected.netloc and parsed.path == expected.path:
            query = parse_qs(parsed.query).get(parameter, [""])[0]
            if query:
                return f"Opened {engine.title()} search for: {query}"
    return None
