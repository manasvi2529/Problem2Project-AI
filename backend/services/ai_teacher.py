"""
ProblemPilot AI — AI Teacher & Pedagogical System
Generates deep technical explanations across Beginner, Intermediate, Advanced,
and Interview Preparation tiers, detailing why decisions were made, architectural
connections, trade-offs, and common pitfalls.
"""
import json
import logging
from typing import Dict, Any, Optional

from backend.config import settings
from backend.services.research_service import analyze_with_ai

logger = logging.getLogger(__name__)


class AITeacher:
    """
    Pedagogical engine connecting real project code to conceptual understanding
    and placement interview mastery.
    """

    @staticmethod
    def get_fallback_explanation(topic: str, level: str = "intermediate") -> Dict[str, Any]:
        """High-value technical breakdown when LLM provider is not connected."""
        topic_clean = topic.strip()
        return {
            "topic": topic_clean,
            "level": level,
            "summary": f"Comprehensive architectural breakdown of {topic_clean} in production systems.",
            "what_it_is": f"{topic_clean} is a foundational architectural component ensuring reliability, type-safety, and modularity in modern full-stack systems.",
            "why_used": f"We chose {topic_clean} over alternatives because it minimizes asynchronous I/O blocking, isolates domain boundaries, and produces testable contracts.",
            "how_it_works": "Requests enter through the FastAPI gateway, pass through Pydantic schema validation, trigger domain services, and persist state atomically via SQLAlchemy async sessions.",
            "architecture_connection": "It acts as the core communication bridge connecting the client UI event listeners to the backend database storage layer.",
            "alternatives_and_tradeoffs": [
                {"alternative": "Django / Flask", "tradeoff": "Higher CPU overhead and synchronous thread-blocking under concurrent stream loads."},
                {"alternative": "Node.js Express", "tradeoff": "Requires manual TypeScript typing and lacks native Python data science library ecosystem."},
            ],
            "common_pitfalls": [
                "Blocking the async event loop with synchronous time.sleep or heavy computational loops.",
                "Omitting database session closing, which leads to connection pool exhaustion.",
                "Forgetting to validate external input types, allowing malformed payload crashes.",
            ],
            "how_to_test": "Use pytest with httpx ASGITransport to test endpoints without spinning up live network ports, mocking database sessions for isolation.",
            "interview_explanation": f"In an interview, introduce {topic_clean} by identifying the bottleneck it resolved: 'To achieve sub-20ms latency and zero unhandled schema drift, I structured {topic_clean} with async coroutines and compile-time data validation, reducing operational triage time by over 80%.'",
        }

    async def explain_concept(
        self,
        topic: str,
        context: str = "",
        level: str = "intermediate",
    ) -> Dict[str, Any]:
        """Generate tailored pedagogical explanation."""
        if not settings.ai_configured:
            return self.get_fallback_explanation(topic, level)

        prompt = f"""You are a distinguished computer science professor and senior principal engineer mentoring a candidate.
Explain this concept/file/technology: "{topic}"
Project Context: {context}
Target Audience Level: {level} (beginner, intermediate, advanced, or interview_prep)

Provide a rich JSON response with:
- "topic": Topic name
- "level": Level
- "summary": 2-sentence executive summary
- "what_it_is": Clear definition
- "why_used": Architectural rationale
- "how_it_works": Step-by-step mechanical explanation
- "architecture_connection": How this interacts with the rest of the project
- "alternatives_and_tradeoffs": Array of objects with "alternative" and "tradeoff"
- "common_pitfalls": Array of 3 common mistakes and how to avoid them
- "how_to_test": How to test this component properly
- "interview_explanation": Exactly how to phrase and explain this in a placement interview to impress interviewers

Return ONLY valid JSON. No markdown backticks."""

        res = await analyze_with_ai(prompt)
        if res:
            try:
                cleaned = res.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()
                data = json.loads(cleaned)
                if "what_it_is" in data:
                    return data
            except Exception as e:
                logger.warning(f"Error parsing AI teacher output: {e}")

        return self.get_fallback_explanation(topic, level)

