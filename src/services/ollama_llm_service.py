"""Ollama LLM service for local language model operations."""

import requests
from typing import Optional
import time


class OllamaLLMService:
    """Generate completions using Ollama local models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "mistral",
        token_tracker=None
    ):
        self.base_url = base_url
        self.default_model = default_model
        self.enabled = self._check_ollama_available()
        self.token_tracker = token_tracker

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code != 200:
                return False

            models = response.json().get('models', [])
            return any(m['name'].startswith(self.default_model) for m in models)
        except Exception:
            return False

    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        context_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Generate chat completion via Ollama.

        Cost: FREE (local)
        Performance: ~500ms-2s depending on model and length

        Returns None if service not enabled or on error.
        """
        if not self.enabled:
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                },
                timeout=60
            )
            response.raise_for_status()

            duration_ms = int((time.time() - start_time) * 1000)

            data = response.json()
            output = data['message']['content']

            # Track usage
            if self.token_tracker:
                input_text = (system_prompt or "") + prompt
                self.token_tracker.track_llm_completion(
                    input_text=input_text,
                    output_text=output,
                    model=model or self.default_model,
                    provider='ollama',
                    duration_ms=duration_ms,
                    context_id=context_id
                )

            return output
        except Exception as e:
            import sys
            print(f"Ollama completion failed: {e}", file=sys.stderr)
            return None

    def summarize_context(
        self,
        content: str,
        max_length: int = 500
    ) -> Optional[str]:
        """
        Generate intelligent summary of context content.

        Cost: FREE (local)
        Falls back to None if service unavailable.
        """
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
        """
        Classify context priority using AI.

        Returns: "always_check", "important", "reference", or None
        """
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
        """Get service statistics."""
        return {
            'enabled': self.enabled,
            'model': self.default_model,
            'base_url': self.base_url,
            'cost': 'FREE (local)',
            'performance': '~500ms-2s per completion'
        }
