"""OpenRouter LLM service for cloud AI completions."""

import requests
from typing import Optional
import json


class OpenRouterLLMService:
    """Generate completions using OpenRouter cloud API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "anthropic/claude-3.5-haiku",
        token_tracker=None
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.token_tracker = token_tracker
        self.base_url = "https://openrouter.ai/api/v1"
        self.enabled = self._check_api_available()

    def _check_api_available(self) -> bool:
        """Check if OpenRouter API is accessible."""
        if not self.api_key:
            return False

        try:
            # Test with minimal request
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.default_model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 5
                },
                timeout=10
            )
            return response.status_code in [200, 201]
        except Exception:
            return False

    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """
        Generate chat completion via OpenRouter.

        Cost: Varies by model
        - anthropic/claude-3.5-haiku: ~$0.25/M tokens
        - mistralai/mistral-7b-instruct: Free tier available
        Performance: ~500ms-2s depending on model
        """
        if not self.enabled:
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            import time
            start_time = time.time()

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/banton/claude-dementia",  # Optional: for rankings
                    "X-Title": "Claude Dementia MCP"  # Optional: for rankings
                },
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=60
            )
            response.raise_for_status()

            data = response.json()
            content = data['choices'][0]['message']['content']

            # Track usage if tracker available
            if self.token_tracker:
                duration_ms = int((time.time() - start_time) * 1000)
                input_text = (system_prompt or "") + prompt
                self.token_tracker.track_llm_completion(
                    input_text=input_text,
                    output_text=content,
                    model=model or self.default_model,
                    provider="openrouter",
                    duration_ms=duration_ms
                )

            return content

        except Exception as e:
            print(f"OpenRouter completion failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"Error details: {error_data}")
                except:
                    pass
            return None

    def summarize_context(
        self,
        content: str,
        max_length: int = 500
    ) -> Optional[str]:
        """Generate intelligent summary of context content."""
        if not self.enabled:
            return None

        prompt = f"""Summarize the following context in {max_length} characters or less.
Focus on:
1. Main topic/purpose
2. Key rules (MUST/ALWAYS/NEVER)
3. Important technical concepts

Context:
{content[:5000]}"""

        return self.chat_completion(
            prompt,
            system_prompt="You are a technical summarization assistant. Be concise and focus on critical information.",
            temperature=0.3,
            max_tokens=200
        )

    def classify_context_priority(self, content: str) -> Optional[str]:
        """Classify context priority using AI."""
        if not self.enabled:
            return None

        prompt = f"""Classify this context's priority level:
- "always_check": Contains rules that MUST be followed (MUST/ALWAYS/NEVER keywords)
- "important": Contains key decisions, specifications, or critical info
- "reference": General information or documentation

Context: {content[:1000]}

Respond with ONLY one word: always_check, important, or reference"""

        response = self.chat_completion(
            prompt,
            temperature=0.1,
            max_tokens=10
        )

        if response:
            priority = response.strip().lower()
            if priority in ["always_check", "important", "reference"]:
                return priority

        return None

    def get_stats(self) -> dict:
        """Get service statistics and configuration."""
        return {
            "enabled": self.enabled,
            "provider": "openrouter",
            "model": self.default_model,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "features": {
                "models_available": "100+ models",
                "free_tier": "Available for some models",
                "openai_compatible": True
            }
        }
