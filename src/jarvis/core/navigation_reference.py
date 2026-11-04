"""Recognize page-relative navigation without turning references into app names."""
import re


def page_navigation(text: str) -> dict | None:
    value = re.sub(r"^(?:(?:no|wait|actually|please|okay|ok)[,! ]+)+", "", text.strip(), flags=re.IGNORECASE)
    value = re.sub(r"^(?:can|could|would) you (?:please )?", "", value, flags=re.IGNORECASE).casefold().strip(" .!?")
    if re.fullmatch(r"(?:go |take me )?back(?: (?:a|one) page)?", value):
        return {"action":"back"}
    match = re.fullmatch(r"(?:open|click|follow) (?:the )?(first|second|third|fourth|fifth|[1-5]) (link|result|one)", value)
    if match:
        ordinal = int(match[1]) if match[1].isdigit() else ["first","second","third","fourth","fifth"].index(match[1])+1
        return {"action":"follow_link", "link_index":ordinal, "link_kind":"result" if match[2] == "result" else "link"}
    return None


def navigation_reference(text: str) -> bool:
    return page_navigation(text) is not None
