from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


DEFAULT_INSIGHT_GOAL = "智能洞察挖掘：系统自动扫描数据，挖掘潜在规律和高价值异常，无需用户预设目标。"


@dataclass
class InsightCandidate:
    title: str
    description: str
    insight_type: str
    score: float
    confidence: float
    evidence: dict[str, Any]
    recommendations: list[str]
    limitations: list[str]
    metric: str | None = None
    dimension: str | None = None

    def to_dict(self, index: int) -> dict[str, Any]:
        score = max(0.0, min(float(self.score), 100.0))
        confidence = max(0.0, min(float(self.confidence), 1.0))
        return {
            "id": f"insight_{index:03d}",
            "title": self.title,
            "description": self.description,
            "type": self.insight_type,
            "score": round(score, 2),
            "confidence": round(confidence, 3),
            "metric": self.metric,
            "dimension": self.dimension,
            "evidence": self.evidence,
            "recommendations": self.recommendations,
            "limitations": self.limitations,
        }


class InsightMiningAgent:
    """Rule-based statistical and pattern mining agent.

    It intentionally does not rely on a user question. It scans tabular data for high-value
    signals, ranks candidates by effect size, coverage and confidence, and returns a compact
    insight report that can be consumed by the existing report/explanation UI.
    """

    def mine(
        self,
        dataframe: pd.DataFrame,
        dataset_profile: dict[str, Any] | None = None,
        user_goal: str | None = None,
        max_insights: int = 12,
    ) -> dict[str, Any]:
        df = self._prepare_dataframe(dataframe)
        profile = dataset_profile or {}
        row_count = int(len(df))
        column_count = int(len(df.columns))
        numeric_cols = self._numeric_columns(df, profile)
        date_cols = self._date_columns(df, profile)
        categorical_cols = self._categorical_columns(df, numeric_cols, date_cols)

        candidates: list[InsightCandidate] = []
        candidates.extend(self._mine_weekday_patterns(df, date_cols, numeric_cols))
        candidates.extend(self._mine_group_metric_patterns(df, categorical_cols, numeric_cols))
        candidates.extend(self._mine_time_trends(df, date_cols, numeric_cols, categorical_cols))
        candidates.extend(self._mine_correlations(df, numeric_cols))
        candidates.extend(self._mine_cooccurrence_patterns(df, date_cols, categorical_cols))
        candidates.extend(self._mine_quality_patterns(df))

        ranked = self._rank_candidates(candidates)[: max(1, max_insights)]
        insights = [candidate.to_dict(index + 1) for index, candidate in enumerate(ranked)]

        summary = self._summary(insights, row_count, column_count)
        return {
            "success": True,
            "task_type": "insight_mining",
            "analysis_type": "insight_mining",
            "user_goal": user_goal or DEFAULT_INSIGHT_GOAL,
            "rows": row_count,
            "columns": column_count,
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "date_columns": date_cols,
            "summary": summary,
            "insights": insights,
            "top_insights": insights[:5],
            "charts": [],
            "limitations": self._global_limitations(row_count, column_count, insights),
            "methodology": [
                "自动识别日期、数值、类别、客户与商品字段。",
                "对时间、分组、相关性、缺失率、异常值和简单序列购买模式进行批量扫描。",
                "基于效应大小、样本覆盖、分组稳定性和可解释性进行 0-100 分排序。",
                "默认输出相关信号和可验证规律，不把观察性数据直接表述为确定因果。",
            ],
        }

    def _prepare_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        df = dataframe.copy()
        df.columns = [str(col).strip() for col in df.columns]
        for col in df.columns:
            if pd.api.types.is_object_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None, "": None})
        return df

    def _numeric_columns(self, df: pd.DataFrame, profile: dict[str, Any]) -> list[str]:
        numeric_summary = profile.get("numeric_summary") if isinstance(profile.get("numeric_summary"), dict) else {}
        candidates = [col for col in df.columns if col in numeric_summary]
        for col in df.columns:
            if col in candidates:
                continue
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= max(3, len(df) * 0.5):
                candidates.append(col)
                df[col] = converted
        return [col for col in candidates if col in df.columns and pd.to_numeric(df[col], errors="coerce").notna().sum() >= 3]

    def _date_columns(self, df: pd.DataFrame, profile: dict[str, Any]) -> list[str]:
        name_hints = ("date", "day", "time", "month", "year", "日期", "时间", "月份", "年月", "下单", "订单")
        profile_dtypes = profile.get("dtypes") if isinstance(profile.get("dtypes"), dict) else {}
        result: list[str] = []
        for col in df.columns:
            col_lower = col.lower()
            hinted = any(hint in col_lower or hint in col for hint in name_hints)
            dtype_text = str(profile_dtypes.get(col) or "").lower()
            if not hinted and "datetime" not in dtype_text:
                continue
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() >= max(3, len(df) * 0.3):
                df[col] = parsed
                result.append(col)
        return result

    def _categorical_columns(self, df: pd.DataFrame, numeric_cols: list[str], date_cols: list[str]) -> list[str]:
        excluded = set(numeric_cols) | set(date_cols)
        result: list[str] = []
        n = max(1, len(df))
        for col in df.columns:
            if col in excluded:
                continue
            non_null = df[col].dropna()
            unique_count = int(non_null.nunique()) if not non_null.empty else 0
            if 2 <= unique_count <= min(80, max(12, int(n * 0.6))):
                result.append(col)
        return result

    def _mine_weekday_patterns(self, df: pd.DataFrame, date_cols: list[str], numeric_cols: list[str]) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        for date_col in date_cols[:2]:
            parsed = pd.to_datetime(df[date_col], errors="coerce")
            if parsed.notna().sum() < 7:
                continue
            is_weekend = parsed.dt.dayofweek >= 5
            for metric in numeric_cols[:8]:
                values = pd.to_numeric(df[metric], errors="coerce")
                sample = pd.DataFrame({"weekend": is_weekend, "value": values}).dropna()
                if len(sample) < 8 or sample["weekend"].nunique() < 2:
                    continue
                weekend_n = int(sample["weekend"].sum())
                workday_n = int((~sample["weekend"]).sum())
                if weekend_n < 2 or workday_n < 2:
                    continue
                weekend_mean = float(sample.loc[sample["weekend"], "value"].mean())
                workday_mean = float(sample.loc[~sample["weekend"], "value"].mean())
                if not self._valid_pair(weekend_mean, workday_mean):
                    continue
                delta_pct = self._pct_change(weekend_mean, workday_mean)
                if abs(delta_pct) < 8:
                    continue
                direction = "高" if delta_pct > 0 else "低"
                effect = min(abs(delta_pct), 200.0) / 2
                confidence = self._confidence_from_counts([weekend_n, workday_n], sample["value"].std())
                candidates.append(
                    InsightCandidate(
                        title=f"{metric} 在周末比工作日{direction} {abs(delta_pct):.1f}%",
                        description=f"以 {date_col} 判断周末，{metric} 周末均值为 {weekend_mean:.3g}，工作日均值为 {workday_mean:.3g}，差异约 {delta_pct:+.1f}% 。",
                        insight_type="calendar_pattern",
                        score=effect * confidence + 18,
                        confidence=confidence,
                        metric=metric,
                        dimension=date_col,
                        evidence={
                            "date_column": date_col,
                            "weekend_mean": round(weekend_mean, 4),
                            "workday_mean": round(workday_mean, 4),
                            "delta_pct": round(delta_pct, 2),
                            "weekend_n": weekend_n,
                            "workday_n": workday_n,
                        },
                        recommendations=["核对周末促销、门店客流或线上投放排期，判断该规律是否可被运营放大。"],
                        limitations=["该洞察来自观察性数据，尚未排除节假日、促销和渠道组合差异。"],
                    )
                )
        return candidates

    def _mine_group_metric_patterns(self, df: pd.DataFrame, categorical_cols: list[str], numeric_cols: list[str]) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        min_group_count = max(2, min(5, int(len(df) * 0.03)))
        for dimension in categorical_cols[:10]:
            for metric in numeric_cols[:10]:
                temp = pd.DataFrame({dimension: df[dimension], metric: pd.to_numeric(df[metric], errors="coerce")}).dropna()
                if len(temp) < 8:
                    continue
                grouped = temp.groupby(dimension)[metric].agg(["mean", "count", "sum"]).reset_index()
                grouped = grouped[grouped["count"] >= min_group_count]
                if len(grouped) < 2:
                    continue
                grouped = grouped.sort_values("mean", ascending=False)
                top = grouped.iloc[0]
                bottom = grouped.iloc[-1]
                top_mean = float(top["mean"])
                bottom_mean = float(bottom["mean"])
                if not self._valid_pair(top_mean, bottom_mean):
                    continue
                delta_pct = self._pct_change(top_mean, bottom_mean)
                if abs(delta_pct) < 12:
                    continue
                top_group = str(top[dimension])
                bottom_group = str(bottom[dimension])
                coverage = float(grouped["count"].sum()) / max(1, len(df))
                confidence = self._confidence_from_counts(grouped["count"].tolist(), temp[metric].std()) * min(1.0, coverage + 0.25)
                score = min(abs(delta_pct), 250.0) * 0.28 * confidence + 22
                candidates.append(
                    InsightCandidate(
                        title=f"{dimension}={top_group} 的 {metric} 均值最高，比 {bottom_group} 高 {abs(delta_pct):.1f}%",
                        description=f"按 {dimension} 分组后，{top_group} 的 {metric} 平均值为 {top_mean:.3g}，{bottom_group} 为 {bottom_mean:.3g}，形成明显分层。",
                        insight_type="segment_difference",
                        score=score,
                        confidence=confidence,
                        metric=metric,
                        dimension=dimension,
                        evidence={
                            "dimension": dimension,
                            "metric": metric,
                            "top_group": top_group,
                            "top_mean": round(top_mean, 4),
                            "top_count": int(top["count"]),
                            "bottom_group": bottom_group,
                            "bottom_mean": round(bottom_mean, 4),
                            "bottom_count": int(bottom["count"]),
                            "delta_pct": round(delta_pct, 2),
                            "group_count": int(len(grouped)),
                            "coverage": round(coverage, 4),
                        },
                        recommendations=[f"把 {dimension}={top_group} 的定价、渠道、活动或用户结构与低表现分组对比，提炼可复制策略。"],
                        limitations=["分组差异可能受到样本结构、促销周期或其他维度共同影响，需进一步交叉验证。"],
                    )
                )
        return candidates

    def _mine_time_trends(
        self,
        df: pd.DataFrame,
        date_cols: list[str],
        numeric_cols: list[str],
        categorical_cols: list[str],
    ) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        for date_col in date_cols[:2]:
            parsed = pd.to_datetime(df[date_col], errors="coerce")
            if parsed.notna().sum() < 6:
                continue
            period = parsed.dt.to_period("M").astype(str)
            for metric in numeric_cols[:10]:
                values = pd.to_numeric(df[metric], errors="coerce")
                monthly = pd.DataFrame({"period": period, "value": values}).dropna().groupby("period")["value"].sum().sort_index()
                if len(monthly) < 3:
                    continue
                first = float(monthly.iloc[0])
                last = float(monthly.iloc[-1])
                if not self._valid_pair(last, first):
                    continue
                delta_pct = self._pct_change(last, first)
                if abs(delta_pct) < 15:
                    continue
                direction = "上升" if delta_pct > 0 else "下降"
                confidence = min(0.95, 0.45 + len(monthly) / 12 + math.log1p(len(df)) / 25)
                candidates.append(
                    InsightCandidate(
                        title=f"{metric} 从 {monthly.index[0]} 到 {monthly.index[-1]} {direction} {abs(delta_pct):.1f}%",
                        description=f"按月汇总后，{metric} 从 {first:.3g} 变化到 {last:.3g}，整体呈{direction}信号。",
                        insight_type="trend_change",
                        score=min(abs(delta_pct), 220.0) * 0.32 * confidence + 20,
                        confidence=confidence,
                        metric=metric,
                        dimension=date_col,
                        evidence={
                            "date_column": date_col,
                            "metric": metric,
                            "start_period": str(monthly.index[0]),
                            "end_period": str(monthly.index[-1]),
                            "start_value": round(first, 4),
                            "end_value": round(last, 4),
                            "delta_pct": round(delta_pct, 2),
                            "period_count": int(len(monthly)),
                        },
                        recommendations=["结合活动、价格、库存、节假日和渠道变更，拆解趋势变化的贡献来源。"],
                        limitations=["时间跨度较短时，趋势可能受单月波动影响，不宜直接外推。"],
                    )
                )

            if categorical_cols:
                dimension = categorical_cols[0]
                for metric in numeric_cols[:5]:
                    temp = pd.DataFrame({"period": period, dimension: df[dimension], metric: pd.to_numeric(df[metric], errors="coerce")}).dropna()
                    if len(temp) < 12:
                        continue
                    pivot = temp.groupby(["period", dimension])[metric].sum().reset_index()
                    groups = []
                    for group, sub in pivot.groupby(dimension):
                        sub = sub.sort_values("period")
                        if len(sub) >= 3 and self._valid_pair(float(sub[metric].iloc[-1]), float(sub[metric].iloc[0])):
                            groups.append((str(group), self._pct_change(float(sub[metric].iloc[-1]), float(sub[metric].iloc[0])), len(sub)))
                    if len(groups) < 2:
                        continue
                    groups.sort(key=lambda item: item[1])
                    worst, best = groups[0], groups[-1]
                    spread = best[1] - worst[1]
                    if abs(spread) < 25:
                        continue
                    candidates.append(
                        InsightCandidate(
                            title=f"{dimension} 分组的 {metric} 趋势分化明显，最大差距 {abs(spread):.1f} 个百分点",
                            description=f"{best[0]} 的期间变化约 {best[1]:+.1f}%，{worst[0]} 约 {worst[1]:+.1f}%，说明不同分组走势并不同步。",
                            insight_type="trend_divergence",
                            score=min(abs(spread), 180.0) * 0.25 + 24,
                            confidence=0.65,
                            metric=metric,
                            dimension=dimension,
                            evidence={
                                "dimension": dimension,
                                "metric": metric,
                                "best_group": best[0],
                                "best_delta_pct": round(best[1], 2),
                                "worst_group": worst[0],
                                "worst_delta_pct": round(worst[1], 2),
                                "spread_pct_points": round(spread, 2),
                            },
                            recommendations=["优先检查走势最差分组是否存在库存、价格、渠道曝光或产品结构变化。"],
                            limitations=["分组趋势仅显示同步性差异，尚不能单独证明具体原因。"],
                        )
                    )
        return candidates

    def _mine_correlations(self, df: pd.DataFrame, numeric_cols: list[str]) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        cols = numeric_cols[:12]
        if len(cols) < 2:
            return candidates
        numeric = df[cols].apply(pd.to_numeric, errors="coerce")
        corr = numeric.corr(numeric_only=True)
        for i, left in enumerate(cols):
            for right in cols[i + 1 :]:
                value = corr.loc[left, right] if left in corr.index and right in corr.columns else None
                if value is None or pd.isna(value):
                    continue
                value = float(value)
                if abs(value) < 0.55:
                    continue
                valid_n = int(numeric[[left, right]].dropna().shape[0])
                if valid_n < 8:
                    continue
                direction = "正相关" if value > 0 else "负相关"
                confidence = min(0.95, 0.45 + abs(value) * 0.35 + math.log1p(valid_n) / 30)
                candidates.append(
                    InsightCandidate(
                        title=f"{left} 与 {right} 呈{direction}，相关系数 {value:.2f}",
                        description=f"在 {valid_n} 条有效记录中，{left} 与 {right} 的 Pearson 相关系数约为 {value:.2f}。",
                        insight_type="correlation",
                        score=abs(value) * 70 * confidence,
                        confidence=confidence,
                        metric=left,
                        dimension=right,
                        evidence={"left_metric": left, "right_metric": right, "correlation": round(value, 4), "valid_n": valid_n},
                        recommendations=["可进一步做分层散点图或回归建模，判断该相关关系在不同分组下是否稳定。"],
                        limitations=["相关不等于因果，且 Pearson 相关主要刻画线性关系。"],
                    )
                )
        return candidates

    def _mine_cooccurrence_patterns(self, df: pd.DataFrame, date_cols: list[str], categorical_cols: list[str]) -> list[InsightCandidate]:
        customer_col = self._find_col(categorical_cols, ("customer", "user", "member", "客户", "用户", "会员"))
        product_col = self._find_col(categorical_cols, ("product", "sku", "item", "商品", "产品", "品类", "类别"))
        date_col = date_cols[0] if date_cols else None
        if not customer_col or not product_col or not date_col:
            return []
        temp = df[[customer_col, product_col, date_col]].dropna().copy()
        if len(temp) < 20:
            return []
        temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp = temp.dropna().sort_values([customer_col, date_col])
        pair_counts: dict[tuple[str, str], int] = {}
        base_counts: dict[str, int] = {}
        for _, sub in temp.groupby(customer_col):
            records = list(zip(sub[product_col].astype(str), sub[date_col]))
            seen_bases = {product for product, _ in records}
            for product in seen_bases:
                base_counts[product] = base_counts.get(product, 0) + 1
            for idx, (left_product, left_date) in enumerate(records):
                for right_product, right_date in records[idx + 1 :]:
                    if left_product == right_product:
                        continue
                    days = (right_date - left_date).days
                    if 0 <= days <= 30:
                        pair_counts[(left_product, right_product)] = pair_counts.get((left_product, right_product), 0) + 1
        if not pair_counts:
            return []
        candidates: list[InsightCandidate] = []
        for (left, right), count in sorted(pair_counts.items(), key=lambda item: item[1], reverse=True)[:12]:
            base = base_counts.get(left, 0)
            if base < 5:
                continue
            rate = count / base
            if rate < 0.25:
                continue
            confidence = min(0.9, 0.4 + math.log1p(count) / 8)
            candidates.append(
                InsightCandidate(
                    title=f"购买 {left} 的客户中有 {rate * 100:.1f}% 会在 30 天内购买 {right}",
                    description=f"基于 {customer_col} 的购买序列，{count} 个客户出现 {left} -> {right} 的 30 天内后续购买信号。",
                    insight_type="sequence_pattern",
                    score=rate * 70 * confidence + min(count, 50) * 0.4,
                    confidence=confidence,
                    metric=product_col,
                    dimension=customer_col,
                    evidence={
                        "customer_column": customer_col,
                        "product_column": product_col,
                        "date_column": date_col,
                        "base_product": left,
                        "next_product": right,
                        "base_customer_count": base,
                        "pair_customer_count": count,
                        "within_days": 30,
                        "conversion_rate": round(rate, 4),
                    },
                    recommendations=["可将该商品组合用于交叉销售、优惠券触达或加购推荐实验。"],
                    limitations=["该序列模式需要订单级客户数据支撑，且仍可能受促销和季节性影响。"],
                )
            )
        return candidates

    def _mine_quality_patterns(self, df: pd.DataFrame) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        n = max(1, len(df))
        for col in df.columns:
            missing_rate = float(df[col].isna().sum()) / n
            if missing_rate >= 0.15:
                candidates.append(
                    InsightCandidate(
                        title=f"{col} 缺失率达到 {missing_rate * 100:.1f}%",
                        description=f"{col} 的缺失值占比偏高，可能影响后续分组、建模或归因分析。",
                        insight_type="data_quality",
                        score=min(missing_rate * 120, 80),
                        confidence=0.95,
                        metric=col,
                        dimension=None,
                        evidence={"column": col, "missing_count": int(df[col].isna().sum()), "missing_rate": round(missing_rate, 4)},
                        recommendations=["确认该字段缺失是否代表真实业务状态，必要时补数或在报告中单独披露。"],
                        limitations=["数据质量洞察用于提示风险，不代表业务表现好坏。"],
                    )
                )
        return candidates

    def _rank_candidates(self, candidates: list[InsightCandidate]) -> list[InsightCandidate]:
        deduped: list[InsightCandidate] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
            key = (candidate.insight_type, candidate.metric, candidate.dimension)
            if key in seen and candidate.insight_type not in {"segment_difference", "sequence_pattern"}:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _summary(self, insights: list[dict[str, Any]], row_count: int, column_count: int) -> str:
        if not insights:
            return f"已扫描 {row_count} 行、{column_count} 列数据，暂未发现达到阈值的高置信规律。建议补充更多时间、客户或业务维度后再次挖掘。"
        top = insights[0]
        return f"已自动扫描 {row_count} 行、{column_count} 列数据，发现 {len(insights)} 条候选洞察。最高价值信号是：{top.get('title')}。"

    def _global_limitations(self, row_count: int, column_count: int, insights: list[dict[str, Any]]) -> list[str]:
        result = ["智能洞察挖掘默认识别相关信号、分层差异和异常模式，不直接证明因果关系。"]
        if row_count < 50:
            result.append("当前样本量较小，分组和时间趋势的稳定性有限。")
        if column_count < 3:
            result.append("字段数量较少，可挖掘的交叉维度有限。")
        if not insights:
            result.append("未发现显著洞察可能是因为数据跨度、维度或样本量不足。")
        return result

    def _find_col(self, columns: list[str], hints: tuple[str, ...]) -> str | None:
        for col in columns:
            lowered = col.lower()
            if any(hint in lowered or hint in col for hint in hints):
                return col
        return None

    def _confidence_from_counts(self, counts: list[Any], std_value: Any) -> float:
        numeric_counts = [int(count) for count in counts if count is not None and int(count) > 0]
        if not numeric_counts:
            return 0.35
        min_count = min(numeric_counts)
        total = sum(numeric_counts)
        count_factor = min(1.0, math.log1p(total) / 5.0) * min(1.0, min_count / 8.0)
        variance_penalty = 0.85 if std_value is not None and not pd.isna(std_value) and float(std_value) > 0 else 0.65
        return max(0.25, min(0.95, 0.25 + count_factor * variance_penalty))

    def _valid_pair(self, left: float, right: float) -> bool:
        return not (pd.isna(left) or pd.isna(right) or abs(right) < 1e-12)

    def _pct_change(self, current: float, baseline: float) -> float:
        return (current - baseline) / abs(baseline) * 100.0
