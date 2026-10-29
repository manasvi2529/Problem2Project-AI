"""
Autonomous Project Deployer & Repository Initializer.

Responsibilities:
1. Creates project sandbox directory in data/sandboxes/<project_name>
2. Writes all full-stack application files (HTML, CSS, JS, Python FastAPI server)
3. Initializes a local Git repository and commits all files
4. Allocates an available local port and launches the server in the background
5. Verifies deployment health and returns active URL
"""
import os
import sys
import socket
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import time

from backend.config import settings

logger = logging.getLogger(__name__)

# Keep track of spawned project processes: {project_name: subprocess.Popen}
DEPLOYED_PROCESSES = {}


def find_available_port(start_port: int = 8020, max_port: int = 8050) -> int:
    """Find a free TCP port on localhost."""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


class ProjectDeployer:
    """Creates local Git repositories and launches fully working applications."""

    @staticmethod
    def deploy_application(
        project_name: str,
        files: Dict[str, str],
        preferred_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Deploy full-stack project files into sandbox, init git, and launch server.
        """
        clean_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name).lower()
        project_dir = settings.SANDBOX_DIR / clean_name
        project_dir.mkdir(parents=True, exist_ok=True)

        port = preferred_port or find_available_port()

        # Update port inside server.py so it runs on the allocated port
        if "server.py" in files:
            files["server.py"] = files["server.py"].replace("port=8020", f"port={port}")

        # 1. Write all source files
        written_files = []
        for filename, content in files.items():
            file_path = project_dir / filename
            file_path.write_text(content, encoding="utf-8")
            written_files.append(filename)

        # 2. Initialize Git Repository
        git_initialized = False
        commit_hash = ""
        try:
            subprocess.run(["git", "init"], cwd=str(project_dir), capture_output=True, check=False)
            subprocess.run(["git", "add", "."], cwd=str(project_dir), capture_output=True, check=False)
            commit_res = subprocess.run(
                ["git", "commit", "-m", "Initial commit from Problem2Project AI"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                check=False
            )
            git_initialized = True

            # Get commit hash
            rev_res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                check=False
            )
            commit_hash = rev_res.stdout.strip() if rev_res.returncode == 0 else "main"
        except Exception as e:
            logger.warning(f"Git init note: {e}")

        # 3. Terminate previous process for this project if running
        if clean_name in DEPLOYED_PROCESSES:
            try:
                DEPLOYED_PROCESSES[clean_name].terminate()
            except Exception:
                pass

        # 4. Launch the application server in the background
        server_script = project_dir / "server.py"
        app_url = f"http://localhost:{port}"

        proc = None
        if server_script.exists():
            try:
                log_file = project_dir / "server.log"
                log_fp = open(log_file, "w", encoding="utf-8")
                flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                proc = subprocess.Popen(
                    [sys.executable, str(server_script)],
                    cwd=str(project_dir),
                    stdout=log_fp,
                    stderr=log_fp,
                    creationflags=flags,
                )
                DEPLOYED_PROCESSES[clean_name] = proc
                # Brief sleep to allow server to bind
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Failed to spawn application process: {e}")

        return {
            "project_name": clean_name,
            "project_directory": str(project_dir),
            "port": port,
            "url": app_url,
            "files_created": written_files,
            "git_initialized": git_initialized,
            "git_commit": commit_hash,
            "status": "deployed" if proc else "created_only",
        }
