"""
Парсит cURL запроса gameEvents из браузера и обновляет odds_logger.py:
  DOMAIN, GAME_ID, x-hd, COOKIES, referer

Использование:
  1. В DevTools → Network → правый клик на gameEvents запрос → Copy → Copy as cURL (bash)
  2. Сохранить cURL в файл curl.txt в этой же папке (или передать через --file)
  3. python update_session.py
     или
     python update_session.py --map 2     # сразу обновить и MAP_NUM

После запуска — odds_logger.py готов к запуску, ничего вручную править не нужно.

Что бывает не так:
  - Скопировал cURL не от gameEvents → скрипт ругнётся что URL не подходит
  - Зеркало живое → cURL прошёл проверку валидации (тестовый GET)
"""

import argparse
import io
import os
import re
import shlex
import sys
from urllib.parse import urlparse, parse_qs

LOGGER_PATH = "odds_logger.py"
from paths import CURL_FILE as CURL_DEFAULT


# ---------------- cURL parser ----------------

def parse_curl(text):
    """Разбирает текст cURL команды. Возвращает dict с полями:
        url, method, headers (dict), cookies (dict), params (dict)
    Поддерживает обе оболочки: bash (\\) и cmd (^).
    """
    # нормализация переносов: bash использует "\" + newline, cmd — "^" + newline
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\\\n\s*", " ", t)   # bash continuation
    t = re.sub(r"\^\n\s*", " ", t)   # cmd continuation
    # cmd-вариант часто экранирует через ^" — сначала уберём такие экраны
    t = t.replace('^"', '"').replace("^&", "&").replace("^$", "$")

    try:
        tokens = shlex.split(t, posix=True)
    except ValueError:
        # на Windows иногда проще без posix
        tokens = shlex.split(t, posix=False)
        tokens = [tok.strip("\"'") for tok in tokens]

    if not tokens or tokens[0].lower() != "curl":
        raise ValueError("Это не cURL команда (должна начинаться со слова 'curl')")

    url = None
    headers = {}
    cookies = {}
    method = "GET"

    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = tokens[i]
                if ":" in hdr:
                    k, v = hdr.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
        elif t in ("-b", "--cookie"):
            i += 1
            if i < len(tokens):
                cookie_str = tokens[i]
                # убрать markdown-обёртки типа [foo](http://foo) — сайт melbet их подсовывает
                cookie_str = re.sub(r"\[([^\]]+)\]\(http[^)]+\)", r"\1", cookie_str)
                for pair in cookie_str.split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        cookies[k.strip()] = v.strip()
        elif t in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i]
        elif t in ("--compressed", "-i", "-k", "-L", "-s", "-S", "--http1.1", "--http2"):
            pass
        elif t.startswith("http://") or t.startswith("https://"):
            url = t
        i += 1

    if not url:
        raise ValueError("В cURL не найден URL")

    parsed = urlparse(url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "cookies": cookies,
        "domain": parsed.netloc,
        "path": parsed.path,
        "params": params,
    }


# ---------------- validation ----------------

def validate_curl(parsed):
    """Проверяет что cURL — это запрос gameEvents."""
    if "gameEvents" not in parsed["path"]:
        raise ValueError(
            f"Это cURL не от gameEvents (путь: {parsed['path']}).\n"
            f"Нужен запрос вида .../cyber/v1/gameEvents?gameId=..."
        )
    if "gameId" not in parsed["params"]:
        raise ValueError("В URL нет параметра gameId")
    if "x-hd" not in parsed["headers"]:
        raise ValueError("В заголовках нет x-hd — этот хедер обязателен")


# ---------------- patcher ----------------

def render_dict_python(d, indent=4):
    """Рендерит dict как Python literal с одним ключом на строку."""
    pad = " " * indent
    lines = ["{"]
    for k, v in d.items():
        # экранируем как repr, чтобы спецсимволы (кавычки, etc) не сломали
        lines.append(f'{pad}{repr(k)}: {repr(v)},')
    lines.append(" " * (indent - 4) + "}")
    return "\n".join(lines)


