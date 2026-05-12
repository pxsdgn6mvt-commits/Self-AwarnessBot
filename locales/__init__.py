from locales.ru import RU
from locales.en import EN

LOCALES = {"ru": RU, "en": EN}


def t(lang: str, key: str, **kwargs) -> str:
    strings = LOCALES.get(lang, EN)
    text = strings.get(key, EN.get(key, key))
    return text.format(**kwargs) if kwargs else text
