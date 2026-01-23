from __future__ import annotations
from typing import TypedDict
import json
import re

from langgraph.graph import StateGraph, END
from app.resources.vllm.client import VLLMClient


COMMON_CHECKLIST: list[str] = [
    "보증금이 주변 시세 대비 과도하지 않은지 확인하세요.",
    "등기부등본 소유자와 계약서 임대인이 동일한지 확인하세요.",
    "등기부등본에 압류·가압류·강제경매 등 권리침해가 없는지 확인하세요.",
    "근저당권 설정 금액이 과도하지 않은지 확인하세요.",
    "계약 직전 최신 등기부등본으로 변동사항이 없는지 다시 확인하세요.",
    "건축물대장에 위반건축물 표시가 없는지 확인하세요.",
    "건축물대장상 용도가 주택인지 확인하세요.",
    "주소/동·호수가 등기부등본·건축물대장·계약서와 모두 일치하는지 확인하세요.",
    "임대인의 신분을 확인하고 계약서 정보와 일치하는지 확인하세요.",
    "공동 소유 주택이면 소유자 전원과 계약하는지 확인하세요.",
    "대리인 계약이면 위임장 원본과 신분증을 확인하세요.",
    "위임장에 주택 주소·계약 조건·보증금 수령자가 명시됐는지 확인하세요.",
    "공인중개사 거래 시 개업 공인중개사 등록 여부를 확인하세요.",
    "중개대상물 확인·설명서를 교부받았는지 확인하세요.",
    "계약 기간(시작일/종료일)이 정확히 적혀있는지 확인하세요.",
    "보증금·월세 금액과 납부일이 계약서에 명시됐는지 확인하세요.",
    "보증금/월세 입금 계좌 예금주가 임대인(또는 적법 수령자)인지 확인하세요.",
    "관리비 포함 항목과 부담 주체가 계약서에 적혀있는지 확인하세요.",
    "구두로 약속한 내용이 있다면 특약에 반영됐는지 확인하세요.",
    "입주 전 집 상태가 계약 조건과 동일한지 확인하세요."
]


class ChecklistState(TypedDict, total=False):
    case_id: str
    keywords: list[str]
    checklists: list[str]


def _normalize_keywords(keywords: list[str]) -> list[str]:
    cleaned = []
    for k in keywords:
        k2 = (k or "").strip()
        if k2:
            cleaned.append(k2)

    seen = set()
    out = []
    for k in cleaned:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _build_prompt(keywords: list[str], common: list[str]) -> list[dict[str, str]]:
    system = (
        "너는 주택 임대차 계약 체크리스트를 생성하는 도우미다.\n"
        "출력 규칙:\n"
        "1) JSON 배열(list)만 출력. 예: [\"...\", \"...\"]\n"
        "2) 전체 항목 수는 20~30개 이하\n"
        "3) 공통 체크리스트 항목은 유지하되, 키워드에 맞는 항목을 추가/보강\n"
        "4) 중복 항목 제거\n"
        "5) 각 문장은 반드시 '~확인하세요.'로 끝나야 함\n"
    )

    user = (
        "[공통 체크리스트]\n- " + "\n- ".join(common) + "\n\n"
        "[사용자 키워드]\n- " + "\n- ".join(keywords) + "\n\n"
        "위 정보를 바탕으로 최종 체크리스트를 만들어줘."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_model_output(text: str) -> list[str]:
    t = (text or "").strip()

    try:
        data = json.loads(t)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return [x.strip() for x in data if x and x.strip()]
    except Exception:
        pass

    t = re.sub(r"^```.*?\n|\n```$", "", t, flags=re.DOTALL).strip()
    lines = []
    for line in t.splitlines():
        s = line.strip()
        s = re.sub(r"^\d+\.\s*", "", s)
        s = re.sub(r"^-+\s*", "", s)
        if s:
            lines.append(s)

    out = []
    seen = set()
    for x in lines:
        x2 = x.strip().strip('"').strip()
        if not x2:
            continue
        if not x2.endswith("확인하세요."):
            if x2.endswith("."):
                x2 = x2[:-1].rstrip()
            if not x2.endswith("확인하세요"):
                x2 = x2 + " 확인하세요."
            else:
                x2 = x2 + "."
        if x2 not in seen:
            seen.add(x2)
            out.append(x2)

    return out


class ChecklistService:
    def __init__(self, vllm: VLLMClient):
        self.vllm = vllm
        self.graph = self._build_graph()

    def _build_graph(self):
        print("그래프 빌드 시작")
        g = StateGraph(ChecklistState)

        def start(state: ChecklistState) -> ChecklistState:
            state["keywords"] = _normalize_keywords(state.get("keywords", []))
            return state

        def route(state: ChecklistState) -> str:
            return "no_keywords" if len(state.get("keywords", [])) == 0 else "with_keywords"

        def no_keywords(state: ChecklistState) -> ChecklistState:
            state["checklists"] = COMMON_CHECKLIST
            return state

        async def with_keywords(state: ChecklistState) -> ChecklistState:
            msgs = _build_prompt(state["keywords"], COMMON_CHECKLIST)
            print("체크리스트 생성 모델 요청")
            content = await self.vllm.chat(msgs, temperature=0.2, max_tokens=800)
            items = _parse_model_output(content)
            print(items)

            merged = []
            seen = set()
            for x in COMMON_CHECKLIST + items:
                x2 = (x or "").strip()
                if x2 and x2 not in seen:
                    seen.add(x2)
                    merged.append(x2)

            state["checklists"] = merged[:30]
            return state

        g.add_node("start", start)
        g.add_node("no_keywords", no_keywords)
        g.add_node("with_keywords", with_keywords)

        g.set_entry_point("start")
        g.add_conditional_edges("start", route, {"no_keywords": "no_keywords", "with_keywords": "with_keywords"})
        g.add_edge("no_keywords", END)
        g.add_edge("with_keywords", END)

        return g.compile()

    async def generate(self, case_id: str, keywords: list[str]) -> list[str]:
        out = await self.graph.ainvoke({"case_id": case_id, "keywords": keywords})
        print("체크리스트 생성 완료")
        return out.get("checklists", COMMON_CHECKLIST)
