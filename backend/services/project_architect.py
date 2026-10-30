"""
ProblemPilot AI — Project Blueprint & Architecture Architect
Generates comprehensive, non-generic project blueprints, system architectures,
database schemas, API contracts, interview preparation guides, and resume bullets.
"""
import json
import logging
from typing import Dict, Any, Optional

from backend.config import settings
from backend.services.research_service import analyze_with_ai

logger = logging.getLogger(__name__)


class ProjectArchitect:
    """
    Synthesizes tailored software blueprints from validated problem opportunities.
    """

    @staticmethod
    def generate_fallback_blueprint(problem_title: str, problem_desc: str, tech_stack: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a rigorous, complete architectural specification when LLM is unavailable.
        """
        clean_title = problem_title.replace("’", "'").strip()
        stack = tech_stack or {
            "frontend": ["HTML5 Semantic Elements", "Modern CSS Glassmorphism", "Vanilla ES6 JavaScript"],
            "backend": ["Python 3.11+", "FastAPI Async Framework", "Pydantic V2 Models"],
            "database": "SQLite (Development) / PostgreSQL with SQLAlchemy 2.0 Async ORM",
            "testing": ["pytest", "pytest-asyncio", "httpx TestClient"],
            "deployment": "Docker / Vercel (Frontend) & Render / Railway (Backend API)",
        }

        return {
            "problem_statement": clean_title,
            "detailed_context": problem_desc,
            "target_users": "Engineering teams, operations leads, and technical founders needing reliable automated solutions.",
            "mvp_features": [
                "Real-time Dashboard with status metrics and telemetry monitoring.",
                "Automated Anomaly Detection & Discrepancy Flagging Engine.",
                "RESTful API for data ingestion, querying, and verification audit trails.",
                "Configurable Webhook & Notification Dispatcher.",
                "CSV and JSON export capabilities for reporting.",
            ],
            "functional_requirements": [
                "System must process incoming records within 200ms.",
                "Discrepancies must be flagged with severity tags (Low, Medium, Critical).",
                "Audit logs must record all state modifications with UTC timestamps.",
                "User must be able to filter, search, and resolve identified issues via the UI.",
            ],
            "non_functional_requirements": [
                "Security: JWT bearer authentication and role-based permissions.",
                "Performance: Asynchronous I/O handling up to 500 concurrent requests.",
                "Maintainability: Modular clean architecture separating routes, services, and models.",
                "Reliability: Graceful degradation and fallback handlers on upstream service timeouts.",
            ],
            "architecture": {
                "pattern": "Layered Micro-modular Architecture",
                "frontend_layer": "Single Page Application communicating over JSON REST APIs with live polling.",
                "api_gateway_layer": "FastAPI ASGI application with CORS middleware, rate limiters, and error interceptors.",
                "service_layer": "Domain logic isolation: validation services, calculation engines, and persistence bridges.",
                "data_layer": "Async SQLAlchemy session management with transactional integrity and foreign key constraints.",
            },
            "database_schema": [
                {
                    "table": "entities",
                    "columns": [
                        "id VARCHAR(36) PRIMARY KEY",
                        "title VARCHAR(255) NOT NULL",
                        "status VARCHAR(50) DEFAULT 'active'",
                        "metadata JSON",
                        "created_at TIMESTAMP WITH TIME ZONE",
                        "updated_at TIMESTAMP WITH TIME ZONE",
                    ],
                    "indexes": ["idx_entities_status", "idx_entities_created_at"],
                    "purpose": "Stores core business entities being tracked or reconciled.",
                },
                {
                    "table": "discrepancies",
                    "columns": [
                        "id VARCHAR(36) PRIMARY KEY",
                        "entity_id VARCHAR(36) REFERENCES entities(id)",
                        "severity VARCHAR(20) NOT NULL",
                        "description TEXT NOT NULL",
                        "resolved BOOLEAN DEFAULT FALSE",
                        "detected_at TIMESTAMP WITH TIME ZONE",
                    ],
                    "indexes": ["idx_discrepancies_resolved"],
                    "purpose": "Stores detected issues, variances, or anomalies with resolution tracking.",
                },
                {
                    "table": "audit_events",
                    "columns": [
                        "id VARCHAR(36) PRIMARY KEY",
                        "event_type VARCHAR(100) NOT NULL",
                        "details JSON",
                        "created_at TIMESTAMP WITH TIME ZONE",
                    ],
                    "indexes": ["idx_audit_events_created_at"],
                    "purpose": "Immutable chronological ledger of all automated and manual actions.",
                },
            ],
            "api_contracts": [
                {"method": "GET", "path": "/api/v1/entities", "purpose": "List tracked records with pagination and status filters.", "response": "{ items: [], total: int }"},
                {"method": "POST", "path": "/api/v1/entities", "purpose": "Ingest and validate new entity record.", "response": "{ id: str, status: 'created' }"},
                {"method": "GET", "path": "/api/v1/discrepancies", "purpose": "Retrieve active unacknowledged anomalies.", "response": "{ discrepancies: [] }"},
                {"method": "POST", "path": "/api/v1/discrepancies/{id}/resolve", "purpose": "Mark an anomaly as investigated and resolved.", "response": "{ status: 'resolved' }"},
                {"method": "GET", "path": "/api/v1/metrics/summary", "purpose": "Quantitative statistics for executive dashboard.", "response": "{ total: int, open_issues: int, health_score: float }"},
            ],
            "tech_stack": stack,
            "testing_plan": [
                "Unit Tests: Model schema validation, business metric formulas, and edge case parsers.",
                "Integration Tests: Full HTTP request-response flow via AsyncClient ASGI transport.",
                "End-to-End Smoke Tests: SPA static asset serving and live API connectivity check.",
            ],
            "interview_preparation": [
                {
                    "question": f"Why did you choose FastAPI and Async SQLAlchemy for {clean_title} instead of traditional Django or Flask?",
                    "answer": "FastAPI provides native asynchronous coroutines (async/await) which prevent I/O blocking when communicating with databases or external APIs. Paired with SQLAlchemy 2.0 async engine and Pydantic validation, it delivers automatic OpenAPI schema generation, compile-time type validation, and high throughput with minimal boilerplate.",
                },
                {
                    "question": "How do you handle schema drift or corrupted data inputs in this system?",
                    "answer": "Input payloads are strictly validated through Pydantic models before reaching the business layer. Any schema anomalies trigger structured 422 Unprocessable Entity responses logged to the audit ledger rather than causing uncaught runtime exceptions.",
                },
                {
                    "question": "What is the single biggest architectural trade-off made in this design?",
                    "answer": "Choosing a single-node asynchronous SQLite/PostgreSQL architecture over a distributed microservice setup. For an MVP processing thousands of daily events, this eliminates network latency and distributed transaction overhead while remaining trivial to containerize and deploy.",
                },
            ],
            "resume_bullet_points": [
                f"Architected and developed {clean_title}, an asynchronous software system reducing manual reconciliation toil by over 80%.",
                "Engineered RESTful APIs with FastAPI and Pydantic V2, achieving sub-20ms response times for high-throughput anomaly detection.",
                "Implemented resilient data modeling using SQLAlchemy Async ORM with automated migration management and comprehensive indexing.",
                "Established automated CI test pipelines with pytest and ASGI test client, ensuring 100% test coverage on critical business logic.",
            ],
        }

    async def generate_blueprint(self, problem_title: str, problem_desc: str) -> Dict[str, Any]:
        """
        Generate an AI-driven or high-quality fallback project blueprint.
        """
        if not settings.ai_configured:
            return self.generate_fallback_blueprint(problem_title, problem_desc)

        prompt = f"""You are an elite software architect at Google / Y Combinator.
Design a complete, production-grade project blueprint to solve this real-world problem:

Problem: {problem_title}
Context: {problem_desc}

Generate a comprehensive JSON document with:
- "problem_statement": Concise problem summary
- "detailed_context": In-depth background
- "target_users": Primary audience
- "mvp_features": List of 5 core MVP features
- "functional_requirements": 4 concrete functional requirements
- "non_functional_requirements": 4 non-functional specs (latency, security, concurrency)
- "architecture": {{"pattern": "...", "frontend_layer": "...", "api_gateway_layer": "...", "service_layer": "...", "data_layer": "..."}}
- "database_schema": Array of 3 tables, each with "table", "columns" (types included), "indexes", "purpose"
- "api_contracts": Array of 5 endpoints with "method", "path", "purpose", "response"
- "tech_stack": {{"frontend": [...], "backend": [...], "database": "...", "testing": [...], "deployment": "..."}}
- "testing_plan": Array of 3 testing strategies
- "interview_preparation": Array of 3 objects with "question" and "answer"
- "resume_bullet_points": Array of 4 high-impact resume achievement bullets

Return ONLY valid JSON. No markdown backticks."""

        ai_res = await analyze_with_ai(prompt)
        if ai_res:
            try:
                cleaned = ai_res.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()
                data = json.loads(cleaned)
                if "problem_statement" in data and "database_schema" in data:
                    return data
            except Exception as e:
                logger.warning(f"Error parsing AI blueprint: {e}")

        return self.generate_fallback_blueprint(problem_title, problem_desc)

