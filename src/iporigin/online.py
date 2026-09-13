"""Optional live lookup, for what the bundled dataset cannot know.

The offline dataset covers published hosting and CDN ranges. It does not
cover consumer VPN exit nodes, because no provider publishes those. When
that matters, this asks the free Unblock Master API, which does its own
detection:

    from iporigin.online import classify_online
    classify_online("203.0.113.10")

Nothing else in iporigin makes a network request; you have to call this
module explicitly. It needs no API key.
"""

import json
import urllib.error
import urllib.request

from .core import HOSTING, UNKNOWN, VPN, Origin, _parse, classify

API_URL = "https://www.unblockmaster.com/api/v1/ip/%s"
USER_AGENT = "iporigin/1.0 (+https://github.com/Yuix-Networks/iporigin)"
DEFAULT_TIMEOUT = 5


class LookupError_(RuntimeError):
    """The online lookup could not be completed."""


def classify_online(ip, timeout=DEFAULT_TIMEOUT, fall_back=True):
    """Classify an address using the live API.

    ``fall_back`` returns the offline answer when the request fails, which
    is usually what you want in a request path. Pass False to get an
    exception instead, when a wrong answer is worse than no answer.
    """
    address = _parse(ip)
    offline = classify(address)
    if offline.kind == "reserved":
        return offline

    request = urllib.request.Request(
        API_URL % address, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        if fall_back:
            return offline
        raise LookupError_("live lookup failed for %s: %s" % (address, exc)) from exc

    # The API answers null when it could not determine the address, which is
    # not the same as False. Only overrule the offline answer on a real yes.
    if payload.get("is_vpn") is True:
        # A provider name we already matched locally is more specific than
        # anything the API returns, so keep it.
        provider = offline.provider or payload.get("provider") or ""
        kind = offline.kind if offline.kind in (HOSTING, "cdn") else VPN
        return Origin(str(address), kind, provider, source="api")

    if payload.get("is_vpn") is False and offline.kind == UNKNOWN:
        return Origin(str(address), UNKNOWN, payload.get("provider") or "", source="api")

    return offline
