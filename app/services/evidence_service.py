import json
import math
import re
from pathlib import Path
from typing import Any


EVIDENCE_FILENAME = "evidence_chain.json"
_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
_DATE_OR_ORDINAL_UNITS = set("年月日号页行列个条项次季度")


def build_evidence_chain(
    *,
    job_dir: Path,
    explanation: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None = None,
    prediction_result: dict[str, Any] | None = None,
    chart_paths: list[str] | None = None,
) -> dict[str, Any]:
    report_data = report_data or _read_json_if_exists(job_dir / "report_data.json") or {}
    prediction_result = prediction_result or _read_json_if_exists(job_dir / "prediction_result.json") or {}
    sources = {
        "analysis_result.json": result_payload,
        "report_data.json": report_data,
    }
    if prediction_result:
        sources["prediction_result.json"] = prediction_result
    flattened = []
    for source_name, payload in sources.items():
        flattened.extend(_flatten_values(payload, source_name))

    findings = _collect_finding_texts(explanation)
    evidence_findings: list[dict[str, Any]] = []
    high_risk_count = 0
    for index, finding_text in enumerate(findings, start=1):
        numbers = _extract_numbers(finding_text)
        evidence_items = []
        for number in numbers:
            matches = _find_number_matches(number, flattened)
            evidence_items.extend(matches[:5])
        evidence_items = _dedupe_evidence_items(evidence_items)
        has_evidence = not numbers or bool(evidence_items)
        risk_level = "low" if has_evidence else "high"
        if risk_level == "high":
            high_risk_count += 1
        evidence_findings.append(
            {
                "finding_id": f"finding_{index}",
                "text": finding_text,
                "numbers": numbers,
                "has_evidence": has_evidence,
                "risk_level": risk_level,
                "evidence_items": evidence_items,
                "charts": chart_paths or [],
                "calculation_note": _calculation_note(numbers, evidence_items),
            }
        )

    chain = {
        "evidence_version": "1.0",
        "job_dir": str(job_dir),
        "evidence_chain_path": str(job_dir / EVIDENCE_FILENAME),
        "risk_level": "high" if high_risk_count else "low",
        "high_risk_count": high_risk_count,
        "source_files": [name for name, payload in sources.items() if payload],
        "findings": evidence_findings,
        "summary": "有结论数字未能在分析产物中找到证据。" if high_risk_count else "结论中的数字均可在分析产物中追溯，或该结论不含数字。",
    }
    _write_json(job_dir / EVIDENCE_FILENAME, chain)
    return chain


def merge_evidence_into_quality_review(quality_review: dict[str, Any], evidence_chain: dict[str, Any]) -> dict[str, Any]:
    review = dict(quality_review or {})
    issues = [item for item in review.get("issues", []) if isinstance(item, dict)] if isinstance(review.get("issues"), list) else []
    missing = [str(item) for item in review.get("missing_evidence", [])] if isinstance(review.get("missing_evidence"), list) else []
    checked_items = [item for item in review.get("checked_items", []) if isinstance(item, dict)] if isinstance(review.get("checked_items"), list) else []
    high_risk_findings = [item for item in evidence_chain.get("findings", []) if isinstance(item, dict) and item.get("risk_level") == "high"]
    if high_risk_findings:
        for finding in high_risk_findings:
            text = str(finding.get("text") or "")
            numbers = ", ".join(str(item.get("raw") if isinstance(item, dict) else item) for item in finding.get("numbers", []))
            issues.append(
                {
                    "issue_type": "missing_numeric_evidence",
                    "severity": "high",
                    "finding": f"结论中的数字未能在分析产物中找到证据：{text[:140]}",
                    "evidence": f"未匹配数字：{numbers or '-'}",
                    "suggestion": "请回到 analysis_result.json、prediction_result.json 或 report_data.json 中核对该数字，或改写为不含无法追溯数字的谨慎表述。",
                }
            )
            missing.append(text)
        checked_items.append({"name": "数字证据链", "status": "fail", "detail": f"{len(high_risk_findings)} 条发现缺少数字证据。"})
        review["risk_level"] = "high"
        review["passed"] = False
    else:
        checked_items.append({"name": "数字证据链", "status": "pass", "detail": "结论数字可以在分析产物中追溯。"})
        review.setdefault("risk_level", "low")
        review.setdefault("passed", True)
    review["issues"] = issues
    review["missing_evidence"] = _dedupe(missing)
    review["checked_items"] = checked_items
    review["evidence_chain_path"] = str((Path(str(evidence_chain.get("job_dir") or "")) / EVIDENCE_FILENAME)) if evidence_chain.get("job_dir") else None
    return review


