import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
CHECKMARKS = {"√", "✓", "1", "true", "TRUE"}
BACKLOG_SHEET = "再挑战及待记录"
DESSERT_SHEET = "甜点配方专区"
DETAIL_SUFFIX = "做法"
RECIPE_WORKBOOK_HINTS = {"牛肉", "牛肉做法", "鸡肉", "鸡肉做法", DESSERT_SHEET}
UNGROUPED_SECTION = "无分组"


@dataclass
class ParsedRecord:
    source_key: str
    source_hash_payload: Dict[str, Any]
    recipe_payload: Dict[str, Any]
    raw_payload: Dict[str, Any]


class WorkbookStructureError(ValueError):
    pass


class XlsxWorkbook:
    def __init__(self, raw_bytes: bytes):
        try:
            self.archive = zipfile.ZipFile(BytesIO(raw_bytes))
        except zipfile.BadZipFile as error:
            raise WorkbookStructureError("无法读取 Excel 文件，请确认文件是未损坏的 .xlsx。") from error

        self.shared_strings = self._load_shared_strings()
        self.sheets = self._load_sheet_map()

    def _load_shared_strings(self) -> List[str]:
        if "xl/sharedStrings.xml" not in self.archive.namelist():
            return []

        root = ET.fromstring(self.archive.read("xl/sharedStrings.xml"))
        values: List[str] = []
        for item in root.findall("a:si", NS):
            text = "".join(node.text or "" for node in item.findall(".//a:t", NS))
            values.append(text)
        return values

    def _load_sheet_map(self) -> Dict[str, str]:
        workbook_root = ET.fromstring(self.archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: f"xl/{rel.attrib['Target']}" for rel in rels_root}

        sheets: Dict[str, str] = {}
        for sheet in workbook_root.findall("a:sheets/a:sheet", NS):
            sheets[sheet.attrib["name"]] = rel_map[sheet.attrib[REL_ID_ATTR]]
        return sheets

    def sheet_names(self) -> List[str]:
        return list(self.sheets.keys())

    def read_sheet(self, name: str) -> List[Dict[str, Any]]:
        target = self.sheets.get(name)
        if not target:
            return []

        root = ET.fromstring(self.archive.read(target))
        row_map: Dict[int, Dict[str, Any]] = {}

        for row in root.findall(".//a:sheetData/a:row", NS):
            row_number = int(row.attrib.get("r", "0") or 0)
            cells: Dict[str, Any] = {"_row_number": row_number}
            for cell in row.findall("a:c", NS):
                reference = cell.attrib.get("r", "")
                column = _column_letters(reference)
                value = self._read_cell_value(cell)
                if value not in (None, ""):
                    cells[column] = value
            if len(cells) > 1:
                row_map[row_number] = cells

        for merged_cell in root.findall(".//a:mergeCells/a:mergeCell", NS):
            start_col, start_row, end_col, end_row = _parse_range_reference(merged_cell.attrib.get("ref", ""))
            if not start_col or start_row == 0:
                continue

            row_entry = row_map.setdefault(start_row, {"_row_number": start_row})
            merge_starts = row_entry.setdefault("_merge_starts", {})
            merge_starts[start_col] = {
                "start_col": start_col,
                "start_row": start_row,
                "end_col": end_col,
                "end_row": end_row,
                "value": row_entry.get(start_col),
            }

        return [row_map[row_number] for row_number in sorted(row_map)]

    def _read_cell_value(self, cell) -> Optional[str]:
        cell_type = cell.attrib.get("t")
        value_node = cell.find("a:v", NS)
        inline_node = cell.find("a:is", NS)

        if cell_type == "s" and value_node is not None and value_node.text:
            return self.shared_strings[int(value_node.text)]
        if cell_type == "inlineStr" and inline_node is not None:
            return "".join(node.text or "" for node in inline_node.findall(".//a:t", NS))
        if value_node is not None and value_node.text is not None:
            return value_node.text.strip()
        return None