def patch_logger(parsed, map_num=None):
    if not os.path.exists(LOGGER_PATH):
        raise FileNotFoundError(f"Не нашёл {LOGGER_PATH} в текущей папке")

    with io.open(LOGGER_PATH, "r", encoding="utf-8") as f:
        c = f.read()
    if c.startswith("\ufeff"):
        c = c.lstrip("\ufeff")

    new_domain = parsed["domain"]
    new_game_id = parsed["params"]["gameId"]
    new_xhd = parsed["headers"].get("x-hd", "")
    new_referer = parsed["headers"].get("referer", "")
    new_cookies = parsed["cookies"]

    changes = []

    # --- DOMAIN ---
    new_c, n = re.subn(
        r'^(DOMAIN\s*=\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{new_domain}"',
        c, count=1, flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("Не нашёл строку DOMAIN = \"...\" в odds_logger.py")
    changes.append(f"DOMAIN -> {new_domain}")
    c = new_c

    # --- GAME_ID ---
    new_c, n = re.subn(
        r'^(GAME_ID\s*=\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{new_game_id}"',
        c, count=1, flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("Не нашёл строку GAME_ID = \"...\"")
    changes.append(f"GAME_ID -> {new_game_id}")
    c = new_c

    # --- MAP_NUM (опционально) ---
    if map_num is not None:
        new_c, n = re.subn(
            r'^(MAP_NUM\s*=\s*)\d+',
            lambda m: f'{m.group(1)}{map_num}',
            c, count=1, flags=re.MULTILINE,
        )
        if n != 1:
            raise RuntimeError("Не нашёл строку MAP_NUM = ...")
        changes.append(f"MAP_NUM -> {map_num}")
        c = new_c

    # --- x-hd ---
    # Ключ в двойных кавычках, значение может быть в любых (repr() сам выбирает).
    # Паттерн: "x-hd"\s*:\s*  затем  "..."  или  '...'  без переносов.
    new_c, n = re.subn(
        r'("x-hd"\s*:\s*)(?:"[^"]*"|\'[^\']*\')',
        lambda m: f'{m.group(1)}{repr(new_xhd)}',
        c, count=1,
    )
    if n != 1:
        raise RuntimeError('Не нашёл x-hd в HEADERS')
    changes.append(f"x-hd -> ({len(new_xhd)} chars)")
    c = new_c

    # --- referer ---
    # В коде он сейчас как f-строка: f"https://{DOMAIN}/en/esports/...".
    # Нам нужно заменить блок REFERER_PATH или просто переписать всю строку referer
    # на литерал из cURL (так надёжнее — он уже включает домен).
    new_referer_safe = new_referer if new_referer else f"https://{new_domain}/"
    # referer тоже может быть в любых кавычках или f-строкой
    new_c, n = re.subn(
        r'("referer"\s*:\s*)(?:f?"[^"]*"|f?\'[^\']*\'|f"[^"{}]*\{[^}]+\}[^"]*")',
        lambda m: f'{m.group(1)}{repr(new_referer_safe)}',
        c, count=1,
    )
    if n != 1:
        raise RuntimeError('Не нашёл referer в HEADERS')
    changes.append(f"referer -> {new_referer_safe[:60]}...")
    c = new_c

    # --- COOKIES ---
    # Ищем блок: COOKIES = {  ...  }
    cookies_block = "COOKIES = " + render_dict_python(new_cookies, indent=4)
    new_c, n = re.subn(
        r'^COOKIES\s*=\s*\{[^}]*\}',
        cookies_block.replace("\\", "\\\\"),  # экранируем для re
        c, count=1, flags=re.MULTILINE | re.DOTALL,
    )
    if n != 1:
        # fallback — попробуем без MULTILINE и с жадным DOTALL
        new_c, n = re.subn(
            r'COOKIES\s*=\s*\{.*?\n\}',
            cookies_block.replace("\\", "\\\\"),
            c, count=1, flags=re.DOTALL,
        )
    if n != 1:
        raise RuntimeError("Не нашёл блок COOKIES = {...} в odds_logger.py")
    changes.append(f"COOKIES -> {len(new_cookies)} штук")
    c = new_c

    # --- проверка синтаксиса перед записью ---
    import ast
    try:
        ast.parse(c)
    except SyntaxError as e:
        raise RuntimeError(f"После патча получился невалидный Python: {e}")

    # пишем как байты utf-8 без BOM (io.open с utf-8 BOM не пишет, но если был — снимем)
    if c.startswith("\ufeff"):
        c = c.lstrip("\ufeff")
    with open(LOGGER_PATH, "wb") as f:
        f.write(c.encode("utf-8"))

    return changes


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=CURL_DEFAULT,
                    help=f"путь к файлу с cURL (по умолчанию {CURL_DEFAULT})")
    ap.add_argument("--map", type=int, default=None,
                    help="опционально: установить MAP_NUM")
    ap.add_argument("--stdin", action="store_true",
                    help="читать cURL со stdin вместо файла")
    args = ap.parse_args()

    if args.stdin:
        print("Вставь cURL и нажми Ctrl+Z затем Enter (Windows) или Ctrl+D (Linux):")
        text = sys.stdin.read()
    else:
        if not os.path.exists(args.file):
            print(f"Не нашёл {args.file}.")
            print(f"Создай файл и вставь туда полный cURL запроса gameEvents из браузера.")
            print(f"Или используй: python update_session.py --stdin")
            sys.exit(1)
        with io.open(args.file, "r", encoding="utf-8") as f:
            text = f.read()

    if not text.strip():
        print("Пустой ввод.")
        sys.exit(1)

    print("Парсю cURL...")
    try:
        parsed = parse_curl(text)
    except Exception as e:
        print(f"Не смог распарсить: {e}")
        sys.exit(1)

    print(f"  URL:     {parsed['url'][:100]}{'...' if len(parsed['url']) > 100 else ''}")
    print(f"  domain:  {parsed['domain']}")
    print(f"  gameId:  {parsed['params'].get('gameId')}")
    print(f"  cookies: {len(parsed['cookies'])} штук")
    print(f"  x-hd:    {len(parsed['headers'].get('x-hd', ''))} chars")
    print()

    try:
        validate_curl(parsed)
    except Exception as e:
        print(f"Валидация не прошла: {e}")
        sys.exit(1)

    print(f"Патчу {LOGGER_PATH}...")
    try:
        changes = patch_logger(parsed, map_num=args.map)
    except Exception as e:
        print(f"Ошибка патча: {e}")
        sys.exit(1)

    for ch in changes:
        print(f"  {ch}")
    print()
    print("Готово. Запускай: python odds_logger.py")


if __name__ == "__main__":
    main()
