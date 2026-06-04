import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, status

from app.services.dataset_reader import (
    find_dataset_file,
    find_original_dataset_file,
    get_dataset_dir,
    get_uploaded_asset_type,
    read_dataset,
)


PLAN_FILENAME = "cleaning_plan.json"
CLEANED_DATASET_FILENAME = "cleaned_dataset.csv"
REPORT_FILENAME = "cleaning_report.json"
PREVIEW_LIMIT = 30


class CleaningStrategy:
    KEEP = "keep"
    FILL_MEDIAN = "fill_median"
    FILL_MODE = "fill_mode"
    DROP_ROWS = "drop_rows"
    DROP_DUPLICATES = "drop_duplicates"
    PARSE_DATE = "parse_date"
    NORMALIZE_PERCENT_DECIMAL = "normalize_percent_decimal"
    NORMALIZE_UNIT_NUMBER = "normalize_unit_number"
    NORMALIZE_ENUM = "normalize_enum"
    CONVERT_NUMERIC = "convert_numeric"
    CAP_OUTLIER_IQR = "cap_outlier_iqr"
    MANUAL_REVIEW = "manual_review"


def build_cleaning_plan(dataset_id: str) -> dict[str, Any]:
    dataset_dir = get_dataset_dir(dataset_id)
    asset_type = get_uploaded_asset_type(dataset_id)
    if asset_type == "image" and not (dataset_dir / "visual_extracted.csv").exists():
        plan = _image_waiting_plan(dataset_id, dataset_dir)
        _write_json(dataset_dir / PLAN_FILENAME, plan)
        return plan

    source_path = find_original_dataset_file(dataset_dir)
    df = read_dataset(source_path)
    issues = _detect_issues(df)
    plan = {
        "dataset_id": dataset_id,
        "asset_type": asset_type,
        "source_file": str(source_path),
        "plan_path": str(dataset_dir / PLAN_FILENAME),
        "created_at": _utc_now(),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(column) for column in df.columns],
        "has_issues": bool(issues),
        "issues": issues,
        "recommended_strategy_ids": {
            str(issue["issue_id"]): str(issue.get("default_strategy_id") or CleaningStrategy.KEEP)
            for issue in issues
        },
        "preview": _preview_payload(df),
        "message": "检测到可修复的数据质量问题，请确认处理策略。" if issues else "当前数据文件未检测到需要自动修复的问题，可以继续分析。",
    }
    _write_json(dataset_dir / PLAN_FILENAME, plan)
    return plan


def apply_cleaning_plan(dataset_id: str, selected_strategies: dict[str, str] | list[dict[str, Any]] | None = None) -> dict[str, Any]:
    dataset_dir = get_dataset_dir(dataset_id)
    plan = _read_json_if_exists(dataset_dir / PLAN_FILENAME) or build_cleaning_plan(dataset_id)
    source_path = Path(str(plan.get("source_file") or ""))
    if not source_path.exists():
        source_path = find_original_dataset_file(dataset_dir)
    df = read_dataset(source_path)
    before_rows = int(len(df))
    before_columns = int(len(df.columns))
    strategy_map = _normalize_selected_strategies(selected_strategies, plan)
    applied: list[dict[str, Any]] = []

    for issue in plan.get("issues", []):
        if not isinstance(issue, dict):
            continue
        issue_id = str(issue.get("issue_id") or "")
        strategy_id = str(strategy_map.get(issue_id) or issue.get("default_strategy_id") or CleaningStrategy.KEEP)
        before_shape = [int(len(df)), int(len(df.columns))]
        df, operation = _apply_issue_strategy(df, issue, strategy_id)
        after_shape = [int(len(df)), int(len(df.columns))]
        applied.append(
            {
                "issue_id": issue_id,
                "issue_type": issue.get("issue_type"),
                "column": issue.get("column"),
                "strategy_id": strategy_id,
                "strategy_label": _strategy_label(issue, strategy_id),
                "description": operation,
                "rows_before": before_shape[0],
                "rows_after": after_shape[0],
                "columns_before": before_shape[1],
                "columns_after": after_shape[1],
            }
        )

    cleaned_path = dataset_dir / CLEANED_DATASET_FILENAME
    df.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    report = {
        "dataset_id": dataset_id,
        "source_file": str(source_path),
        "cleaned_dataset_path": str(cleaned_path),
        "cleaning_report_path": str(dataset_dir / REPORT_FILENAME),
        "created_at": _utc_now(),
        "row_count_before": before_rows,
        "row_count_after": int(len(df)),
        "column_count_before": before_columns,
        "column_count_after": int(len(df.columns)),
        "applied_strategies": applied,
        "preview": _preview_payload(df),
        "message": "已生成清洗后的数据集，后续分析将基于该版本执行。" if applied else "数据未做自动修改，后续分析将继续使用当前数据。",
    }
    _write_json(dataset_dir / REPORT_FILENAME, report)
    return report