def parse_recipe_workbook(
    raw_bytes: bytes,
    pair_overrides: Optional[List[Dict[str, str]]] = None,
    include_review: bool = False,
) -> Dict[str, Any]:
    workbook = XlsxWorkbook(raw_bytes)
    sheet_names = workbook.sheet_names()
    if not RECIPE_WORKBOOK_HINTS.issubset(set(sheet_names)):
        raise WorkbookStructureError("当前导入器现在只支持这份真实菜谱工作簿的结构。")

    normalized_overrides = _normalize_pair_overrides(pair_overrides or [])
    review_sections: List[Dict[str, Any]] = []
    records: List[ParsedRecord] = []
    stats = {
        "paired_recipes": 0,
        "index_only_recipes": 0,
        "detail_only_recipes": 0,
        "dessert_recipes": 0,
        "backlog_items": 0,
    }

    base_sections = [
        name
        for name in sheet_names
        if name not in {BACKLOG_SHEET, DESSERT_SHEET} and not name.endswith(DETAIL_SUFFIX)
    ]

    for base_section in base_sections:
        detail_sheet = f"{base_section}{DETAIL_SUFFIX}"
        if detail_sheet not in workbook.sheets:
            continue

        pair_result = _parse_paired_section(
            base_section=base_section,
            index_rows=workbook.read_sheet(base_section),
            detail_rows=workbook.read_sheet(detail_sheet),
            overrides=normalized_overrides.get(base_section, []),
            include_review=include_review,
        )
        records.extend(pair_result["records"])
        for key, value in pair_result["stats"].items():
            stats[key] += value
        if include_review and pair_result.get("review"):
            review_sections.append(pair_result["review"])

    dessert_records = _parse_dessert_sheet(workbook.read_sheet(DESSERT_SHEET))
    records.extend(dessert_records)
    stats["dessert_recipes"] = len(dessert_records)

    backlog_records = _parse_backlog_sheet(workbook.read_sheet(BACKLOG_SHEET))
    records.extend(backlog_records)
    stats["backlog_items"] = len(backlog_records)

    _dedupe_source_keys(records)

    preview_rows = [_build_preview_row(record.recipe_payload) for record in records[:12]]
    library_sections = _count_labels(record.recipe_payload["library_section"] for record in records)
    record_statuses = _count_labels(
        _record_status_label(record.recipe_payload["record_kind"], record.recipe_payload.get("backlog_status"))
        for record in records
    )

    return {
        "parser_kind": "recipe_workbook_v2",
        "sheet_names": sheet_names,
        "records": records,
        "fields": _import_fields(),
        "preview_rows": preview_rows,
        "pairing_review": review_sections if include_review else [],
        "summary": {
            "total_records": len(records),
            "recipe_records": sum(1 for record in records if record.recipe_payload["record_kind"] == "recipe"),
            "backlog_records": sum(1 for record in records if record.recipe_payload["record_kind"] == "backlog"),
            "library_sections": library_sections,
            "record_statuses": record_statuses,
            "pair_override_count": len(pair_overrides or []),
            **stats,
        },
    }


def _parse_paired_section(
    base_section: str,
    index_rows: List[Dict[str, Any]],
    detail_rows: List[Dict[str, Any]],
    overrides: List[Dict[str, str]],
    include_review: bool,
) -> Dict[str, Any]:
    index_items = _parse_index_sheet(base_section, index_rows)
    detail_items = _parse_detail_sheet(base_section, detail_rows)
    matched_pairs, unmatched_indexes, unmatched_details = _match_index_and_detail(index_items, detail_items, overrides)

    records: List[ParsedRecord] = []
    for index_item, detail_item in matched_pairs:
        records.append(_build_recipe_record(base_section, index_item=index_item, detail_item=detail_item))

    for index_item in unmatched_indexes:
        records.append(_build_recipe_record(base_section, index_item=index_item, detail_item=None))

    for detail_item in unmatched_details:
        records.append(_build_recipe_record(base_section, index_item=None, detail_item=detail_item))

    review = None
    if include_review and (unmatched_indexes or unmatched_details):
        review = {
            "library_section": base_section,
            "index_only_count": len(unmatched_indexes),
            "detail_only_count": len(unmatched_details),
            "index_only_items": _build_index_review_items(unmatched_indexes, unmatched_details),
            "detail_only_items": _build_detail_review_items(unmatched_details, unmatched_indexes),
        }

    return {
        "records": records,
        "stats": {
            "paired_recipes": len(matched_pairs),
            "index_only_recipes": len(unmatched_indexes),
            "detail_only_recipes": len(unmatched_details),
        },
        "review": review,
    }


