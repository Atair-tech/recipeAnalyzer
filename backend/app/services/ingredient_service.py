import re
from typing import Dict, List, Optional, Tuple


INGREDIENT_ALIAS_MAP = {
    "西红柿": "番茄",
    "小番茄": "番茄",
    "圣女果": "番茄",
    "马铃薯": "土豆",
    "洋芋": "土豆",
    "鸡蛋液": "鸡蛋",
    "蛋液": "鸡蛋",
    "可生食鸡蛋": "鸡蛋",
    "小葱": "葱",
    "香葱": "葱",
    "大葱": "葱",
    "青葱": "葱",
    "葱花": "葱",
    "葱段": "葱",
    "蒜末": "蒜",
    "蒜蓉": "蒜",
    "蒜瓣": "蒜",
    "姜末": "姜",
    "姜丝": "姜",
    "姜片": "姜",
    "包浆豆腐": "豆腐",
    "中豆腐": "豆腐",
    "嫩豆腐": "豆腐",
    "老豆腐": "豆腐",
    "北豆腐": "豆腐",
    "南豆腐": "豆腐",
    "内脂豆腐": "豆腐",
    "kiri奶油奶酪": "奶油奶酪",
    "tandoori料": "tandoori",
    "peri-peri酱": "peri-peri",
}

KNOWN_UNITS = [
    "大勺",
    "小勺",
    "汤匙",
    "茶匙",
    "毫升",
    "公升",
    "千克",
    "公斤",
    "ml",
    "mL",
    "kg",
    "g",
    "l",
    "L",
    "克",
    "斤",
    "两",
    "个",
    "只",
    "颗",
    "粒",
    "根",
    "段",
    "片",
    "块",
    "条",
    "把",
    "张",
    "枚",
    "瓣",
    "包",
    "袋",
    "盒",
    "碗",
    "杯",
]

QUALITATIVE_AMOUNTS = ["适量", "少许", "少量", "若干", "按需"]

PREPARATION_WORDS = [
    "切碎",
    "切丝",
    "切片",
    "切丁",
    "切段",
    "拍碎",
    "剁碎",
    "压泥",
    "去皮",
    "洗净",
    "焯水",
    "沥干",
    "泡发",
]

DROP_PREFIXES = [
    "推荐",
    "建议",
    "如果",
    "或者",
    "而且",
    "然后",
    "起锅",
    "可选",
    "其他配菜",
    "其他搭配",
    "不减脂",
    "减脂",
    "原版",
    "升级版",
    "一人份",
    "人多",
    "人少",
    "如做",
    "如果做",
    "如有",
    "如贝壳类",
    "因为",
    "但是",
    "不过",
    "之后",
    "同时",
    "下面",
    "上脑等",
    "买现成",
    "原配方",
    "喜欢的",
    "喜欢吃辣",
]

DROP_HINTS = [
    "推荐",
    "建议",
    "做法",
    "词条",
    "版本",
    "搭配",
    "可选",
    "起锅",
    "不计热量",
    "更好的做法",
    "适合",
    "增香",
    "提味",
    "比例为",
    "也可放",
    "可放",
    "可以放",
    "其他配菜",
    "其他搭配",
    "蛋白质",
    "可参考",
    "可根据",
    "可使用",
    "都可以",
    "什么都不放",
    "最后",
    "里面可以",
    "加入",
    "topping",
    "一人份",
    "人多可以",
    "可以加",
    "可加",
    "可以用",
    "可用",
    "也可以",
    "需要",
    "还需要",
    "如果",
    "的话",
    "另准备",
    "垫底",
    "摆盘",
    "另记",
    "另最好",
    "基础上",
    "之后",
    "汤汁",
    "差不多",
    "比例是",
    "减少",
    "增加",
    "降低热量",
    "至少",
    "就不放",
    "更好吃",
    "必须",
    "实际",
    "象征性",
    "相应记录",
    "参考",
    "词条",
    "版台",
    "热量",
]

REMARK_PREFIXES = ["推荐", "可用", "也可", "也可以", "最好", "建议"]

