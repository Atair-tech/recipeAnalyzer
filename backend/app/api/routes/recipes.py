from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.recipe import (
    RecipeEditorCreatePayload,
    RecipeEditorRowPayload,
    RecipeUpdatePayload,
    TableEditorApplyPayload,
    TableEditorRowsPayload,
    TableEditorSqlPayload,
    UserViewFilterValuesPayload,
    UserViewRowsPayload,
)
from app.services.excel_export_service import build_excel_bytes, normalize_filename
from app.services.recipe_service import (
    apply_table_editor_changes,
    create_recipe_editor_row,
    execute_table_editor_sql,
    export_recipes_rows,
    get_recipe,
    get_recipe_editor_schema,
    get_table_editor_schema,
    get_recipe_filters,
    get_user_view_editor_schema,
    list_user_view_filter_values,
    list_table_editor_rows,
    list_recipe_editor_rows,
    list_recipes,
    list_user_view_editor_rows,
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


@router.get("/recipes/editor/tables")
def recipe_editor_tables():
    return get_table_editor_schema()


@router.post("/recipes/editor/table-rows")
def recipe_editor_table_rows(payload: TableEditorRowsPayload):
    try:
        return list_table_editor_rows(
            table=payload.table,
            filters=payload.filters,
            limit=payload.limit,
            offset=payload.offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recipes/editor/user-views")
def recipe_editor_user_views():
    return get_user_view_editor_schema()


@router.post("/recipes/editor/user-view-rows")
def recipe_editor_user_view_rows(payload: UserViewRowsPayload):
    try:
        return list_user_view_editor_rows(
            view=payload.view,
            filters=payload.filters,
            limit=payload.limit,
            offset=payload.offset,
            sort_column=payload.sort_column,
            sort_direction=payload.sort_direction,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/recipes/editor/user-view-filter-values")
def recipe_editor_user_view_filter_values(payload: UserViewFilterValuesPayload):
    try:
        return list_user_view_filter_values(
            view=payload.view,
            column=payload.column,
            filters=payload.filters,
            search=payload.search,
            limit=payload.limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/recipes/editor/sql")
def recipe_editor_sql(payload: TableEditorSqlPayload):
    try:
        return execute_table_editor_sql(payload.sql)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"SQL 执行失败：{error}") from error


@router.post("/recipes/editor/apply")
def recipe_editor_apply(payload: TableEditorApplyPayload):
    try:
        return apply_table_editor_changes(payload.table, payload.changes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"写入更改失败：{error}") from error


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