def _collect_finding_texts(explanation: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    summary = explanation.get("summary")
    if isinstance(summary, str) and summary.strip():
        texts.append(summary.strip())
    for key in ("key_findings", "recommendations", "limitations"):
        value = explanation.get(key)
        if isinstance(value, list):
            for item in value:
                text = _item_to_text(item)
                if text:
                    texts.append(text)
    return _dedupe(texts)


def _item_to_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        pieces = []
        for key in ("title", "finding", "description", "insight", "text", "recommendation"):
            value = item.get(key)
            if value:
                pieces.append(str(value))
        return "：".join(pieces).strip()
    return str(item).strip() if item is not None else ""


def _extract_numbers(text: str) -> list[dict[str, Any]]:
    results = []
    for match in _NUMBER_PATTERN.finditer(text or ""):
        raw = match.group(0)
        is_percent = raw.endswith("%")
        if _should_skip_number_token(text, match.start(), match.end(), raw, is_percent):
            continue
        try:
            value = float(raw[:-1] if is_percent else raw)
        except ValueError:
            continue
        context = text[max(0, match.start() - 18): min(len(text), match.end() + 18)]
        results.append({"raw": raw, "value": value, "is_percent": is_percent, "context": context})
    return results


def _should_skip_number_token(text: str, start: int, end: int, raw: str, is_percent: bool) -> bool:
    if is_percent:
        return False

    previous_char = text[start - 1] if start > 0 else ""
    next_char = text[end] if end < len(text) else ""

    if next_char in _DATE_OR_ORDINAL_UNITS:
        return True
    if previous_char in {"第", "上", "下"} and next_char in _DATE_OR_ORDINAL_UNITS:
        return True
    if previous_char in {"-", "/", "－", "—"} or next_char in {"-", "/", "－", "—"}:
        return True
    if raw.startswith("-") and previous_char.isdigit():
        return True

    return False


def _find_number_matches(number: dict[str, Any], flattened: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = _number_targets(number)
    matches = []
    for item in flattened:
        numeric_value = item.get("numeric_value")
        if numeric_value is None:
            continue
        if any(_close(float(numeric_value), target) for target in targets):
            source_text = item.get("source_text")
            calculation = f"结论数字 {number.get('raw')} 与 {item.get('source_file')} 的 {item.get('json_path')} 匹配。"
            if source_text:
                calculation = f"{calculation} 来源文本：{source_text}"
            matches.append(
                {
                    "number": number.get("raw"),
                    "source_file": item.get("source_file"),
                    "json_path": item.get("json_path"),
                    "value": item.get("value"),
                    "row_context": item.get("row_context"),
                    "calculation": calculation,
                }
            )
    return matches


def _number_targets(number: dict[str, Any]) -> list[float]:
    value = float(number["value"])
    targets = [value]
    if number.get("is_percent"):
        targets.append(value / 100.0)
        targets.append(-value)
        targets.append(-value / 100.0)
        targets.append(abs(value))
        targets.append(abs(value) / 100.0)
        targets.append(-abs(value))
        targets.append(-abs(value) / 100.0)
    return _dedupe_float_targets(targets)


def _flatten_values(value: Any, source_file: str, path: str = "$", row_context: Any = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        next_row_context = value if _is_table_row(value) else row_context
        for key, child in value.items():
            rows.extend(_flatten_values(child, source_file, f"{path}.{key}", next_row_context))
        return rows
    if isinstance(value, list):
        for index, child in enumerate(value):
            next_row_context = child if isinstance(child, dict) and _is_table_row(child) else row_context
            rows.extend(_flatten_values(child, source_file, f"{path}[{index}]", next_row_context))
        return rows

    numeric_value = _coerce_number(value)
    rows.append(
        {
            "source_file": source_file,
            "json_path": path,
            "value": value,
            "numeric_value": numeric_value,
            "row_context": row_context,
        }
    )
    if numeric_value is None and isinstance(value, str):
        for index, number in enumerate(_extract_numbers(value)):
            rows.append(
                {
                    "source_file": source_file,
                    "json_path": f"{path}#number[{index}]",
                    "value": number.get("raw"),
                    "numeric_value": float(number["value"]),
                    "row_context": row_context,
                    "source_text": value,
                }
            )
    return rows


def _is_table_row(value: dict[str, Any]) -> bool:
    numeric_count = sum(1 for item in value.values() if _coerce_number(item) is not None)
    return len(value) >= 2 and numeric_count >= 1


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.endswith("%"):
            text = text[:-1]
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _close(left: float, right: float) -> bool:
    tolerance = max(1e-6, abs(right) * 0.001)
    return abs(left - right) <= tolerance


def _calculation_note(numbers: list[dict[str, Any]], evidence_items: list[dict[str, Any]]) -> str:
    if not numbers:
        return "该结论不含可抽取数字，依据为解释文本与图表整体判断。"
    if evidence_items:
        return "结论数字已通过递归扫描分析结果 JSON 找到匹配值。"
    return "结论含数字，但未在 analysis_result.json、prediction_result.json 或 report_data.json 中找到匹配值。"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (
            str(item.get("number")),
            str(item.get("source_file")),
            str(item.get("json_path")),
            str(item.get("value")),
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe_float_targets(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        if math.isfinite(float(value)) and not any(_close(float(value), existing) for existing in result):
            result.append(float(value))
    return result


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
