"""
ProblemPilot AI — Cloud Deployment Engine
Manages real cloud hosting deployment configurations (Vercel, Render, Railway, Docker)
and conducts live remote health verification.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class CloudDeployer:
    """
    Produces cloud deployment manifests and performs live remote verification.
    """

    @staticmethod
    def generate_deployment_manifests(
        workspace_dir: Path,
        project_name: str,
        provider: str = "vercel",
    ) -> Dict[str, str]:
        """
        Generate provider-specific deployment manifests.
        """
        manifests = {}
        clean_name = "".join(c if c.isalnum() or c == "-" else "-" for c in project_name.lower())[:30].strip("-")

        # 1. Vercel Manifest
        vercel_config = {
            "version": 2,
            "name": clean_name,
            "builds": [
                {"src": "server.py", "use": "@vercel/python"},
                {"src": "index.html", "use": "@vercel/static"},
                {"src": "styles.css", "use": "@vercel/static"},
                {"src": "app.js", "use": "@vercel/static"},
            ],
            "routes": [
                {"src": "/api/(.*)", "dest": "server.py"},
                {"src": "/(.*)", "dest": "/$1"},
            ]
        }
        manifests["vercel.json"] = json.dumps(vercel_config, indent=2)

        # 2. Render Manifest
        render_yaml = f"""services:
  - type: web
    name: {clean_name}
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
"""
        manifests["render.yaml"] = render_yaml

        # 3. Dockerfile
        dockerfile = f"""FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8030

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8030"]
"""
        manifests["Dockerfile"] = dockerfile

        # Write them to workspace
        for fname, content in manifests.items():
            fpath = workspace_dir / fname
            fpath.write_text(content, encoding="utf-8")

        return manifests

    @staticmethod
    async def verify_remote_deployment(deployment_url: str) -> Dict[str, Any]:
        """
        Conduct live HTTP health check probe on public deployment URL.
        """
        clean_url = deployment_url.rstrip("/")
        endpoints_to_probe = [
            f"{clean_url}/api/v1/health",
            f"{clean_url}/health",
            clean_url,
        ]

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for url in endpoints_to_probe:
                try:
                    resp = await client.get(url)
                    if resp.status_code in (200, 201, 204):
                        return {
                            "verified": True,
                            "url": deployment_url,
                            "probed_endpoint": url,
                            "status_code": resp.status_code,
                            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
                            "message": "Live cloud deployment verified healthy.",
                        }
                except Exception as e:
                    logger.debug(f"Probe to {url} failed: {e}")

        return {
            "verified": False,
            "url": deployment_url,
            "error": "Could not connect to deployment URL or health endpoints did not respond with 200 OK.",
        }