SPLIT_PATTERN = re.compile(r"[\n,，;；、]+")
PAREN_PATTERN = re.compile(r"[（(](.*?)[）)]")
BOOK_TITLE_PATTERN = re.compile(r"[【】]")
ARABIC_NUMBER_PATTERN = r"\d+(?:\.\d+)?(?:/\d+)?(?:-\d+(?:\.\d+)?)?"
CHINESE_NUMBER_PATTERN = r"[一二三四五六七八九十两半几]+"
AMOUNT_TOKEN_PATTERN = rf"(?:{ARABIC_NUMBER_PATTERN}|{CHINESE_NUMBER_PATTERN}|适量|少许|少量|若干|按需)"
UNIT_PATTERN = "|".join(sorted((re.escape(unit) for unit in KNOWN_UNITS), key=len, reverse=True))
PREFIX_PATTERN = re.compile(rf"^(?P<amount>{AMOUNT_TOKEN_PATTERN})(?P<unit>{UNIT_PATTERN})?(?P<name>.+)$")
SUFFIX_PATTERN = re.compile(rf"^(?P<name>.+?)(?P<amount>{AMOUNT_TOKEN_PATTERN})(?P<unit>{UNIT_PATTERN})$")
SPACE_SUFFIX_PATTERN = re.compile(rf"^(?P<name>.+?)\s+(?P<amount>{AMOUNT_TOKEN_PATTERN})(?P<unit>{UNIT_PATTERN})?$")


def parse_ingredients_text(ingredients_text: Optional[str]) -> List[Dict[str, Optional[str]]]:
    if not ingredients_text:
        return []

    parsed_items: List[Dict[str, Optional[str]]] = []
    for raw_part in SPLIT_PATTERN.split(ingredients_text):
        cleaned_part = raw_part.strip(" \t\r\n-•·")
        if not cleaned_part:
            continue

        name, amount, unit, remark = _split_ingredient_part(cleaned_part)
        normalized_name = normalize_ingredient_name(name)
        if not normalized_name:
            continue

        parsed_items.append(
            {
                "name": normalized_name,
                "normalized_name": normalized_name,
                "amount": _normalize_amount(amount),
                "unit": unit,
                "remark": remark,
            }
        )

    return _dedupe_ingredient_items(parsed_items)


def normalize_ingredient_name(name: str) -> str:
    compact = re.sub(r"\s+", "", name.strip())
    compact = PAREN_PATTERN.sub("", compact)
    compact = BOOK_TITLE_PATTERN.sub("", compact)
    compact = compact.strip("（）；，,;:： ")
    compact = _strip_remark_prefix(compact)
    compact = _strip_brand_prefix(compact)
    return INGREDIENT_ALIAS_MAP.get(compact, compact)