def _parse_index_sheet(base_section: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current_section: Optional[str] = None

    for row in rows[1:]:
        if row.get("D") == "菜名":
            continue

        next_section = _resolve_section_name(row, section_column="A", header_columns=("B",), name_column="D")
        if next_section is not None:
            current_section = next_section

        name = _clean_text(row.get("D"))
        if not name:
            continue

        review_value = _clean_text(row.get("G"))
        review_date = _parse_excel_date(review_value)
        source_reference = None if review_date else review_value

        items.append(
            {
                "item_ref": f"index|{base_section}|{row.get('_row_number')}",
                "row_number": row.get("_row_number"),
                "base_section": base_section,
                "section_name": current_section or UNGROUPED_SECTION,
                "name": name,
                "name_keys": _name_keys(name),
                "cuisine": _normalize_nullable_text(row.get("E")),
                "sub_cuisine": _normalize_nullable_text(row.get("F")),
                "source_reference": source_reference,
                "last_reviewed_on": review_date,
                "bmd_flag": _checked(row.get("B")),
                "cc_flag": _checked(row.get("C")),
                "raw_row": row,
            }
        )

    return items


def _parse_detail_sheet(base_section: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current_section: Optional[str] = None

    for row in rows:
        if row.get("B") == "菜名":
            continue

        next_section = _resolve_section_name(row, section_column="A", header_columns=("B",), name_column="B")
        if next_section is not None:
            current_section = next_section

        name = _clean_text(row.get("B"))
        if not name:
            continue

        items.append(
            {
                "item_ref": f"detail|{base_section}|{row.get('_row_number')}",
                "row_number": row.get("_row_number"),
                "base_section": base_section,
                "section_name": current_section or UNGROUPED_SECTION,
                "name": name,
                "name_keys": _name_keys(name),
                "ingredients_text": _clean_text(row.get("C")),
                "seasonings_text": _clean_text(row.get("D")),
                "steps_text": _clean_text(row.get("E")),
                "raw_row": row,
            }
        )

    return items


def _parse_dessert_sheet(rows: List[Dict[str, Any]]) -> List[ParsedRecord]:
    records: List[ParsedRecord] = []
    current_section: Optional[str] = None

    for row in rows[1:]:
        if row.get("A"):
            current_section = _clean_text(row.get("A"))

        name = _clean_text(row.get("B"))
        if not name:
            continue

        payload = _base_recipe_payload(
            name=name,
            source_key=f"recipe|{DESSERT_SHEET}|{_stable_name_key(name)}",
            record_kind="recipe",
            backlog_status=None,
            alias=None,
            library_section=DESSERT_SHEET,
            section_name=current_section,
            category=current_section,
            cuisine=None,
            sub_cuisine=None,
            ingredients_text=_clean_text(row.get("C")),
            seasonings_text=None,
            steps_text=_clean_text(row.get("D")),
            notes_text=None,
            source_reference=None,
            last_reviewed_on=None,
            bmd_flag=False,
            cc_flag=False,
            source_text=_build_source_text(
                title=name,
                blocks=[
                    ("专题库", DESSERT_SHEET),
                    ("类别", current_section),
                    ("食材", row.get("C")),
                    ("做法", row.get("D")),
                ],
            ),
        )
        records.append(
            ParsedRecord(
                source_key=payload["source_key"],
                source_hash_payload=payload,
                recipe_payload=payload,
                raw_payload={
                    "sheet": DESSERT_SHEET,
                    "row_number": row.get("_row_number"),
                    "raw_row": row,
                },
            )
        )

    return records


def _parse_backlog_sheet(rows: List[Dict[str, Any]]) -> List[ParsedRecord]:
    records: List[ParsedRecord] = []

    for row in rows[1:]:
        for column, status in (("A", "待挑战"), ("D", "待记录")):
            name = _clean_text(row.get(column))
            if not name:
                continue

            payload = _base_recipe_payload(
                name=name,
                source_key=f"backlog|{status}|{_stable_name_key(name)}",
                record_kind="backlog",
                backlog_status=status,
                alias=None,
                library_section=BACKLOG_SHEET,
                section_name=status,
                category=status,
                cuisine=None,
                sub_cuisine=None,
                ingredients_text=None,
                seasonings_text=None,
                steps_text=None,
                notes_text=None,
                source_reference=None,
                last_reviewed_on=None,
                bmd_flag=False,
                cc_flag=False,
                source_text=_build_source_text(
                    title=name,
                    blocks=[
                        ("记录类型", "待办事项"),
                        ("状态", status),
                        ("来源工作表", BACKLOG_SHEET),
                    ],
                ),
            )
            records.append(
                ParsedRecord(
                    source_key=payload["source_key"],
                    source_hash_payload=payload,
                    recipe_payload=payload,
                    raw_payload={
                        "sheet": BACKLOG_SHEET,
                        "row_number": row.get("_row_number"),
                        "column": column,
                        "raw_row": row,
                    },
                )
            )

    return records


def _build_recipe_record(
    base_section: str,
    index_item: Optional[Dict[str, Any]],
    detail_item: Optional[Dict[str, Any]],
) -> ParsedRecord:
    display_name = (index_item or {}).get("name") or (detail_item or {}).get("name") or "未命名菜谱"
    alias = _build_alias(index_item, detail_item)
    section_name = (index_item or {}).get("section_name") or (detail_item or {}).get("section_name")
    notes = []
    if index_item is None:
        notes.append("索引页未找到对应条目。")
    if detail_item is None:
        notes.append("做法页未找到对应条目。")

    match_key = _match_key_for_source(index_item, detail_item, display_name)
    payload = _base_recipe_payload(
        name=display_name,
        source_key=f"recipe|{base_section}|{match_key}",
        record_kind="recipe",
        backlog_status=None,
        alias=alias,
        library_section=base_section,
        section_name=section_name,
        category=section_name,
        cuisine=(index_item or {}).get("cuisine"),
        sub_cuisine=(index_item or {}).get("sub_cuisine"),
        ingredients_text=(detail_item or {}).get("ingredients_text"),
        seasonings_text=(detail_item or {}).get("seasonings_text"),
        steps_text=(detail_item or {}).get("steps_text"),
        notes_text="\n".join(notes) or None,
        source_reference=(index_item or {}).get("source_reference"),
        last_reviewed_on=(index_item or {}).get("last_reviewed_on"),
        bmd_flag=bool((index_item or {}).get("bmd_flag")),
        cc_flag=bool((index_item or {}).get("cc_flag")),
        source_text=_build_source_text(
            title=display_name,
            blocks=[
                ("专题库", base_section),
                ("分组", section_name),
                ("菜系", (index_item or {}).get("cuisine")),
                ("亚菜系", (index_item or {}).get("sub_cuisine")),
                ("BMD", "是" if (index_item or {}).get("bmd_flag") else "否"),
                ("CC", "是" if (index_item or {}).get("cc_flag") else "否"),
                ("最后记录日期", (index_item or {}).get("last_reviewed_on")),
                ("来源/修订备注", (index_item or {}).get("source_reference")),
                ("食材", (detail_item or {}).get("ingredients_text")),
                ("调料", (detail_item or {}).get("seasonings_text")),
                ("做法及要点", (detail_item or {}).get("steps_text")),
                ("系统备注", "\n".join(notes) or None),
            ],
        ),
    )

    return ParsedRecord(
        source_key=payload["source_key"],
        source_hash_payload=payload,
        recipe_payload=payload,
        raw_payload={
            "index_sheet": base_section,
            "index_row_number": (index_item or {}).get("raw_row", {}).get("_row_number"),
            "index_row": (index_item or {}).get("raw_row"),
            "detail_sheet": f"{base_section}{DETAIL_SUFFIX}",
            "detail_row_number": (detail_item or {}).get("raw_row", {}).get("_row_number"),
            "detail_row": (detail_item or {}).get("raw_row"),
        },
    )


def _match_index_and_detail(
    index_items: List[Dict[str, Any]],
    detail_items: List[Dict[str, Any]],
    overrides: List[Dict[str, str]],
) -> Tuple[List[Tuple[Dict[str, Any], Dict[str, Any]]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    matches: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    matched_indexes = set()
    matched_details = set()

    _apply_override_pairs(matches, matched_indexes, matched_details, index_items, detail_items, overrides)

    detail_key_map: Dict[str, List[int]] = {}
    for detail_index, detail_item in enumerate(detail_items):
        for key in detail_item["name_keys"]:
            detail_key_map.setdefault(key, []).append(detail_index)

    for index_pos, index_item in enumerate(index_items):
        if index_pos in matched_indexes:
            continue

        exact_candidates = {
            candidate
            for key in index_item["name_keys"]
            for candidate in detail_key_map.get(key, [])
            if candidate not in matched_details
        }
        if len(exact_candidates) == 1:
            detail_pos = exact_candidates.pop()
            matches.append((index_item, detail_items[detail_pos]))
            matched_indexes.add(index_pos)
            matched_details.add(detail_pos)

    for index_pos, index_item in enumerate(index_items):
        if index_pos in matched_indexes:
            continue

        best_detail_pos = None
        best_score = 0.0
        second_score = 0.0

        for detail_pos, detail_item in enumerate(detail_items):
            if detail_pos in matched_details:
                continue
            score = _name_similarity(index_item, detail_item)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_detail_pos = detail_pos
            elif score > second_score:
                second_score = score

        if best_detail_pos is not None and best_score >= 0.64 and (best_score - second_score) >= 0.06:
            matches.append((index_item, detail_items[best_detail_pos]))
            matched_indexes.add(index_pos)
            matched_details.add(best_detail_pos)

    unmatched_indexes = [item for position, item in enumerate(index_items) if position not in matched_indexes]
    unmatched_details = [item for position, item in enumerate(detail_items) if position not in matched_details]
    return matches, unmatched_indexes, unmatched_details


def _apply_override_pairs(
    matches: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    matched_indexes: set,
    matched_details: set,
    index_items: List[Dict[str, Any]],
    detail_items: List[Dict[str, Any]],
    overrides: List[Dict[str, str]],
) -> None:
    for override in overrides:
        override_index_ref = _clean_text(override.get("index_ref"))
        override_detail_ref = _clean_text(override.get("detail_ref"))
        index_pos = next(
            (
                position
                for position, item in enumerate(index_items)
                if position not in matched_indexes
                and (
                    (override_index_ref and item.get("item_ref") == override_index_ref)
                    or (
                        not override_index_ref
                        and _clean_text(item["name"]) == override["index_name"]
                    )
                )
            ),
            None,
        )
        detail_pos = next(
            (
                position
                for position, item in enumerate(detail_items)
                if position not in matched_details
                and (
                    (override_detail_ref and item.get("item_ref") == override_detail_ref)
                    or (
                        not override_detail_ref
                        and _clean_text(item["name"]) == override["detail_name"]
                    )
                )
            ),
            None,
        )
        if index_pos is None or detail_pos is None:
            continue

        matches.append((index_items[index_pos], detail_items[detail_pos]))
        matched_indexes.add(index_pos)
        matched_details.add(detail_pos)


def _build_index_review_items(index_items: List[Dict[str, Any]], detail_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "item_ref": item.get("item_ref"),
            "row_number": item.get("row_number"),
            "name": item["name"],
            "section_name": item.get("section_name"),
            "suggestions": _suggest_detail_matches(item, detail_pool),
        }
        for item in index_items
    ]


def _build_detail_review_items(detail_items: List[Dict[str, Any]], index_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "item_ref": item.get("item_ref"),
            "row_number": item.get("row_number"),
            "name": item["name"],
            "section_name": item.get("section_name"),
            "suggestions": _suggest_index_matches(item, index_pool),
        }
        for item in detail_items
    ]


def _suggest_detail_matches(index_item: Dict[str, Any], detail_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for detail_item in detail_pool:
        score = _name_similarity(index_item, detail_item)
        if score < 0.45:
            continue
        ranked.append(
            {
                "detail_ref": detail_item.get("item_ref"),
                "detail_name": detail_item["name"],
                "row_number": detail_item.get("row_number"),
                "section_name": detail_item.get("section_name"),
                "score": round(score, 3),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["detail_name"]))
    return ranked[:3]


def _suggest_index_matches(detail_item: Dict[str, Any], index_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for index_item in index_pool:
        score = _name_similarity(index_item, detail_item)
        if score < 0.45:
            continue
        ranked.append(
            {
                "index_ref": index_item.get("item_ref"),
                "index_name": index_item["name"],
                "row_number": index_item.get("row_number"),
                "section_name": index_item.get("section_name"),
                "score": round(score, 3),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["index_name"]))
    return ranked[:3]


def _normalize_pair_overrides(pair_overrides: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    normalized: Dict[str, List[Dict[str, str]]] = {}
    for item in pair_overrides:
        library_section = _clean_text(item.get("library_section"))
        index_name = _clean_text(item.get("index_name"))
        detail_name = _clean_text(item.get("detail_name"))
        index_ref = _clean_text(item.get("index_ref"))
        detail_ref = _clean_text(item.get("detail_ref"))
        if not library_section or not index_name or not detail_name:
            continue
        normalized.setdefault(library_section, []).append(
            {
                "library_section": library_section,
                "index_ref": index_ref,
                "index_name": index_name,
                "detail_ref": detail_ref,
                "detail_name": detail_name,
            }
        )
    return normalized


def _name_similarity(index_item: Dict[str, Any], detail_item: Dict[str, Any]) -> float:
    left_candidates = index_item["name_keys"] or {_stable_name_key(index_item["name"])}
    right_candidates = detail_item["name_keys"] or {_stable_name_key(detail_item["name"])}
    best = 0.0

    for left in left_candidates:
        for right in right_candidates:
            best = max(best, SequenceMatcher(None, left, right).ratio())

    if (
        index_item.get("section_name")
        and detail_item.get("section_name")
        and index_item["section_name"] == detail_item["section_name"]
    ):
        best += 0.05

    return min(best, 1.0)


def _base_recipe_payload(**kwargs) -> Dict[str, Any]:
    return {
        "name": kwargs["name"],
        "record_kind": kwargs["record_kind"],
        "backlog_status": kwargs["backlog_status"],
        "alias": kwargs["alias"],
        "library_section": kwargs["library_section"],
        "section_name": kwargs["section_name"],
        "category": kwargs["category"],
        "cuisine": kwargs["cuisine"],
        "sub_cuisine": kwargs["sub_cuisine"],
        "flavor": None,
        "difficulty": None,
        "estimated_time": None,
        "servings": None,
        "tools": None,
        "ingredients_text": kwargs["ingredients_text"],
        "seasonings_text": kwargs["seasonings_text"],
        "steps_text": kwargs["steps_text"],
        "notes_text": kwargs["notes_text"],
        "source_reference": kwargs["source_reference"],
        "last_reviewed_on": kwargs["last_reviewed_on"],
        "bmd_flag": int(bool(kwargs["bmd_flag"])),
        "cc_flag": int(bool(kwargs["cc_flag"])),
        "source_text": kwargs["source_text"],
        "tags": [],
        "source_key": kwargs["source_key"],
    }


def _build_preview_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "record_kind": _record_status_label(payload["record_kind"], payload.get("backlog_status")),
        "name": payload["name"],
        "library_section": payload["library_section"],
        "section_name": payload["section_name"],
        "cuisine": payload["cuisine"],
        "sub_cuisine": payload["sub_cuisine"],
        "bmd_flag": "是" if payload["bmd_flag"] else "",
        "cc_flag": "是" if payload["cc_flag"] else "",
        "last_reviewed_on": payload["last_reviewed_on"],
        "source_reference": payload["source_reference"],
        "ingredients_text": payload["ingredients_text"],
        "seasonings_text": payload["seasonings_text"],
        "steps_text": payload["steps_text"],
        "notes_text": payload["notes_text"],
    }


def _import_fields() -> List[Dict[str, str]]:
    return [
        {"key": "record_kind", "label": "记录类型"},
        {"key": "name", "label": "名称"},
        {"key": "library_section", "label": "专题库"},
        {"key": "section_name", "label": "分组"},
        {"key": "cuisine", "label": "菜系"},
        {"key": "sub_cuisine", "label": "亚菜系"},
        {"key": "bmd_flag", "label": "BMD"},
        {"key": "cc_flag", "label": "CC"},
        {"key": "last_reviewed_on", "label": "最后记录日期"},
        {"key": "source_reference", "label": "来源/修订备注"},
        {"key": "ingredients_text", "label": "食材"},
        {"key": "seasonings_text", "label": "调料"},
        {"key": "steps_text", "label": "做法及要点"},
        {"key": "notes_text", "label": "系统备注"},
    ]


def _build_alias(index_item: Optional[Dict[str, Any]], detail_item: Optional[Dict[str, Any]]) -> Optional[str]:
    names = [item["name"] for item in (index_item, detail_item) if item and item.get("name")]
    if len(names) < 2:
        return None
    if names[0] == names[1]:
        return None
    return names[1]


def _match_key_for_source(
    index_item: Optional[Dict[str, Any]],
    detail_item: Optional[Dict[str, Any]],
    fallback_name: str,
) -> str:
    if index_item and detail_item:
        shared = index_item["name_keys"] & detail_item["name_keys"]
        if shared:
            return sorted(shared, key=len, reverse=True)[0]
    if index_item and index_item["name_keys"]:
        return sorted(index_item["name_keys"], key=len, reverse=True)[0]
    if detail_item and detail_item["name_keys"]:
        return sorted(detail_item["name_keys"], key=len, reverse=True)[0]
    return _stable_name_key(fallback_name)


def _name_keys(name: Optional[str]) -> set[str]:
    text = _clean_text(name)
    if not text:
        return set()

    keys = set()
    full_key = _stable_name_key(text)
    if full_key:
        keys.add(full_key)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        key = _stable_name_key(line)
        if key:
            keys.add(key)

    stripped = _strip_annotations(text)
    if stripped and stripped != text:
        keys.add(_stable_name_key(stripped))
        for line in [line.strip() for line in stripped.splitlines() if line.strip()]:
            key = _stable_name_key(line)
            if key:
                keys.add(key)

    return {key for key in keys if key}


def _stable_name_key(value: Optional[str]) -> str:
    text = _strip_annotations(_clean_text(value))
    if not text:
        return ""

    lines = [line.strip("：: ") for line in text.splitlines() if line.strip()]
    candidate = max(lines, key=len) if len(lines) > 1 else (lines[0] if lines else text)
    candidate = re.sub(r"[\s\u3000]+", "", candidate)
    candidate = candidate.replace("：", "").replace(":", "")
    candidate = candidate.replace("（真）", "")
    candidate = re.sub(r"[·•/]+", "", candidate)
    return candidate.lower()


def _strip_annotations(text: Optional[str]) -> str:
    value = _clean_text(text)
    if not value:
        return ""

    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"[（(【\[].*?[）)】\]]", "", value)
    value = re.sub(r"\n+", "\n", value)
    return value.strip()


def _parse_excel_date(raw_value: Optional[str]) -> Optional[str]:
    value = _clean_text(raw_value)
    if not value:
        return None

    if re.fullmatch(r"\d{5}", value):
        base = datetime(1899, 12, 30)
        try:
            parsed = base + timedelta(days=int(value))
        except ValueError:
            return None
        return parsed.strftime("%Y-%m-%d")

    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            parsed = datetime.strptime(value, pattern)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_nullable_text(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    if not cleaned or cleaned in {"无", "無", "-"}:
        return None
    return cleaned


def _resolve_section_name(
    row: Dict[str, Any],
    section_column: str,
    header_columns: Tuple[str, ...],
    name_column: str,
) -> Optional[str]:
    merge_starts = row.get("_merge_starts") or {}

    if section_column in merge_starts:
        return _normalize_section_name(row.get(section_column))

    section_value = _clean_text(row.get(section_column))
    if section_value:
        return _normalize_section_name(section_value)

    if _clean_text(row.get(name_column)):
        return None

    for column in header_columns:
        header_value = _clean_text(row.get(column))
        if not header_value:
            continue
        if column in merge_starts or _looks_like_section_header(row, header_value, name_column, column):
            return _normalize_section_name(header_value)

    return None


def _looks_like_section_header(
    row: Dict[str, Any],
    header_value: str,
    name_column: str,
    header_column: str,
) -> bool:
    if not header_value or _clean_text(row.get(name_column)):
        return False

    for key, value in row.items():
        if key in {"_row_number", "_merge_starts", header_column}:
            continue
        if _clean_text(value):
            return False

    return True


def _normalize_section_name(value: Optional[str]) -> str:
    cleaned = _clean_text(value)
    return cleaned or UNGROUPED_SECTION


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None


def _checked(value: Optional[str]) -> bool:
    cleaned = _clean_text(value)
    return bool(cleaned and cleaned in CHECKMARKS)


def _build_source_text(title: str, blocks: Iterable[Tuple[str, Optional[str]]]) -> str:
    lines = [f"名称: {title}"]
    for label, value in blocks:
        cleaned = _clean_text(value)
        if cleaned:
            lines.append(f"{label}: {cleaned}")
    return "\n".join(lines)


def _record_status_label(record_kind: str, backlog_status: Optional[str]) -> str:
    if record_kind == "backlog":
        return backlog_status or "待办事项"
    return "正式菜谱"


def _count_labels(values: Iterable[Optional[str]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return [
        {"label": label, "value": counts[label]}
        for label in sorted(counts, key=lambda item: (-counts[item], item))
    ]


def _dedupe_source_keys(records: List[ParsedRecord]) -> None:
    counts: Dict[str, int] = {}
    for record in records:
        base_key = record.source_key
        occurrence = counts.get(base_key, 0) + 1
        counts[base_key] = occurrence
        if occurrence == 1:
            continue

        unique_key = f"{base_key}#{occurrence}"
        record.source_key = unique_key
        record.recipe_payload["source_key"] = unique_key
        record.source_hash_payload["source_key"] = unique_key


def _column_letters(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    return match.group(1) if match else reference


def _parse_range_reference(reference: str) -> Tuple[str, int, str, int]:
    if not reference:
        return "", 0, "", 0

    if ":" in reference:
        start_ref, end_ref = reference.split(":", 1)
    else:
        start_ref = end_ref = reference

    start_col, start_row = _parse_cell_reference(start_ref)
    end_col, end_row = _parse_cell_reference(end_ref)
    return start_col, start_row, end_col, end_row


def _parse_cell_reference(reference: str) -> Tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", reference or "")
    if not match:
        return "", 0
    return match.group(1), int(match.group(2))


def serialize_raw_payload(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)
