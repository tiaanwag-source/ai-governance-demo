# sdk/client.py

import os
import json
from typing import Any, Dict, Optional

import requests


class AIGovClient:
    """
    Thin SDK around the AI Governance Demo API.

    Responsibilities:
      - Handle base URL and optional API key
      - Provide simple methods:
          * health()
          * get_metrics()
          * recompute_all()
          * get_governance_context(agent_id)
          * check_action(agent_id, action, prompt, metadata, requested_by)
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        # Default to env var or localhost
        self.api_base = (api_base or os.getenv("AI_GOV_API_BASE", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("AI_GOV_API_KEY")
        self.timeout = timeout

    # ------------- internal helpers -------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_base}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        resp.raise_for_status()
        if not resp.text:
            return None
        return resp.json()

    def _post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_base}{path}"
        payload = json.dumps(body or {})
        resp = requests.post(url, headers=self._headers(), data=payload, timeout=self.timeout)
        resp.raise_for_status()
        if not resp.text:
            return None
        return resp.json()

    # ------------- public methods -------------

    def health(self) -> Any:
        """Ping /health."""
        return self._get("/health")

    def get_metrics(self) -> Any:
        """Fetch /admin/metrics summary."""
        return self._get("/admin/metrics")

    def recompute_all(self) -> Any:
        """Hit /admin/recompute_all to recompute signals + risk bands."""
        return self._post("/admin/recompute_all", {})

    def get_governance_context(self, agent_id: str) -> Any:
        """
        Fetch SEE + SCORE context for a single agent.

        Expects backend route:
          GET /agents/{agent_id}/governance
        """
        return self._get(f"/agents/{agent_id}/governance")

    def check_action(
        self,
        agent_id: str,
        action: str,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        requested_by: Optional[str] = None,
    ) -> Any:
        """
        Call the safeguard endpoint to retrieve system header + approval guidance.
        """
        body: Dict[str, Any] = {
            "agent_id": agent_id,
            "action": action,
            "prompt": prompt,
            "metadata": metadata or {},
        }
        if requested_by:
            body["requested_by"] = requested_by
        return self._post("/sdk/check_and_header", body)

    def safe_chat(
        self,
        agent_id: str,
        user_prompt: str,
        input_metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Convenience wrapper that runs check_action() for a chat-style request.
        """
        requested_by = (input_metadata or {}).get("requested_by") if input_metadata else None
        return self.check_action(
            agent_id=agent_id,
            action="chat",
            prompt=user_prompt,
            metadata=input_metadata,
            requested_by=requested_by,
        )