def sync_recipe_ingredients(connection, recipe_id: int, ingredients_text: Optional[str]) -> None:
    connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))

    parsed_items = parse_ingredients_text(ingredients_text)
    if not parsed_items:
        return

    for item in parsed_items:
        ingredient_id = _get_or_create_ingredient(connection, item["name"], item["normalized_name"])
        connection.execute(
            """
            INSERT INTO recipe_ingredients (
                recipe_id,
                ingredient_id,
                amount,
                unit,
                remark
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (recipe_id, ingredient_id, item["amount"], item["unit"], item["remark"]),
        )

    connection.execute(
        """
        DELETE FROM ingredients
        WHERE id NOT IN (
            SELECT DISTINCT ingredient_id
            FROM recipe_ingredients
        )
        """
    )


def sync_recipe_ingredients_from_items(connection, recipe_id: int, items: List[Dict[str, Optional[str]]]) -> None:
    connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))

    if not items:
        connection.execute(
            """
            DELETE FROM ingredients
            WHERE id NOT IN (
                SELECT DISTINCT ingredient_id
                FROM recipe_ingredients
            )
            """
        )
        return

    normalized_items = _dedupe_ingredient_items(
        [
            {
                "name": normalize_ingredient_name(item.get("name") or ""),
                "normalized_name": normalize_ingredient_name(item.get("name") or ""),
                "amount": _normalize_amount(item.get("amount")),
                "unit": item.get("unit"),
                "remark": _normalize_remark(item.get("remark")),
            }
            for item in items
            if normalize_ingredient_name(item.get("name") or "")
        ]
    )

    for item in normalized_items:
        ingredient_id = _get_or_create_ingredient(connection, item["name"], item["normalized_name"])
        connection.execute(
            """
            INSERT INTO recipe_ingredients (
                recipe_id,
                ingredient_id,
                amount,
                unit,
                remark
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (recipe_id, ingredient_id, item["amount"], item["unit"], item["remark"]),
        )

    connection.execute(
        """
        DELETE FROM ingredients
        WHERE id NOT IN (
            SELECT DISTINCT ingredient_id
            FROM recipe_ingredients
        )
        """
    )


def _get_or_create_ingredient(connection, name: str, normalized_name: str) -> int:
    row = connection.execute(
        """
        SELECT id
        FROM ingredients
        WHERE normalized_name = ?
           OR name = ?
        ORDER BY id
        LIMIT 1
        """,
        (normalized_name, name),
    ).fetchone()

    if row is not None:
        return row["id"]

    cursor = connection.execute(
        """
        INSERT INTO ingredients (name, alias, normalized_name)
        VALUES (?, ?, ?)
        """,
        (normalized_name, name if normalized_name != name else None, normalized_name),
    )
    return cursor.lastrowid


def _split_ingredient_part(part: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    inline_remarks = [match.strip() for match in PAREN_PATTERN.findall(part) if match.strip()]
    base_part = PAREN_PATTERN.sub(" ", part)
    base_part = re.sub(r"\s+", " ", base_part).strip(" （）；，,;")

    if _should_drop_phrase(base_part):
        return "", None, None, None

    remark_parts: List[str] = []

    preparation_remark = _extract_preparation_remark(base_part)
    if preparation_remark:
        base_part = base_part[: -len(preparation_remark)].strip(" （）；，,;")
        remark_parts.append(preparation_remark)

    compact_part = re.sub(r"\s+", "", base_part)
    name, amount, unit, trailing_remark = _extract_structured_fields(base_part, compact_part)
    if trailing_remark:
        remark_parts.append(trailing_remark)

    if not name:
        return "", None, None, None

    prefix_remark = _extract_remark_prefix(name)
    if prefix_remark:
        remark_parts.append(prefix_remark)
        name = _strip_remark_prefix(name)

    normalized_name = normalize_ingredient_name(name)
    if not normalized_name or _should_drop_phrase(normalized_name):
        return "", None, None, None

    remark = _join_remark_parts(inline_remarks + remark_parts)
    return normalized_name, amount, unit, remark


def _extract_structured_fields(base_part: str, compact_part: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    prefixed_match = PREFIX_PATTERN.match(compact_part)
    if prefixed_match:
        name = prefixed_match.group("name")
        if _looks_like_ingredient_name(name):
            return name, prefixed_match.group("amount"), prefixed_match.group("unit"), None

    suffix_match = SUFFIX_PATTERN.match(compact_part)
    if suffix_match:
        name = suffix_match.group("name")
        if _looks_like_ingredient_name(name):
            return name, suffix_match.group("amount"), suffix_match.group("unit"), None

    spaced_match = SPACE_SUFFIX_PATTERN.match(base_part)
    if spaced_match:
        name = spaced_match.group("name").strip()
        if _looks_like_ingredient_name(name):
            return name, spaced_match.group("amount"), spaced_match.group("unit"), None

    name, rest = _extract_name_and_rest(base_part)
    amount, unit, trailing_remark = _split_amount_and_unit(rest)
    return name, amount, unit, trailing_remark


def _extract_name_and_rest(part: str) -> Tuple[str, str]:
    if " " in part:
        name, rest = part.split(" ", 1)
        return name.strip(), rest.strip()

    amount_match = re.search(AMOUNT_TOKEN_PATTERN, part)
    if amount_match and amount_match.start() > 0:
        return part[: amount_match.start()].strip(), part[amount_match.start() :].strip()

    return part.strip(), ""


def _split_amount_and_unit(rest: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not rest:
        return None, None, None

    normalized_rest = rest.strip(" ，,;；")

    for token in QUALITATIVE_AMOUNTS:
        if normalized_rest.startswith(token):
            trailing = normalized_rest[len(token) :].strip(" ，,;；")
            return token, None, _normalize_remark(trailing)

    amount_match = re.match(rf"^(?P<amount>{AMOUNT_TOKEN_PATTERN})(?P<tail>.*)$", normalized_rest)
    if not amount_match:
        return None, None, _normalize_remark(normalized_rest)

    amount = amount_match.group("amount")
    tail = amount_match.group("tail").strip()
    unit, trailing = _extract_unit_and_remark(tail)
    return amount, unit, _normalize_remark(trailing)


def _extract_unit_and_remark(tail: str) -> Tuple[Optional[str], Optional[str]]:
    if not tail:
        return None, None

    for unit in sorted(KNOWN_UNITS, key=len, reverse=True):
        if tail.startswith(unit):
            trailing = tail[len(unit) :].strip(" ，,;；")
            return unit, trailing or None

    if " " in tail:
        unit, trailing = tail.split(" ", 1)
        return unit.strip() or None, trailing.strip() or None

    return None, tail or None


def _extract_preparation_remark(part: str) -> Optional[str]:
    for phrase in PREPARATION_WORDS:
        if part.endswith(phrase):
            return phrase
    return None


def _looks_like_ingredient_name(value: str) -> bool:
    if not value:
        return False

    normalized = re.sub(r"\s+", "", value)
    if re.search(AMOUNT_TOKEN_PATTERN, normalized):
        return False
    if _should_drop_phrase(normalized):
        return False
    return True


def _normalize_amount(amount: Optional[str]) -> Optional[str]:
    if not amount:
        return None

    cleaned = amount.strip()
    combined_amount_map = {
        "一个": "1",
        "两个": "2",
        "三个": "3",
        "四个": "4",
        "五个": "5",
        "六个": "6",
        "七个": "7",
        "八个": "8",
        "九个": "9",
        "十个": "10",
    }
    if cleaned in combined_amount_map:
        return combined_amount_map[cleaned]

    amount_map = {
        "半": "0.5",
        "一": "1",
        "二": "2",
        "两": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "10",
    }
    return amount_map.get(cleaned, cleaned)


def _normalize_remark(remark: Optional[str]) -> Optional[str]:
    if not remark:
        return None
    cleaned = remark.strip(" （）；，,;:：")
    return cleaned or None


def _join_remark_parts(parts: List[str]) -> Optional[str]:
    cleaned_parts: List[str] = []
    seen = set()
    for part in parts:
        normalized = _normalize_remark(part)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned_parts.append(normalized)
    return "；".join(cleaned_parts) if cleaned_parts else None


def _dedupe_ingredient_items(items: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    exact_seen = set()
    exact_items: List[Dict[str, Optional[str]]] = []
    for item in items:
        dedupe_key = (
            item["normalized_name"],
            item["amount"] or "",
            item["unit"] or "",
            item["remark"] or "",
        )
        if dedupe_key in exact_seen:
            continue
        exact_seen.add(dedupe_key)
        exact_items.append(item)

    grouped: Dict[str, List[Dict[str, Optional[str]]]] = {}
    for item in exact_items:
        grouped.setdefault(item["normalized_name"], []).append(item)

    merged_items: List[Dict[str, Optional[str]]] = []
    for group in grouped.values():
        has_structured_variant = any(item["amount"] or item["unit"] or item["remark"] for item in group)
        if not has_structured_variant:
            merged_items.extend(group)
            continue

        for item in group:
            if not item["amount"] and not item["unit"] and not item["remark"]:
                continue
            merged_items.append(item)

    return merged_items


def _should_drop_phrase(value: str) -> bool:
    normalized = re.sub(r"\s+", "", value or "")
    if not normalized:
        return True

    lowered = normalized.lower()
    if any(token.lower() in lowered for token in DROP_HINTS):
        return True
    if any(lowered.startswith(prefix.lower()) for prefix in DROP_PREFIXES):
        return True
    if normalized.startswith(("约", "大概", "至少", "最少", "最多")):
        return True
    if len(normalized) >= 8 and any(symbol in normalized for symbol in ("：", ":", "。", "*", "=")):
        return True
    if len(normalized) >= 10 and any(symbol in normalized for symbol in ("/", "+")):
        return True
    if len(normalized) >= 8 and re.search(r"[A-Za-z]{4,}.*[A-Za-z]{4,}", normalized):
        return True
    if len(normalized) >= 8 and any(char in normalized for char in ("我", "你", "他", "她", "它")):
        return True
    return False


def _extract_remark_prefix(name: str) -> Optional[str]:
    compact = re.sub(r"\s+", "", name or "")
    for prefix in REMARK_PREFIXES:
        if compact.startswith(prefix) and len(compact) > len(prefix):
            return prefix
    return None


def _strip_remark_prefix(value: str) -> str:
    compact = re.sub(r"\s+", "", value or "")
    for prefix in REMARK_PREFIXES:
        if compact.startswith(prefix) and len(compact) > len(prefix):
            return compact[len(prefix) :]
    return compact


def _strip_brand_prefix(value: str) -> str:
    compact = re.sub(r"\s+", "", value or "")
    chinese_suffixes = [
        "奶酪",
        "牛奶",
        "豆腐",
        "黄油",
        "辣酱",
        "咖喱酱",
        "红椒膏",
        "面酱",
        "酱",
        "面",
        "饼",
        "水",
    ]
    for suffix in chinese_suffixes:
        match = re.match(rf"^[A-Za-z][A-Za-z0-9-]*({suffix})$", compact)
        if match:
            return match.group(1)
    return compact
