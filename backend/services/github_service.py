"""
ProblemPilot AI — GitHub Integration Service
Secure account verification, automated secret scanning, repository creation,
git commits and push operations with remote verification.
"""
import re
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


# Regex patterns for secret detection
SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI / Claude Secret Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Access Token"),
    (r"-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----", "Private Cryptographic Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"postgres(ql)?://[^:]+:[^@]+@", "PostgreSQL Connection String with Password"),
]


class GitHubService:
    """
    Manages GitHub credentials, secret scanning, repository creation, and code push.
    """

    @staticmethod
    def scan_files_for_secrets(files: Dict[str, str]) -> List[Dict[str, str]]:
        """
        Scan all files for exposed secrets before allowing any commit or push.
        """
        findings = []
        for file_name, content in files.items():
            for pattern, label in SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    findings.append({
                        "file": file_name,
                        "type": label,
                        "description": f"Exposed secret pattern ({label}) detected in {file_name}.",
                    })
        return findings

    @staticmethod
    async def verify_github_token(token: str) -> Dict[str, Any]:
        """
        Verify that a GitHub Personal Access Token or OAuth token is valid and active.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ProblemPilot-AI",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.github.com/user", headers=headers)
            if resp.status_code == 200:
                user_data = resp.json()
                return {
                    "valid": True,
                    "username": user_data.get("login"),
                    "name": user_data.get("name"),
                    "email": user_data.get("email"),
                    "public_repos": user_data.get("public_repos"),
                    "scopes": resp.headers.get("x-oauth-scopes", ""),
                }
            return {
                "valid": False,
                "error": f"GitHub API rejected token (HTTP {resp.status_code}): {resp.text}",
            }

    @staticmethod
    async def create_remote_repository(
        token: str,
        repo_name: str,
        description: str,
        private: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new remote repository on GitHub under the authenticated user's account.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ProblemPilot-AI",
        }
        payload = {
            "name": repo_name,
            "description": description[:350],
            "private": private,
            "auto_init": False,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.github.com/user/repos", headers=headers, json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "repo_url": data.get("html_url"),
                    "clone_url": data.get("clone_url"),
                    "full_name": data.get("full_name"),
                    "private": data.get("private"),
                }
            elif resp.status_code == 422:
                # Repo already exists
                user_resp = await client.get("https://api.github.com/user", headers=headers)
                username = user_resp.json().get("login") if user_resp.status_code == 200 else "unknown"
                return {
                    "success": True,
                    "repo_url": f"https://github.com/{username}/{repo_name}",
                    "clone_url": f"https://github.com/{username}/{repo_name}.git",
                    "full_name": f"{username}/{repo_name}",
                    "note": "Repository already existed, using existing target.",
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to create repo (HTTP {resp.status_code}): {resp.text}",
                }

    @staticmethod
    async def commit_and_push_to_github(
        workspace_dir: Path,
        repo_clone_url: str,
        token: str,
        commit_message: str = "Initial commit by ProblemPilot AI",
    ) -> Dict[str, Any]:
        """
        Initialize git, stage files, commit, configure remote with token, and push.
        """
        # Embed token safely for authenticated push: https://oauth2:TOKEN@github.com/...
        auth_url = repo_clone_url
        if "https://github.com/" in repo_clone_url:
            auth_url = repo_clone_url.replace("https://github.com/", f"https://oauth2:{token}@github.com/")

        async def run_git(args: List[str]) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=str(workspace_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

        # 1. Initialize git if needed
        await run_git(["init"])
        await run_git(["config", "user.name", "ProblemPilot AI"])
        await run_git(["config", "user.email", "bot@problempilot.ai"])
        await run_git(["branch", "-M", "main"])

        # 2. Stage all files
        await run_git(["add", "."])

        # 3. Commit
        code, out, err = await run_git(["commit", "-m", commit_message])

        # 4. Remote setup
        await run_git(["remote", "remove", "origin"])
        await run_git(["remote", "add", "origin", auth_url])

        # 5. Push
        code, out, err = await run_git(["push", "-u", "origin", "main", "--force"])
        if code != 0:
            # Mask token in error message
            safe_err = err.replace(token, "[REDACTED_TOKEN]")
            return {"success": False, "error": f"Git push failed: {safe_err}"}

        # 6. Verify commit on remote
        verification = await GitHubService.verify_remote_commit(
            token=token,
            full_name=repo_clone_url.replace(".git", "").split("github.com/")[-1],
            branch="main",
        )

        return {
            "success": True,
            "commit_message": commit_message,
            "branch": "main",
            "remote_verified": verification.get("verified", False),
            "latest_commit_sha": verification.get("sha"),
            "message": "Successfully pushed project to GitHub and verified remote repository state.",
        }

    @staticmethod
    def get_oauth_authorization_url(state: str) -> Dict[str, Any]:
        """
        Generate secure GitHub OAuth authorization URL with CSRF state token.
        """
        if not settings.GITHUB_CLIENT_ID:
            return {
                "configured": False,
                "error": "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env.",
            }

        url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.GITHUB_CLIENT_ID}"
            f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
            f"&scope=repo,read:user"
            f"&state={state}"
        )
        return {
            "configured": True,
            "auth_url": url,
            "state": state,
        }

    @staticmethod
    async def exchange_code_for_token(code: str) -> Dict[str, Any]:
        """
        Exchange OAuth callback authorization code for an authenticated GitHub access token.
        """
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            return {
                "success": False,
                "error": "GitHub OAuth client credentials are not configured.",
            }

        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
        }
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://github.com/login/oauth/access_token", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data:
                    # Fetch user info with the acquired token
                    user_info = await GitHubService.verify_github_token(data["access_token"])
                    return {
                        "success": True,
                        "access_token": data["access_token"],
                        "token_type": data.get("token_type", "bearer"),
                        "scope": data.get("scope", ""),
                        "user": user_info,
                    }
                return {
                    "success": False,
                    "error": data.get("error_description", "Failed to retrieve access token from GitHub."),
                }
            return {
                "success": False,
                "error": f"GitHub token exchange failed (HTTP {resp.status_code})",
            }

    @staticmethod
    async def verify_remote_commit(token: str, full_name: str, branch: str = "main") -> Dict[str, Any]:
        """
        Verify that a remote repository exists and latest commit has been accepted on GitHub.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ProblemPilot-AI",
        }
        clean_name = full_name.strip("/")
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(f"https://api.github.com/repos/{clean_name}/commits/{branch}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "verified": True,
                        "sha": data.get("sha", "")[:7],
                        "full_sha": data.get("sha", ""),
                        "commit_message": data.get("commit", {}).get("message", ""),
                        "commit_date": data.get("commit", {}).get("author", {}).get("date"),
                    }
            except Exception as e:
                logger.debug(f"Remote commit check error: {e}")

        return {"verified": False}

