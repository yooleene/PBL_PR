"""
Google Gemini API를 활용한 기자 기사 분석 모듈
- 일반 분석 (관심분야·논조·키워드): 최신 기사 20건으로 분리 호출
- 토킹포인트 생성: 포스코 관련 기사 5건으로 분리 호출
"""

import json
import os
import re
from typing import Dict, List
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiAnalyzer:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 또는 GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.model = genai.GenerativeModel(model_name)

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
        두 개의 Gemini 호출로 분석 수행.
        1) 최신 기사 20건 → 관심분야·논조·키워드
        2) 포스코 기사 5건 → 토킹포인트·포스코 보도 성향
        """
        posco_articles = posco_articles or []

        # ── 호출 1: 일반 분석 ─────────────────────────────────────────────
        article_texts = self._articles_to_text(articles[:20])
        general = self._call_general_analysis(journalist_name, media_name, article_texts)

        # ── 호출 2: 토킹포인트 (포스코) ──────────────────────────────────
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
    #  Gemini 호출 1: 관심분야 · 논조 · 키워드
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

        return self._call_gemini(prompt, context="일반분석")

    # ------------------------------------------------------------------ #
    #  Gemini 호출 2: 토킹포인트 (포스코)
    # ------------------------------------------------------------------ #

    def _call_talking_points(
        self,
        journalist_name: str,
        media_name: str,
        posco_texts: str,
        general_texts: str,
    ) -> Dict:
        context_section = (
            f"=== 포스코 관련 기사 ===\n{posco_texts}"
            if posco_texts.strip()
            else f"(포스코 관련 기사 없음 — 아래 일반 기사 기반으로 작성)\n\n=== 기자 최신 기사 ===\n{general_texts}"
        )

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
      "content": "구체적 대화 내용 (2~3문장)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "구체적 대화 내용 (2~3문장)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "구체적 대화 내용 (2~3문장)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "구체적 대화 내용 (2~3문장)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }},
    {{
      "title": "토킹포인트 제목",
      "content": "구체적 대화 내용 (2~3문장)",
      "rationale": "이 포인트가 효과적인 이유 (1문장)"
    }}
  ],
  "meeting_strategy": "전반적인 미팅 전략 및 주의사항 (3~5문장)"
}}

규칙:
- talking_points: 정확히 5개
- 포스코 홍보 담당자 관점에서 실질적으로 활용 가능한 내용
- 기자의 관심사와 포스코 현안을 연결하는 방향으로 작성
- 한국어로 작성
- 순수 JSON만 출력 (다른 텍스트 없음)"""

        return self._call_gemini(prompt, context="토킹포인트")

    # ------------------------------------------------------------------ #
    #  공통 Gemini 호출 + JSON 파싱
    # ------------------------------------------------------------------ #

    def _call_gemini(self, prompt: str, context: str = "") -> Dict:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )
            raw = response.text.strip()

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
            return {"error": str(e)}

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
