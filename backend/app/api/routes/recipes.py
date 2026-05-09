from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.recipe import RecipeEditorCreatePayload, RecipeEditorRowPayload, RecipeUpdatePayload
from app.services.excel_export_service import build_excel_bytes, normalize_filename
from app.services.recipe_service import (
    create_recipe_editor_row,
    export_recipes_rows,
    get_recipe,
    get_recipe_editor_schema,
    get_recipe_filters,
    list_recipe_editor_rows,
    list_recipes,
    update_recipe,
    update_recipe_editor_row,
)


router = APIRouter()


@router.get("/recipes")
def recipes(
    search: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    library_section: Optional[str] = Query(default=None),
    section_name: Optional[str] = Query(default=None),
    cuisine: Optional[str] = Query(default=None),
    ingredient: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    managed_tag: List[str] = Query(default=[]),
    bmd_only: bool = Query(default=False),
    cc_only: bool = Query(default=False),
):
    return {
        "items": list_recipes(
            search=search,
            status=status,
            library_section=library_section,
            section_name=section_name,
            cuisine=cuisine,
            ingredient=ingredient,
            tag=tag,
            managed_tags=managed_tag,
            bmd_only=bmd_only,
            cc_only=cc_only,
        )
    }


@router.get("/recipes/export")
def recipes_export(
    search: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    library_section: Optional[str] = Query(default=None),
    section_name: Optional[str] = Query(default=None),
    cuisine: Optional[str] = Query(default=None),
    ingredient: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    managed_tag: List[str] = Query(default=[]),
    bmd_only: bool = Query(default=False),
    cc_only: bool = Query(default=False),
):
    rows = export_recipes_rows(
        search=search,
        status=status,
        library_section=library_section,
        section_name=section_name,
        cuisine=cuisine,
        ingredient=ingredient,
        tag=tag,
        managed_tags=managed_tag,
        bmd_only=bmd_only,
        cc_only=cc_only,
    )
    headers = list(rows[0].keys()) if rows else ["菜名", "记录类型", "专题库", "分组", "菜系", "亚菜系", "标签", "食材", "调料", "做法及要点", "系统备注", "来源/修订备注", "最后记录日期", "BMD", "CC"]
    excel_bytes = build_excel_bytes(
        sheet_name="菜谱库导出",
        headers=headers,
        rows=[[row.get(header, "") for header in headers] for row in rows],
    )
    file_name = normalize_filename(f"recipes_{tag or library_section or 'export'}", "recipes_export")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/recipes/filters")
def recipe_filters():
    return get_recipe_filters()


@router.get("/recipes/editor/schema")
def recipe_editor_schema():
    return get_recipe_editor_schema()


@router.get("/recipes/editor/rows")
def recipe_editor_rows():
    return {"items": list_recipe_editor_rows()}


@router.post("/recipes/editor/rows")
def recipe_editor_create(payload: RecipeEditorCreatePayload):
    try:
        return create_recipe_editor_row(payload.values)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put("/recipes/editor/rows/{recipe_id}")
def recipe_editor_update(recipe_id: int, payload: RecipeEditorRowPayload):
    try:
        recipe = update_recipe_editor_row(recipe_id, payload.values)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.get("/recipes/{recipe_id}")
def recipe_detail(recipe_id: int):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.put("/recipes/{recipe_id}")
def recipe_update(recipe_id: int, payload: RecipeUpdatePayload):
    try:
        recipe = update_recipe(recipe_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe
