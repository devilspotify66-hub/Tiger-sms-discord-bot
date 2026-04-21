"""Popular service/country code lookups for tiger-sms.

Full list of supported service/country codes is documented at
https://tiger-sms.com/api — the bot accepts any code from there.
"""

# Most popular services (lowercase code -> display name)
POPULAR_SERVICES: dict[str, str] = {
    "tg": "Telegram",
    "wa": "WhatsApp",
    "go": "Google / YouTube / Gmail",
    "ds": "Discord",
    "fb": "Facebook",
    "ig": "Instagram",
    "tw": "Twitter / X",
    "tl": "Truecaller",
    "mt": "Steam",
    "am": "Amazon",
    "dh": "eBay",
    "ub": "Uber",
    "oi": "Tinder",
    "qv": "Badoo",
    "wb": "WeChat",
    "mj": "Zalo",
    "lf": "TikTok / Douyin",
    "re": "Coinbase",
    "ot": "Any other",
    "vi": "Viber",
    "ya": "Yandex",
    "bz": "Blizzard",
    "mb": "Yahoo",
    "av": "Avito",
    "hb": "Twitch",
    "dr": "ChatGPT",
}

# Popular countries (numeric id -> display name)
POPULAR_COUNTRIES: dict[str, str] = {
    "0": "Russia",
    "1": "Ukraine",
    "2": "Kazakhstan",
    "4": "Philippines",
    "6": "Indonesia",
    "7": "Malaysia",
    "10": "Vietnam",
    "12": "USA (virtual)",
    "16": "United Kingdom",
    "22": "India",
    "33": "Colombia",
    "36": "Canada",
    "37": "Morocco",
    "43": "Germany",
    "44": "Lithuania",
    "52": "Thailand",
    "54": "Mexico",
    "55": "Taiwan",
    "56": "Spain",
    "62": "Turkey",
    "73": "Brazil",
    "78": "France",
    "86": "Italy",
    "117": "Portugal",
    "151": "Chile",
    "163": "Finland",
    "172": "Denmark",
    "173": "Switzerland",
    "174": "Norway",
    "175": "Australia",
    "182": "Japan",
    "187": "United States",
    "190": "Korea",
    "196": "Singapore",
}


def service_name(code: str) -> str:
    return POPULAR_SERVICES.get(code.lower(), code)


def country_name(cid: str) -> str:
    return POPULAR_COUNTRIES.get(str(cid), f"Country {cid}")