def get_cleaning_report(dataset_id: str) -> dict[str, Any]:
    dataset_dir = get_dataset_dir(dataset_id)
    report = _read_json_if_exists(dataset_dir / REPORT_FILENAME)
    if report:
        return report
    plan = _read_json_if_exists(dataset_dir / PLAN_FILENAME) or build_cleaning_plan(dataset_id)
    return {
        "dataset_id": dataset_id,
        "source_file": plan.get("source_file"),
        "cleaned_dataset_path": None,
        "cleaning_report_path": str(dataset_dir / REPORT_FILENAME),
        "created_at": _utc_now(),
        "row_count_before": plan.get("row_count", 0),
        "row_count_after": plan.get("row_count", 0),
        "column_count_before": plan.get("column_count", 0),
        "column_count_after": plan.get("column_count", 0),
        "applied_strategies": [],
        "preview": plan.get("preview", {"columns": [], "rows": []}),
        "message": "尚未应用清洗策略。",
    }


def _detect_issues(df: pd.DataFrame) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issue_index = 1

    for column in df.columns:
        series = df[column]
        missing_count = int(series.isna().sum())
        if missing_count:
            numeric = pd.api.types.is_numeric_dtype(series)
            default_strategy = CleaningStrategy.FILL_MEDIAN if numeric else CleaningStrategy.FILL_MODE
            strategies = [
                _strategy(CleaningStrategy.KEEP, "保留并说明限制", "不改动该列，报告中提示缺失值限制。"),
                _strategy(CleaningStrategy.DROP_ROWS, "删除该行", "删除该字段为空的记录。"),
                _strategy(CleaningStrategy.MANUAL_REVIEW, "手动修改", "暂不自动处理，导出后由人工修正。"),
            ]
            if numeric:
                strategies.insert(1, _strategy(CleaningStrategy.FILL_MEDIAN, "按中位数填充", "用该列中位数填充缺失值。", True))
            else:
                strategies.insert(1, _strategy(CleaningStrategy.FILL_MODE, "按众数填充", "用该列最常见值填充缺失值。", True))
            issues.append(_issue(
                issue_index,
                "missing_values",
                column,
                f"检测到“{column}”列有 {missing_count} 个空值。",
                missing_count,
                strategies,
                default_strategy,
                severity="medium" if missing_count / max(len(df), 1) >= 0.1 else "low",
            ))
            issue_index += 1

    duplicate_count = int(df.duplicated().sum())
    if duplicate_count:
        issues.append(_issue(
            issue_index,
            "duplicate_rows",
            None,
            f"检测到 {duplicate_count} 行完全重复记录。",
            duplicate_count,
            [
                _strategy(CleaningStrategy.KEEP, "保留重复行", "不自动删除重复记录。"),
                _strategy(CleaningStrategy.DROP_DUPLICATES, "删除重复行", "保留第一条记录，删除完全重复行。", True),
                _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "导出后人工确认重复记录是否为真实业务记录。"),
            ],
            CleaningStrategy.DROP_DUPLICATES,
            severity="medium",
        ))
        issue_index += 1

    for column in df.columns:
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            outlier_count = _iqr_outlier_count(series)
            if outlier_count:
                issues.append(_issue(
                    issue_index,
                    "outliers",
                    column,
                    f"检测到“{column}”列有 {outlier_count} 个可能异常值。",
                    outlier_count,
                    [
                        _strategy(CleaningStrategy.KEEP, "保留异常值", "保留原值，并在报告中说明存在异常点。", True),
                        _strategy(CleaningStrategy.CAP_OUTLIER_IQR, "按 IQR 边界截尾", "把低于/高于 IQR 合理边界的值限制在边界内。"),
                        _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "由人工确认异常值是否为录入错误。"),
                    ],
                    CleaningStrategy.KEEP,
                    severity="low",
                ))
                issue_index += 1
            continue

        text_series = series.dropna().astype(str).str.strip()
        if text_series.empty:
            continue

        numeric_ratio = _numeric_parse_ratio(text_series)
        if numeric_ratio >= 0.75:
            issues.append(_issue(
                issue_index,
                "type_correction",
                column,
                f"“{column}”列大部分值可解析为数字，建议纠正字段类型。",
                int(round(len(text_series) * numeric_ratio)),
                [
                    _strategy(CleaningStrategy.KEEP, "保留文本类型", "不自动转换字段类型。"),
                    _strategy(CleaningStrategy.CONVERT_NUMERIC, "转换为数值", "去除千分位和空格后转换为数值。", True),
                    _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "人工确认是否所有值都应为数值。"),
                ],
                CleaningStrategy.CONVERT_NUMERIC,
            ))
            issue_index += 1

        percent_ratio = _percent_ratio(text_series)
        if percent_ratio >= 0.2:
            issues.append(_issue(
                issue_index,
                "percent_decimal",
                column,
                f"“{column}”列存在百分比与小数口径混用的风险。",
                int(round(len(text_series) * percent_ratio)),
                [
                    _strategy(CleaningStrategy.KEEP, "保留原格式", "不自动统一百分比口径。"),
                    _strategy(CleaningStrategy.NORMALIZE_PERCENT_DECIMAL, "统一为小数", "将 5% 转成 0.05，并把疑似百分数统一到小数口径。", True),
                    _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "人工确认该列实际口径。"),
                ],
                CleaningStrategy.NORMALIZE_PERCENT_DECIMAL,
            ))
            issue_index += 1

        date_ratio = _date_parse_ratio(text_series)
        if date_ratio >= 0.65:
            issues.append(_issue(
                issue_index,
                "date_format",
                column,
                f"“{column}”列大部分值可解析为日期，建议统一日期格式。",
                int(round(len(text_series) * date_ratio)),
                [
                    _strategy(CleaningStrategy.KEEP, "保留原日期文本", "不自动修改日期格式。"),
                    _strategy(CleaningStrategy.PARSE_DATE, "统一为 YYYY-MM-DD", "将可解析日期统一为标准日期文本。", True),
                    _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "人工核对无法解析或歧义日期。"),
                ],
                CleaningStrategy.PARSE_DATE,
            ))
            issue_index += 1

        unit_ratio = _unit_ratio(text_series)
        if unit_ratio >= 0.25:
            issues.append(_issue(
                issue_index,
                "unit_conversion",
                column,
                f"“{column}”列存在数值和单位混写，建议抽取为统一数值。",
                int(round(len(text_series) * unit_ratio)),
                [
                    _strategy(CleaningStrategy.KEEP, "保留原单位文本", "不自动换算单位。"),
                    _strategy(CleaningStrategy.NORMALIZE_UNIT_NUMBER, "抽取统一数值", "识别常见单位并换算为基础数值。", True),
                    _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "由人工确认单位含义和换算口径。"),
                ],
                CleaningStrategy.NORMALIZE_UNIT_NUMBER,
            ))
            issue_index += 1

        normalized_unique = text_series.str.lower().str.replace(r"\s+", "", regex=True).nunique(dropna=True)
        raw_unique = text_series.nunique(dropna=True)
        if 1 < normalized_unique < raw_unique and raw_unique <= 50:
            issues.append(_issue(
                issue_index,
                "text_enum_normalization",
                column,
                f"“{column}”列存在大小写、空格或全半角差异造成的枚举不一致。",
                raw_unique - normalized_unique,
                [
                    _strategy(CleaningStrategy.KEEP, "保留原枚举", "不自动归一化文本枚举。"),
                    _strategy(CleaningStrategy.NORMALIZE_ENUM, "统一文本枚举", "去除首尾空格并按忽略大小写后的主写法归一。", True),
                    _strategy(CleaningStrategy.MANUAL_REVIEW, "手动核对", "人工确认枚举合并规则。"),
                ],
                CleaningStrategy.NORMALIZE_ENUM,
            ))
            issue_index += 1

    return issues


