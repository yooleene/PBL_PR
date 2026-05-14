"""
OpenAI API를 활용한 기자 기사 분석 모듈
- 일반 분석 (관심분야·논조·키워드): 최신 기사 20건으로 분리 호출
- 토킹포인트 생성: 최신 기사 20건과 포스코 관련 기사 5건으로 분리 호출
"""

import json
import os
import re
from typing import Dict, List
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class OpenAIAnalyzer:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        self.client = OpenAI(api_key=api_key)
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    # ------------------------------------------------------------------ #
    #  메인 분석 함수
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        journalist_name: str,
        media_name: str,
        articles: List[Dict],
        posco_articles: List[Dict] = None,
    ) -> Dict:
        """
        두 개의 OpenAI 호출로 분석 수행.
        1) 최신 기사 20건 → 관심분야·논조·키워드
        2) 최신 기사 20건 + 포스코 기사 5건 → 토킹포인트·포스코 보도 성향
        """
        posco_articles = posco_articles or []

        # ── 호출 1: 일반 분석 ─────────────────────────────────────────────
        article_texts = self._articles_to_text(articles[:20])
        general = self._call_general_analysis(journalist_name, media_name, article_texts)

        # ── 호출 2: 토킹포인트 (최신 기사 + 포스코) ───────────────────────
        posco_texts = self._articles_to_text(posco_articles[:5])
        talking = self._call_talking_points(journalist_name, media_name, posco_texts, article_texts)

        # ── 결과 병합 ─────────────────────────────────────────────────────
        analysis = {**general, **talking}

        return {
            "journalist_name": journalist_name,
            "media_name": media_name,
            "total_articles": len(articles),
            "posco_article_count": len(posco_articles),
            "analysis": analysis,
            "latest_articles": self._format_list(articles[:20]),
            "posco_articles": self._format_list(posco_articles[:5]),
        }

    # ------------------------------------------------------------------ #
    #  OpenAI 호출 1: 관심분야 · 논조 · 키워드
    # ------------------------------------------------------------------ #

    def _call_general_analysis(self, journalist_name: str, media_name: str, article_texts: str) -> Dict:
        prompt = f"""당신은 언론 분석 전문가입니다.
아래는 {media_name} 소속 '{journalist_name}' 기자의 최신 기사입니다.

{article_texts}

위 기사들을 분석하여 아래 JSON 형식으로만 응답하세요.
마크다운 코드블록(```)을 절대 사용하지 말고 순수 JSON만 출력하세요.

{{
  "interest_areas": [
    {{"area": "분야명", "description": "1~2문장 설명"}},
    {{"area": "분야명", "description": "1~2문장 설명"}},
    {{"area": "분야명", "description": "1~2문장 설명"}}
  ],
  "article_tone": {{
    "overall": "전체 논조 요약 (2~3문장)",
    "characteristics": ["특징1", "특징2", "특징3"],
    "stance": "비판적"
  }},
  "recent_keywords": [
    {{"keyword": "키워드1", "frequency": "높음", "context": "관련 맥락 한 문장"}},
    {{"keyword": "키워드2", "frequency": "중간", "context": "관련 맥락 한 문장"}},
    {{"keyword": "키워드3", "frequency": "높음", "context": "관련 맥락 한 문장"}},
    {{"keyword": "키워드4", "frequency": "낮음", "context": "관련 맥락 한 문장"}},
    {{"keyword": "키워드5", "frequency": "중간", "context": "관련 맥락 한 문장"}}
  ]
}}

규칙:
- interest_areas: 3~5개
- recent_keywords: 5~10개
- stance는 반드시 "비판적", "중립적", "우호적" 중 하나
- frequency는 반드시 "높음", "중간", "낮음" 중 하나
- 한국어로 작성
- 순수 JSON만 출력 (다른 텍스트 없음)"""

        return self._call_openai(prompt, context="일반분석")

    # ------------------------------------------------------------------ #
    #  OpenAI 호출 2: 토킹포인트 (최신 기사 + 포스코)
    # ------------------------------------------------------------------ #

    def _call_talking_points(
        self,
        journalist_name: str,
        media_name: str,
        posco_texts: str,
        general_texts: str,
    ) -> Dict:
        context_section = f"""=== 기자 최신 기사 20건 ===
{general_texts}

=== 포스코 관련 기사 5건 ===
{posco_texts}"""

        prompt = f"""당신은 포스코 홍보팀 PR 전략가입니다.
'{journalist_name}' 기자({media_name})와의 미팅을 준비합니다.

{context_section}

위 기사를 바탕으로 아래 JSON 형식으로만 응답하세요.
마크다운 코드블록(```)을 절대 사용하지 말고 순수 JSON만 출력하세요.

{{
  "posco_coverage": {{
    "has_posco_articles": true,
    "posco_tone": "포스코 관련 기사의 논조 (1~2문장)",
    "posco_topics": ["토픽1", "토픽2", "토픽3"],
    "posco_summary": "포스코 관련 보도 요약 (3~5문장)"
  }},
  "talking_points": [
    {{
      "title": "토킹포인트 제목",
      "content": "기자에게 직접 말할 1인칭 대화 시나리오 (100자 이내)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "기자에게 직접 말할 1인칭 대화 시나리오 (300자 이내)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "기자에게 직접 말할 1인칭 대화 시나리오 (300자 이내)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "기자에게 직접 말할 1인칭 대화 시나리오 (300자 이내)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "기자에게 직접 말할 1인칭 대화 시나리오 (300자 이내)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }}
  ],
  "meeting_strategy": "전반적인 미팅 전략 및 주의사항 (3~5문장)"
}}

규칙:
- talking_points: 정확히 5개
- 기자의 최신 기사 20건과 포스코 관련 기사 5건을 모두 기준으로 작성
- 기자가 관심 있어 할 주제를 포스코 현안과 연결
- content는 포스코 홍보 담당자인 내가 기자에게 직접 말하는 1인칭 대화 시나리오로 작성
- content는 실제 미팅에서 바로 말할 수 있는 자연스러운 문장으로 작성(300자 내외)
- content에는 분석 설명이나 요약 대신 내가 할 말을 그대로 작성
- content에서 말투는 회사가 잘 홍보될 수 있도록 낮은 말투나 과장된 표현은 피하고, 기자가 신뢰할 수 있는 전문가로 인식할 수 있도록 정중하면서도 친근한 어조로 작성
- content는 각 항목마다 공백 포함 300자 이내
- 한국어로 작성
- 순수 JSON만 출력 (다른 텍스트 없음)"""

        result = self._call_openai(prompt, context="토킹포인트")
        self._limit_talking_point_content(result)
        return result

    # ------------------------------------------------------------------ #
    #  공통 OpenAI 호출 + JSON 파싱
    # ------------------------------------------------------------------ #

    def _call_openai(self, prompt: str, context: str = "") -> Dict:
        raw = ""
        try:
            response = self.client.responses.create(
                model=self.model_name,
                input=prompt,
            )
            raw = (response.output_text or "").strip()

            # 코드블록 제거
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*", "", raw)
            raw = raw.strip()

            return json.loads(raw)

        except json.JSONDecodeError:
            # JSON 부분만 추출 재시도
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
            return {"parse_error": True, "raw_response": raw[:500]}

        except Exception as e:
            error = {"error": str(e)}
            if raw:
                error["raw_response"] = raw[:500]
            if context:
                error["context"] = context
            return error

    # ------------------------------------------------------------------ #
    #  유틸
    # ------------------------------------------------------------------ #

    def _articles_to_text(self, articles: List[Dict]) -> str:
        """기사 목록을 프롬프트용 텍스트로 변환 (제목 필수, 본문 최대 1200자)"""
        if not articles:
            return "(기사 없음)"
        parts = []
        for i, art in enumerate(articles, 1):
            title = art.get("title", "")
            date = art.get("date", "")
            content = art.get("full_content", "").strip()
            if len(content) > 1200:
                content = content[:1200] + "…"
            # 본문이 없어도 제목만으로 분석 가능하도록 유지
            body = content if content else "(본문 미수집)"
            parts.append(f"[{i}] {date}\n제목: {title}\n내용: {body}")
        return "\n\n".join(parts)

    def _limit_talking_point_content(self, analysis: Dict) -> None:
        """모델 응답이 길어질 때 화면 표시용 토킹포인트 발화문을 100자로 제한."""
        talking_points = analysis.get("talking_points")
        if not isinstance(talking_points, list):
            return

        for point in talking_points:
            if not isinstance(point, dict) or "content" not in point:
                continue
            content = re.sub(r"\s+", " ", str(point["content"])).strip()
            point["content"] = content if len(content) <= 100 else content[:99].rstrip() + "…"

    def _format_list(self, articles: List[Dict]) -> List[Dict]:
        return [
            {
                "title": a.get("title", ""),
                "date": a.get("date", ""),
                "url": a.get("url", ""),
                "summary": (a.get("full_content", "")[:200] + "…")
                if len(a.get("full_content", "")) > 200
                else a.get("full_content", ""),
            }
            for a in articles
        ]


# 기존 코드와의 호환성을 위해 유지
GeminiAnalyzer = OpenAIAnalyzer
