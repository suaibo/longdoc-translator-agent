from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class StructureState(TypedDict):
    profile: str
    source: str
    translation: str
    issues: list[dict[str, str]]


def _validate_table(state: StructureState) -> dict:
    source_rows = sum(
        1 for line in state["source"].splitlines() if line.lstrip().startswith("|")
    )
    translated_rows = sum(
        1
        for line in state["translation"].splitlines()
        if line.lstrip().startswith("|")
    )
    issues = []
    if source_rows != translated_rows:
        issues.append(
            {
                "type": "TABLE",
                "severity": "HIGH",
                "message": "表格行数与原文不一致",
            }
        )
    return {"issues": issues}


def _validate_formula(state: StructureState) -> dict:
    return _validate_marker_count(state, "$", "FORMULA", "公式分隔符数量不一致")


def _validate_reference(state: StructureState) -> dict:
    return _validate_marker_count(state, "[", "REFERENCE", "引用标记数量不一致")


def _validate_marker_count(
    state: StructureState, marker: str, issue_type: str, message: str
) -> dict:
    issues = []
    if state["source"].count(marker) != state["translation"].count(marker):
        issues.append(
            {"type": issue_type, "severity": "HIGH", "message": message}
        )
    return {"issues": issues}


def build_structure_subgraph(profile: str):
    validators = {
        "table": _validate_table,
        "formula": _validate_formula,
        "reference": _validate_reference,
    }
    builder = StateGraph(StructureState)
    builder.add_node("validate_structure", validators[profile])
    builder.add_edge(START, "validate_structure")
    builder.add_edge("validate_structure", END)
    return builder.compile(name=f"{profile}-structure-subgraph")


def validate_structure(
    profile: str, source: str, translation: str
) -> list[dict[str, str]]:
    if profile not in {"table", "formula", "reference"}:
        return []
    result = build_structure_subgraph(profile).invoke(
        {
            "profile": profile,
            "source": source,
            "translation": translation,
            "issues": [],
        }
    )
    return result["issues"]