def _apply_issue_strategy(df: pd.DataFrame, issue: dict[str, Any], strategy_id: str) -> tuple[pd.DataFrame, str]:
    column = issue.get("column")
    issue_type = str(issue.get("issue_type") or "")
    if strategy_id in {CleaningStrategy.KEEP, CleaningStrategy.MANUAL_REVIEW}:
        return df, "未自动修改，保留原始数据并在报告中说明限制。"

    if issue_type == "missing_values" and column in df.columns:
        if strategy_id == CleaningStrategy.DROP_ROWS:
            return df[df[column].notna()].copy(), f"已删除“{column}”为空的记录。"
        if strategy_id == CleaningStrategy.FILL_MEDIAN:
            numeric = pd.to_numeric(df[column], errors="coerce")
            median = numeric.median()
            next_df = df.copy()
            next_df[column] = numeric.fillna(median)
            return next_df, f"已用中位数 {median} 填充“{column}”缺失值。"
        if strategy_id == CleaningStrategy.FILL_MODE:
            next_df = df.copy()
            mode = next_df[column].mode(dropna=True)
            fill_value = mode.iloc[0] if not mode.empty else ""
            next_df[column] = next_df[column].fillna(fill_value)
            return next_df, f"已用众数“{fill_value}”填充“{column}”缺失值。"

    if issue_type == "duplicate_rows" and strategy_id == CleaningStrategy.DROP_DUPLICATES:
        return df.drop_duplicates().copy(), "已删除完全重复行。"

    if issue_type == "date_format" and column in df.columns and strategy_id == CleaningStrategy.PARSE_DATE:
        next_df = df.copy()
        parsed = pd.to_datetime(next_df[column], errors="coerce")
        next_df[column] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), next_df[column])
        return next_df, f"已将“{column}”中可解析日期统一为 YYYY-MM-DD。"

    if issue_type == "percent_decimal" and column in df.columns and strategy_id == CleaningStrategy.NORMALIZE_PERCENT_DECIMAL:
        next_df = df.copy()
        next_df[column] = next_df[column].map(_parse_percent_decimal)
        return next_df, f"已将“{column}”统一为小数口径。"

    if issue_type == "unit_conversion" and column in df.columns and strategy_id == CleaningStrategy.NORMALIZE_UNIT_NUMBER:
        next_df = df.copy()
        next_df[column] = next_df[column].map(_parse_unit_number)
        return next_df, f"已将“{column}”中的常见单位文本抽取为统一数值。"

    if issue_type == "text_enum_normalization" and column in df.columns and strategy_id == CleaningStrategy.NORMALIZE_ENUM:
        next_df = df.copy()
        next_df[column] = _normalize_enum_series(next_df[column])
        return next_df, f"已归一化“{column}”的文本枚举。"

    if issue_type == "type_correction" and column in df.columns and strategy_id == CleaningStrategy.CONVERT_NUMERIC:
        next_df = df.copy()
        next_df[column] = pd.to_numeric(next_df[column].astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
        return next_df, f"已将“{column}”转换为数值字段。"

    if issue_type == "outliers" and column in df.columns and strategy_id == CleaningStrategy.CAP_OUTLIER_IQR:
        numeric = pd.to_numeric(df[column], errors="coerce")
        q1 = numeric.quantile(0.25)
        q3 = numeric.quantile(0.75)
        iqr = q3 - q1
        if pd.isna(iqr) or iqr == 0:
            return df, "异常值截尾未执行，因为该列缺少有效分位数。"
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        next_df = df.copy()
        next_df[column] = numeric.clip(lower, upper)
        return next_df, f"已按 IQR 边界 [{lower}, {upper}] 截尾“{column}”。"

    return df, "所选策略未触发自动修改。"


def _strategy_label(issue: dict[str, Any], strategy_id: str) -> str:
    for strategy in issue.get("strategies", []):
        if isinstance(strategy, dict) and strategy.get("strategy_id") == strategy_id:
            return str(strategy.get("label") or strategy_id)
    return strategy_id


def _normalize_selected_strategies(selected: dict[str, str] | list[dict[str, Any]] | None, plan: dict[str, Any]) -> dict[str, str]:
    defaults = {
        str(issue.get("issue_id")): str(issue.get("default_strategy_id") or CleaningStrategy.KEEP)
        for issue in plan.get("issues", [])
        if isinstance(issue, dict) and issue.get("issue_id")
    }
    if isinstance(selected, dict):
        return {**defaults, **{str(k): str(v) for k, v in selected.items()}}
    if isinstance(selected, list):
        updates = {}
        for item in selected:
            if isinstance(item, dict) and item.get("issue_id") and item.get("strategy_id"):
                updates[str(item["issue_id"])] = str(item["strategy_id"])
        return {**defaults, **updates}
    return defaults


def _preview_payload(df: pd.DataFrame) -> dict[str, Any]:
    safe = df.head(PREVIEW_LIMIT).where(pd.notna(df.head(PREVIEW_LIMIT)), None)
    return {
        "columns": [str(column) for column in safe.columns],
        "rows": safe.to_dict(orient="records"),
        "row_limit": PREVIEW_LIMIT,
    }


def _issue(
    index: int,
    issue_type: str,
    column: Any,
    message: str,
    detected_count: int,
    strategies: list[dict[str, Any]],
    default_strategy_id: str,
    severity: str = "low",
) -> dict[str, Any]:
    return {
        "issue_id": f"issue_{index}",
        "issue_type": issue_type,
        "column": str(column) if column is not None else None,
        "message": message,
        "detected_count": int(detected_count),
        "severity": severity,
        "strategies": strategies,
        "default_strategy_id": default_strategy_id,
    }


def _strategy(strategy_id: str, label: str, description: str, recommended: bool = False) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "label": label,
        "description": description,
        "recommended": recommended,
    }


