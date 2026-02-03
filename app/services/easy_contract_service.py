from __future__ import annotations
import logging
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

from app.resources.vllm.client import VLLMClient
from app.resources.ocr.upstage_client import UpstageDocumentParseClient
from app.utils.upstage_html import extract_plain_text_from_upstage_json
from app.settings import settings


class EasyContractState(TypedDict, total=False):
    case_id: int
    # 입력 파일들(각각 bytes + doc_type)
    docs: List[Dict[str, Any]]  # {"filename": str, "bytes": bytes, "doc_type": str}

    # OCR 결과
    pages_text: List[Dict[str, Any]]  # {"doc_type": str, "file": str, "page": int, "text": str}

    # 페이지별 핵심 요약
    page_summaries: List[Dict[str, Any]]  # {"doc_type":..., "file":..., "page":..., "summary": str}

    # 최종 쉬운계약서(마크다운)
    markdown: str


def _page_summary_prompt(doc_type: str, page_no: int, text: str) -> list[dict[str, str]]:
    system = (
        "너는 주택 임대차 문서를 페이지 단위로 읽고 핵심 정보를 추출하는 도우미다.\n"
        "규칙:\n"
        "1) 출력은 간결한 불릿 목록으로만 작성\n"
        "2) 아래 항목을 우선 추출: 계약일/임대차기간/보증금/월세/관리비/특약/위약금/해지조건/수리·하자/원상복구/당사자 정보\n"
        "3) 페이지에 없으면 '없음'으로 쓰지 말고 해당 항목은 생략\n"
        "4) 숫자/날짜는 원문 표현을 최대한 유지\n"
    )
    user = (
        f"[문서타입] {doc_type}\n"
        f"[페이지] {page_no}\n"
        f"[OCR 텍스트]\n{text}\n\n"
        "이 페이지에서 중요한 조항과 날계약일/임대차기간/보증금/월세/관리비/특약/위약금/해지조건/수리·하자/원상복구만 불릿으로 정리해줘.\n"
        "반드시 OCR 텍스트에 제시된 내용을 정리하고 없는 정보를 만들어내지 마라.\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _final_markdown_prompt(page_summaries: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = (
        "너는 주택 임대차 계약서를 쉽게 풀어서 설명하고 분석해서 마크다운으로 출력하는 도우미다.\n"
        "규칙:\n"
        "1) 출력은 마크다운만 (설명문/코드블록 금지)\n"
        "2) 사실에 근거해 작성. 추측 금지\n"
        "3) 섹션 예시(필요한 것만 포함):\n"
        "   - 요약(한 문단)\n"
        "   - 핵심 조건(표)\n"
        "   - 중요 조항(불릿)\n"
        "   - 위험/주의 포인트(불릿)\n"
        "4) 금액/날짜/기간/당사자/주소 등은 가능한 한 원문 기반으로 명확히\n"
    )

    lines = []
    for s in page_summaries:
        lines.append(
            f"- ({s['doc_type']}/{s['file']} p.{s['page']}) {s['summary']}".strip()
        )

    user = (
        "[페이지별 핵심 요약]\n" + "\n".join(lines) + "\n\n"
        "위 주택 임대차 계약서 요약들을 종합하여 계약서를 설명하고 분석한 결과를 마크다운으로 작성해줘."
        "반드시 페이지별 핵심 요약을 기반으로 작성하고 없는 정보를 만들어내지 마라.\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class EasyContractService:
    def __init__(self, vllm: VLLMClient, ocr: UpstageDocumentParseClient):
        self.vllm = vllm
        self.ocr = ocr
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(EasyContractState)

        async def ocr_stage(state: EasyContractState) -> EasyContractState:
            logger.info("계약서 ocr stage")
            pages_text: list[dict[str, Any]] = []

            for doc in state["docs"]:
                filename = doc["filename"]
                doc_type = doc["doc_type"]
                b = doc["bytes"]

                if filename.lower().endswith(".pdf"):
                    from app.utils.pdf_images import pdf_bytes_to_png_pages
                    try:
                        logger.info("pdf 이미지 변환중")
                        page_images = pdf_bytes_to_png_pages(b, zoom=2.0)
                        logger.info("pdf 이미지 변환완료")
                    except Exception as e:
                        raise RuntimeError("UNPROCESSABLE_DOCUMENT") from e

                    for i, img in enumerate(page_images, start=1):
                        logger.info("이미지로 변환 후 ocr 요청")
                        data = await self.ocr.parse_image(img, filename=f"{filename}.p{i}.png")
                        logger.info("ocr 완료 후 텍스트 추출")
                        text = extract_plain_text_from_upstage_json(data)
                        logger.debug("OCR 결과", extra={"text_length": len(text)})
                        pages_text.append({"doc_type": doc_type, "file": filename, "page": i, "text": text})
                else:
                    logger.info("ocr 요청")
                    data = await self.ocr.parse_image(b, filename=filename)
                    logger.info("ocr 완료 후 텍스트 추출")
                    text = extract_plain_text_from_upstage_json(data)
                    logger.debug("OCR 결과", extra={"text_length": len(text)})
                    pages_text.append({"doc_type": doc_type, "file": filename, "page": 1, "text": text})

            state["pages_text"] = pages_text
            return state

        async def page_summarize_stage(state: EasyContractState) -> EasyContractState:
            logger.info("계약서 페이지별 요약 시작")
            summaries: list[dict[str, Any]] = []
            for p in state.get("pages_text", []):
                txt = (p.get("text") or "").strip()
                if not txt:
                    continue

                msgs = _page_summary_prompt(p["doc_type"], p["page"], txt[:20000])
                logger.info("계약서 요약중")
                summary = await self.vllm.chat(
                    msgs,
                    temperature=0.2,
                    max_tokens=1024,
                    model=settings.VLLM_LORA_ADAPTER_EASYCONTRACT,
                )
                logger.debug("계약서 요약 결과", extra={"summary_length": len(summary)})
                summaries.append(
                    {"doc_type": p["doc_type"], "file": p["file"], "page": p["page"], "summary": summary.strip()}
                )

            state["page_summaries"] = summaries
            return state

        async def final_stage(state: EasyContractState) -> EasyContractState:
            msgs = _final_markdown_prompt(state.get("page_summaries", []))
            logger.info("쉬운계약서 생성 요청")
            md = await self.vllm.chat(
                msgs,
                temperature=0.2,
                max_tokens=2048,
                model=settings.VLLM_LORA_ADAPTER_EASYCONTRACT,
            )
            logger.info("쉬운계약서 생성 완료")
            state["markdown"] = md.strip()
            logger.debug("마크다운 생성 완료", extra={"length": len(state["markdown"])})
            return state

        g.add_node("ocr", ocr_stage)
        g.add_node("page_summarize", page_summarize_stage)
        g.add_node("final", final_stage)

        g.set_entry_point("ocr")
        g.add_edge("ocr", "page_summarize")
        g.add_edge("page_summarize", "final")
        g.add_edge("final", END)

        return g.compile()

    async def generate(self, case_id: int, docs: list[dict[str, Any]]) -> str:
        logger.info("쉬운 계약서 시작", extra={"case_id": case_id})
        out = await self.graph.ainvoke({"case_id": case_id, "docs": docs})
        logger.info("쉬운 계약서 마크다운 생성 완료", extra={"case_id": case_id, "length": len(out.get("markdown", ""))})
        return out.get("markdown", "")
