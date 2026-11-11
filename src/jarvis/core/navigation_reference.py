"""Recognize page-relative navigation without turning references into app names."""
import re


def page_navigation(text: str, *, allow_video: bool = False) -> dict | None:
    value = re.sub(r"^(?:(?:no|wait|actually|please|okay|ok)[\s,.:!?-]+)+", "", text.strip(), flags=re.IGNORECASE)
    value = re.sub(r"^(?:can|could|would) you (?:please )?", "", value, flags=re.IGNORECASE).casefold().strip(" .!?")
    if re.fullmatch(r"(?:go |take me )?back(?: (?:a|one) page)?", value):
        return {"action":"back"}
    if allow_video:
        correction = re.fullmatch(r"(?:go |take me )?back(?: (?:a|one) page)?[, ]+(?:and then|and|then) (.+)", value)
        if correction:
            target = correction[1]
            if re.match(r"(?:the )?(?:first|second|third|fourth|fifth|[1-5])\b", target):
                target = "open " + target
            if re.match(r"(?:open|play|click|follow)\b", target):
                follow = page_navigation(target, allow_video=True)
                if follow is not None and follow["action"] == "follow_link":
                    return {**follow, "action": "back_and_follow"}
    match = re.fullmatch(r"(?:open|click|follow) (?:the )?(first|second|third|fourth|fifth|[1-5]) (link|result|one)", value)
    if match:
        ordinal = int(match[1]) if match[1].isdigit() else ["first","second","third","fourth","fifth"].index(match[1])+1
        kind = "reference" if match[2] == "one" and allow_video else ("result" if match[2] == "result" else "link")
        return {"action":"follow_link", "link_index":ordinal, "link_kind":kind}
    if allow_video:
        video = re.fullmatch(
            r"(?:(?:open|play|click|follow) )?(?:the )?(first|second|third|fourth|fifth|[1-5]) "
            r"(?:video|vid|vd|clip)(?: (?:on|in) (youtube|vimeo|it|(?:this|the current|the) (?:page|tab)))?",
            value,
        )
        if video:
            ordinal = int(video[1]) if video[1].isdigit() else ("first", "second", "third", "fourth", "fifth").index(video[1]) + 1
            navigation = {"action": "follow_link", "link_index": ordinal, "link_kind": "video"}
            if video[2] in {"youtube", "vimeo"}:
                navigation["site"] = video[2] + ".com"
            return navigation
    return None


def navigation_reference(text: str) -> bool:
    return page_navigation(text) is not None


def chrome_tabs_requested(text: str) -> bool:
    text = " ".join(text.casefold().strip(" .!?").split())
    text = re.sub(r"^(?:please |(?:can|could|would) you (?:please )?)", "", text)
    return bool(re.fullmatch(
        r"(?:(?:what|which) (?:(?:chrome|browser) )?tabs (?:do i have open|are open|are currently open|are there)"
        r"|(?:list|show|tell me) (?:me |my |the |all )*(?:open |current )?(?:(?:chrome|browser) )?tabs)"
        r"(?: (?:in|on) (?:my |google )?chrome)?(?: right now)?", text,
    ))
