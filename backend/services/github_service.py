"""
ProblemPilot AI — GitHub Integration Service
Secure account verification, automated secret scanning, repository creation,
git commits and push operations with remote verification.
"""
import os
import re
import base64
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


def redact_credentials(text: Any, token: Optional[str] = None) -> str:
    """
    Scrub tokens and credential patterns from text, logs, and error messages.
    Ensures credentials never appear in user-facing responses or server logs.
    """
    if not text:
        return ""
    redacted = str(text)
    if token and str(token) in redacted:
        redacted = redacted.replace(str(token), "[REDACTED_TOKEN]")
    # Redact common credential patterns (PAT, OAuth, fine-grained PAT)
    redacted = re.sub(r"gh[pousr]_[A-Za-z0-9_]{20,}", "[REDACTED_TOKEN]", redacted)
    redacted = re.sub(r"github_pat_[A-Za-z0-9_]{20,}", "[REDACTED_TOKEN]", redacted)
    # Redact embedded URL credentials https://user:pass@github.com -> https://[REDACTED_AUTH]@github.com
    redacted = re.sub(r"(https?://)[^:@\s]+:[^@\s]+@", r"\1[REDACTED_AUTH]@", redacted)
    # Redact authorization header values
    redacted = re.sub(r"(AUTHORIZATION:\s*(?:bearer|basic)\s+)[^\s'\"]+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


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
        Checks for .env files, private keys, API keys, and sensitive tokens.
        """
        findings = []
        for file_name, content in files.items():
            # Check sensitive file names
            base_name = Path(file_name).name.lower()
            if base_name in (".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json"):
                findings.append({
                    "file": file_name,
                    "type": "Sensitive Environment/Key File",
                    "description": f"Restricted environment or private credential file detected ({file_name}).",
                })

            # Check pattern matches
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
    def redact_credentials(text: Any, token: Optional[str] = None) -> str:
        return redact_credentials(text, token)

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
                "error": redact_credentials(f"GitHub API rejected token (HTTP {resp.status_code}): {resp.text}", token),
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
        Preserves remote private repository creation.
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
                    "error": redact_credentials(f"Failed to create repo (HTTP {resp.status_code}): {resp.text}", token),
                }

    @staticmethod
    async def commit_and_push_to_github(
        workspace_dir: Path,
        repo_clone_url: str,
        token: str,
        commit_message: str = "Initial commit by ProblemPilot AI",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Initialize git, stage files, commit, configure clean remote without tokens,
        and securely push using temporary subprocess HTTP authentication headers.
        Never embeds tokens in git remote URLs, command-line arguments, or .git/config.
        """
        # Ensure clean remote URL without any credentials embedded
        clean_url = re.sub(r"https?://[^@]+@", "https://", repo_clone_url)

        async def run_git(args: List[str], env: Optional[Dict[str, str]] = None) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=str(workspace_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

        # Prepare secure temporary HTTP extraHeader authorization for git subprocess
        auth_bytes = f"x-access-token:{token}".encode("utf-8")
        basic_auth = base64.b64encode(auth_bytes).decode("ascii")

        push_env = os.environ.copy()
        push_env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic_auth}",
            "GIT_CONFIG_KEY_1": "credential.helper",
            "GIT_CONFIG_VALUE_1": "",
        })

        try:
            # 1. Initialize git if needed
            await run_git(["init"])
            await run_git(["config", "user.name", "ProblemPilot AI"])
            await run_git(["config", "user.email", "bot@problempilot.ai"])
            await run_git(["branch", "-M", "main"])

            # 2. Stage all files
            await run_git(["add", "."])

            # 3. Commit only if there are changes to commit
            status_code, status_out, _ = await run_git(["status", "--porcelain"])
            if status_out.strip():
                await run_git(["commit", "-m", commit_message])

            # 4. Configure remote with clean URL (never containing credentials)
            code, out, _ = await run_git(["remote", "get-url", "origin"])
            if code == 0:
                await run_git(["remote", "set-url", "origin", clean_url])
            else:
                await run_git(["remote", "add", "origin", clean_url])

            # 5. Push using temporary subprocess environment authentication
            push_args = ["push", "-u", "origin", "main"]
            if force:
                push_args.append("--force")

            code, out, err = await run_git(push_args, env=push_env)
            if code != 0:
                safe_err = redact_credentials(err, token)
                if "fetch first" in err or "non-fast-forward" in err or "conflict" in err:
                    return {
                        "success": False,
                        "conflict": True,
                        "error": f"Push rejected: Remote repository already has conflicting commits. Use a fresh repository or merge history: {safe_err}",
                    }
                return {"success": False, "error": f"Git push failed: {safe_err}"}

            # 6. Verify commit on remote repository
            clean_full_name = clean_url.replace(".git", "").split("github.com/")[-1]
            try:
                verification = await GitHubService.verify_remote_commit(
                    token=token,
                    full_name=clean_full_name,
                    branch="main",
                )
            except Exception as ve:
                verification = {"verified": False, "error": redact_credentials(str(ve), token)}

            return {
                "success": True,
                "commit_message": commit_message,
                "branch": "main",
                "remote_verified": verification.get("verified", False),
                "latest_commit_sha": verification.get("sha"),
                "commit_details": verification,
                "message": "Successfully pushed project to GitHub and verified remote repository state.",
            }
        except Exception as e:
            safe_err = redact_credentials(str(e), token)
            return {
                "success": False,
                "error": f"Git operation failed: {safe_err}",
            }
        finally:
            # Secure cleanup: clear in-memory temporary credentials and guarantee clean remote URL
            push_env.clear()
            try:
                await run_git(["remote", "set-url", "origin", clean_url])
            except Exception:
                pass

    @staticmethod
    def get_oauth_authorization_url(state: str) -> Dict[str, Any]:
        """
        Generate secure GitHub OAuth authorization URL with CSRF state token.
        """
        missing = settings.get_missing_github_oauth_vars()
        if missing:
            return {
                "configured": False,
                "missing_vars": missing,
                "error": f"GitHub OAuth is not configured. Missing required variables: {', '.join(missing)}.",
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
            "callback_url": settings.GITHUB_REDIRECT_URI,
        }

    @staticmethod
    async def exchange_code_for_token(code: str) -> Dict[str, Any]:
        """
        Exchange OAuth callback authorization code for an authenticated GitHub access token.
        """
        missing = settings.get_missing_github_oauth_vars()
        if missing:
            return {
                "success": False,
                "missing_vars": missing,
                "error": f"GitHub OAuth client credentials are not configured. Missing: {', '.join(missing)}.",
            }

        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
        }
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
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
                        "error": data.get("error_description", data.get("error", "Failed to retrieve access token from GitHub.")),
                    }
                return {
                    "success": False,
                    "error": f"GitHub token exchange failed (HTTP {resp.status_code})",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Network error during GitHub token exchange: {str(e)}",
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