def _iqr_outlier_count(series: pd.Series) -> int:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 8:
        return 0
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if not math.isfinite(float(iqr)) or iqr <= 0:
        return 0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((numeric < lower) | (numeric > upper)).sum())


def _numeric_parse_ratio(series: pd.Series) -> float:
    parsed = pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
    return float(parsed.notna().mean()) if len(series) else 0.0


def _percent_ratio(series: pd.Series) -> float:
    return float(series.astype(str).str.contains("%", regex=False).mean()) if len(series) else 0.0


def _date_parse_ratio(series: pd.Series) -> float:
    parsed = pd.to_datetime(series, errors="coerce")
    return float(parsed.notna().mean()) if len(series) else 0.0


def _unit_ratio(series: pd.Series) -> float:
    pattern = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*(kg|g|公斤|克|元|万元|k|m|cm|米|公里|km)\s*$", re.I)
    return float(series.astype(str).map(lambda value: bool(pattern.match(value))).mean()) if len(series) else 0.0


def _parse_percent_decimal(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("%"):
            return float(text[:-1].strip()) / 100.0
        number = float(text.replace(",", ""))
        return number / 100.0 if abs(number) > 1 else number
    except ValueError:
        return value


def _parse_unit_number(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    match = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*([\w\u4e00-\u9fff]+)?$", text)
    if not match:
        return value
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    factors = {
        "g": 0.001,
        "克": 0.001,
        "kg": 1.0,
        "公斤": 1.0,
        "万元": 10000.0,
        "元": 1.0,
        "cm": 0.01,
        "m": 1.0,
        "米": 1.0,
        "km": 1000.0,
        "公里": 1000.0,
    }
    return number * factors.get(unit, 1.0)


def _normalize_enum_series(series: pd.Series) -> pd.Series:
    canonical: dict[str, str] = {}
    result = []
    for value in series:
        if pd.isna(value):
            result.append(value)
            continue
        text = str(value).strip()
        key = re.sub(r"\s+", "", text).lower()
        canonical.setdefault(key, text)
        result.append(canonical[key])
    return pd.Series(result, index=series.index)


def _image_waiting_plan(dataset_id: str, dataset_dir: Path) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "asset_type": "image",
        "source_file": None,
        "plan_path": str(dataset_dir / PLAN_FILENAME),
        "created_at": _utc_now(),
        "row_count": 0,
        "column_count": 0,
        "columns": [],
        "has_issues": False,
        "issues": [],
        "recommended_strategy_ids": {},
        "preview": {"columns": [], "rows": [], "row_limit": PREVIEW_LIMIT},
        "message": "图片将在视觉解析后生成结构化数据；当前没有可直接清洗的表格内容。",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
