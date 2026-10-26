"""Recipe and pulse-scheme parser for the ALD anomaly application v2.

The parser intentionally preserves process blocks instead of collapsing every
number into one total.  In particular, a GeTe -> Te recipe keeps the GeTe pulse
block and the following Te pulse block separate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import re
from typing import Iterable


ROUTE_TE_2STEP = "TE_2STEP"
ROUTE_TE_4STEP = "TE_4STEP"
ROUTE_TE_COREACTANT_4STEP = "TE_COREACTANT_4STEP"
ROUTE_GETE_ONLY = "GETE_ONLY"
ROUTE_GETE_THEN_TE = "GETE_THEN_TE"
ROUTE_GETE_GESE_THEN_TE = "GETE_GESE_THEN_TE"
ROUTE_GESE_ONLY = "GESE_ONLY"
ROUTE_TE_OXIDE = "TE_OXIDE"
ROUTE_OTHER = "OTHER_COMPLEX_ROUTE"
ROUTE_UNCERTAIN = "PARSE_UNCERTAIN"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    """Split while preserving delimiters inside (), [] and {}."""
    parts: list[str] = []
    start = 0
    depth = 0
    opening = "([{"
    closing = ")]}"
    for idx, char in enumerate(text):
        if char in opening:
            depth += 1
        elif char in closing:
            depth = max(0, depth - 1)
        elif char == delimiter and depth == 0:
            part = text[start:idx].strip()
            if part:
                parts.append(part)
            start = idx + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


@dataclass(frozen=True)
class PulseBlock:
    raw: str = ""
    step_values: tuple[float, ...] = ()
    physical_step_count: int = 0
    pulse_pair_count: int | None = None
    inject_total: float | None = None
    purge_total: float | None = None
    duration_total: float | None = None
    parse_status: str = "empty"
    parse_note: str = ""

    def prefixed_dict(self, prefix: str) -> dict[str, object]:
        return {
            f"{prefix}_pulse_raw": self.raw,
            f"{prefix}_step_values": "|".join(f"{v:g}" for v in self.step_values),
            f"{prefix}_step_count": self.physical_step_count,
            f"{prefix}_pulse_pair_count": self.pulse_pair_count,
            f"{prefix}_inject_total": self.inject_total,
            f"{prefix}_purge_total": self.purge_total,
            f"{prefix}_duration_total": self.duration_total,
            f"{prefix}_pulse_parse_status": self.parse_status,
            f"{prefix}_pulse_parse_note": self.parse_note,
        }


def _expand_term(term: str) -> tuple[list[float], str | None]:
    term = term.strip()
    repeat = re.fullmatch(r"\((.*)\)\s*\*\s*(\d+)", term)
    multiplier = 1
    if repeat:
        term = repeat.group(1)
        multiplier = int(repeat.group(2))
    # A hyphen in the workbook is a stage separator, not a negative sign.
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", term)]
    if not numbers:
        return [], f"숫자를 찾지 못함: {term!r}"
    return numbers * multiplier, None


def parse_pulse_block(expression: object) -> PulseBlock:
    raw = _clean_text(expression)
    if not raw:
        return PulseBlock()

    values: list[float] = []
    notes: list[str] = []
    for term in split_top_level(raw, "+"):
        expanded, error = _expand_term(term)
        values.extend(expanded)
        if error:
            notes.append(error)

    if not values:
        return PulseBlock(raw=raw, parse_status="unparsed", parse_note="; ".join(notes))

    duration_total = float(sum(values))
    if len(values) % 2:
        notes.append("단계 수가 홀수여서 inject/purge 쌍 합계를 확정하지 않음")
        return PulseBlock(
            raw=raw,
            step_values=tuple(values),
            physical_step_count=len(values),
            duration_total=duration_total,
            parse_status="warning",
            parse_note="; ".join(notes),
        )

    inject_total = float(sum(values[0::2]))
    purge_total = float(sum(values[1::2]))
    return PulseBlock(
        raw=raw,
        step_values=tuple(values),
        physical_step_count=len(values),
        pulse_pair_count=len(values) // 2,
        inject_total=inject_total,
        purge_total=purge_total,
        duration_total=duration_total,
        parse_status="ok" if not notes else "warning",
        parse_note="; ".join(notes),
    )


def parse_pulse_scheme(value: object) -> list[PulseBlock]:
    raw = _clean_text(value)
    if not raw:
        return []
    return [parse_pulse_block(part) for part in split_top_level(raw, ",")]


def normalize_reactant(value: object) -> tuple[str, float | None, bool]:
    raw = _clean_text(value)
    if not raw:
        return "", None, False
    normalized = re.sub(r"Isopropylamin(?:e)?", "Isopropylamine", raw, flags=re.IGNORECASE)
    flow_match = re.search(r"Ar\s*:\s*(\d+(?:\.\d+)?)\s*sccm", normalized, re.IGNORECASE)
    flow = float(flow_match.group(1)) if flow_match else None
    lower = normalized.lower()
    if "isopropylamine" in lower:
        name = "Isopropylamine"
    elif "methanol" in lower:
        name = "Methanol"
    elif re.search(r"\bdiw\b", lower):
        name = "DIW"
    elif re.fullmatch(r"\s*Ar\s*:\s*\d+(?:\.\d+)?\s*sccm\s*", normalized, re.IGNORECASE):
        name = "Ar"
    else:
        name = normalized.split("_")[0].strip()
    co_reactant_used = bool(name and name != "Ar")
    return name, flow, co_reactant_used


def _first_number(patterns: Iterable[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


_POST_TE_PATTERN = re.compile(r"Te\s*\(\s*OEt\s*\)\s*4|_Te_?\d+\s*cycle", re.IGNORECASE)
_GETE_PATTERN = re.compile(r"\bgete|^gt(?:\(|_)|^ald_gt$", re.IGNORECASE)
# "GeSe doping(10cycle)", "GeSe(12cycle)", "GeSe_70cycle" 를 모두 잡는다.
_GESE_PATTERN = re.compile(
    r"GeSe(\s*doping)?\s*[_(]?\s*(\d+(?:\.\d+)?)\s*cycle", re.IGNORECASE
)


def _has_post_te(recipe: str) -> bool:
    return bool(_POST_TE_PATTERN.search(recipe))


def split_gese_cycles(recipe: str) -> tuple[float | None, float | None]:
    """레시피 안의 GeSe 블록을 위치로 구분해 (도핑 cycle, 캡층 cycle)을 돌려준다.

    - GeTe 뒤 · 후속 Te(OEt)4 앞에 있는 GeSe  → Se 도핑
      ("doping" 표기가 없어도 도핑으로 본다. 2026-08 이후 레시피는 "GeSe(12cycle)"처럼 적힘)
    - "doping"이라고 명시된 GeSe             → 위치와 상관없이 Se 도핑
    - 후속 Te 뒤에 오는 GeSe                 → 캡층 (도핑 아님)
    - GeTe가 없는 레시피의 GeSe(GeSe 단독 등) → 기존과 같이 캡층 칸에 기록
    """
    gete = _GETE_PATTERN.search(recipe)
    te = _POST_TE_PATTERN.search(recipe) if gete else None
    gete_pos = gete.start() if gete else None
    te_pos = te.start() if te else None

    doping: float | None = None
    caps: list[float] = []
    for match in _GESE_PATTERN.finditer(recipe):
        cycle = float(match.group(2))
        explicit = bool(match.group(1))
        between = (
            gete_pos is not None
            and match.start() > gete_pos
            and (te_pos is None or match.start() < te_pos)
        )
        if (explicit or between) and doping is None:
            doping = cycle
        else:
            caps.append(cycle)
    return doping, (caps[-1] if caps else None)


@dataclass
class ParsedRecipe:
    recipe_name: str
    pulse_scheme_raw: str
    deposition_route: str
    te_step_mode: int | None
    co_reactant_used: bool
    co_reactant_name: str
    co_reactant_flow_sccm: float | None
    gete_only: bool
    gete_then_te: bool
    gete_cycle: float | None
    te_cycle: float | None
    gese_doping_cycle: float | None
    post_gese_cap_cycle: float | None
    cte_cycle: float | None
    al2o3_cap_cycle: float | None
    primary_block: PulseBlock = field(default_factory=PulseBlock)
    post_te_block: PulseBlock = field(default_factory=PulseBlock)
    additional_block_count: int = 0
    parse_status: str = "ok"
    parse_note: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("primary_block")
        data.pop("post_te_block")
        data.update(self.primary_block.prefixed_dict("primary"))
        data.update(self.post_te_block.prefixed_dict("post_te"))
        return data


def parse_recipe(recipe_name: object, pulse_scheme: object = None, reactant: object = None) -> ParsedRecipe:
    recipe = _clean_text(recipe_name)
    pulse_raw = _clean_text(pulse_scheme)
    blocks = parse_pulse_scheme(pulse_raw)
    primary = blocks[0] if blocks else PulseBlock()
    reactant_name, reactant_flow, co_reactant = normalize_reactant(reactant)
    lower = recipe.lower()

    has_gete = bool(_GETE_PATTERN.search(recipe))
    has_gese = "gese" in lower
    gese_doping_cycle, post_gese_cap_cycle = split_gese_cycles(recipe)
    has_gese_doping = gese_doping_cycle is not None or bool(
        re.search(r"GeSe\s*doping", recipe, re.IGNORECASE)
    )
    has_post_te = has_gete and _has_post_te(recipe)
    is_te_oxide = bool(re.match(r"\s*TeO2", recipe, re.IGNORECASE))
    is_direct_te = bool(re.match(r"\s*Te(?:_|\b)", recipe, re.IGNORECASE)) and not is_te_oxide

    gete_cycle = _first_number(
        (
            r"GeTe\s*\(\s*(\d+(?:\.\d+)?)\s*cycle\s*\)",
            r"GeTe(?:\([^)]*\))?[_\s]+(\d+(?:\.\d+)?)\s*cycle",
        ),
        recipe,
    )
    post_te_cycle = _first_number(
        (
            r"Te\s*\(\s*OEt\s*\)\s*4[_\s]*(?:\(|\[)?\s*(\d+(?:\.\d+)?)\s*cyc(?:le|yle)",
            r"Te\s*\(\s*OEt\s*\)\s*4\s*\(\s*(\d+(?:\.\d+)?)\s*cycle\s*\)",
        ),
        recipe,
    )
    direct_te_cycle = _first_number((r"^Te(?:O2)?[_\s]+(\d+(?:\.\d+)?)\s*cycle",), recipe)
    te_cycle = post_te_cycle if has_post_te else direct_te_cycle
    cte_cycle = _first_number((r"CTe[_\s]*(\d+(?:\.\d+)?)\s*cycle",), recipe)
    al2o3_cap_cycle = _first_number((r"Al2O3\s*\(?\s*(\d+(?:\.\d+)?)\s*cycle",), recipe)

    post_te_block = blocks[1] if has_post_te and len(blocks) >= 2 else PulseBlock()
    te_step_mode: int | None
    if is_direct_te or is_te_oxide:
        te_step_mode = primary.physical_step_count or None
    elif has_post_te:
        te_step_mode = post_te_block.physical_step_count or None
    else:
        te_step_mode = None

    if has_gete and has_gese_doping and has_post_te:
        route = ROUTE_GETE_GESE_THEN_TE
    elif has_gete and has_post_te:
        route = ROUTE_GETE_THEN_TE
    elif has_gete:
        route = ROUTE_GETE_ONLY
    elif has_gese:
        route = ROUTE_GESE_ONLY
    elif is_te_oxide:
        route = ROUTE_TE_OXIDE
    elif is_direct_te:
        if te_step_mode == 2:
            route = ROUTE_TE_2STEP
        elif te_step_mode == 4 and co_reactant:
            route = ROUTE_TE_COREACTANT_4STEP
        elif te_step_mode == 4:
            route = ROUTE_TE_4STEP
        else:
            route = ROUTE_OTHER
    elif re.search(r"\(Me3Si\)2(?:Te|Se)", recipe, re.IGNORECASE):
        route = ROUTE_OTHER
    else:
        route = ROUTE_UNCERTAIN

    notes: list[str] = []
    statuses = [block.parse_status for block in blocks]
    if any(status == "unparsed" for status in statuses):
        notes.append("Pulse Scheme 일부를 파싱하지 못함")
    elif any(status == "warning" for status in statuses):
        notes.append("Pulse Scheme에 의미 확인이 필요한 홀수 단계식이 있음")
    if has_gete and gete_cycle is None:
        notes.append("GeTe cycle을 Recipe명에서 찾지 못함")
    if has_post_te and post_te_cycle is None:
        notes.append("후속 Te cycle을 Recipe명에서 찾지 못함")
    if has_post_te and len(blocks) < 2:
        notes.append("GeTe/Te 순차 공정인데 Pulse Scheme 블록이 2개 미만임")
    if route == ROUTE_UNCERTAIN:
        notes.append("증착 경로를 판별하지 못함")

    parse_status = "ok"
    if route == ROUTE_UNCERTAIN or any(status == "unparsed" for status in statuses):
        parse_status = "unparsed"
    elif notes:
        parse_status = "warning"

    return ParsedRecipe(
        recipe_name=recipe,
        pulse_scheme_raw=pulse_raw,
        deposition_route=route,
        te_step_mode=te_step_mode,
        co_reactant_used=co_reactant,
        co_reactant_name=reactant_name,
        co_reactant_flow_sccm=reactant_flow,
        gete_only=route == ROUTE_GETE_ONLY,
        gete_then_te=route in {ROUTE_GETE_THEN_TE, ROUTE_GETE_GESE_THEN_TE},
        gete_cycle=gete_cycle,
        te_cycle=te_cycle,
        gese_doping_cycle=gese_doping_cycle,
        post_gese_cap_cycle=post_gese_cap_cycle,
        cte_cycle=cte_cycle,
        al2o3_cap_cycle=al2o3_cap_cycle,
        primary_block=primary,
        post_te_block=post_te_block,
        additional_block_count=max(0, len(blocks) - (2 if has_post_te else 1)),
        parse_status=parse_status,
        parse_note="; ".join(notes),
    )


__all__ = [
    "ParsedRecipe",
    "PulseBlock",
    "normalize_reactant",
    "parse_pulse_block",
    "parse_pulse_scheme",
    "parse_recipe",
    "split_top_level",
]
