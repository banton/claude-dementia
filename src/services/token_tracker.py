"""Token usage tracking for cost comparison."""

import sqlite3
import time
from typing import Dict, Optional
import tiktoken


class TokenTracker:
    """Track token usage for cost comparison with cloud APIs."""

    # Pricing (per million tokens)
    PRICING = {
        # OpenAI Embeddings
        'openai_embedding_small': 0.02,      # text-embedding-3-small
        'openai_embedding_large': 0.13,      # text-embedding-3-large

        # OpenAI LLM
        'openai_gpt35_input': 0.50,          # GPT-3.5 Turbo input
        'openai_gpt35_output': 1.50,         # GPT-3.5 Turbo output
        'openai_gpt4_input': 10.00,          # GPT-4 Turbo input
        'openai_gpt4_output': 30.00,         # GPT-4 Turbo output

        # Voyage AI Embeddings (200M free tokens for most models)
        'voyage_3_large': 0.18,              # voyage-3-large
        'voyage_context_3': 0.18,            # voyage-context-3
        'voyage_3_5': 0.06,                  # voyage-3.5
        'voyage_3_5_lite': 0.02,             # voyage-3.5-lite (cheapest)
        'voyage_code_3': 0.18,               # voyage-code-3
        'voyage_finance_2': 0.12,            # voyage-finance-2 (50M free)
        'voyage_law_2': 0.12,                # voyage-law-2 (50M free)
        'voyage_code_2': 0.12,               # voyage-code-2 (50M free)

        # Voyage AI Rerankers (200M free tokens)
        'voyage_rerank_2_5': 0.05,           # rerank-2.5
        'voyage_rerank_2_5_lite': 0.02,      # rerank-2.5-lite

        # OpenRouter (via OpenAI-compatible)
        'openrouter_claude_haiku': 0.25,     # Claude 3 Haiku
        'openrouter_mistral_7b': 0.00,       # Free tier

        # Local (Ollama)
        'ollama': 0.00                        # FREE
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_schema()

        # Initialize tokenizer for accurate counting
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-3.5/4 encoding
        except:
            self.tokenizer = None  # Fallback to char-based estimation

    def _init_schema(self):
        """Create usage tracking table if not exists."""
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                operation_type TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER DEFAULT 0,
                input_chars INTEGER NOT NULL,
                output_chars INTEGER DEFAULT 0,
                duration_ms INTEGER,
                context_id INTEGER,
                metadata TEXT
            )
        ''')

        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp
            ON token_usage(timestamp DESC)
        ''')

        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_usage_operation
            ON token_usage(operation_type, provider)
        ''')

        self.conn.commit()

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Uses tiktoken if available, otherwise estimates based on chars.
        """
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except:
                pass

        # Fallback: estimate (1 token ≈ 4 chars)
        return len(text) // 4

    def track_embedding(
        self,
        text: str,
        model: str,
        provider: str,
        duration_ms: int,
        context_id: Optional[int] = None
    ):
        """Track embedding generation."""
        tokens = self.count_tokens(text)

        self.conn.execute('''
            INSERT INTO token_usage
            (timestamp, operation_type, model, provider,
             input_tokens, input_chars, duration_ms, context_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            time.time(),
            'embedding',
            model,
            provider,
            tokens,
            len(text),
            duration_ms,
            context_id
        ))

        self.conn.commit()

    def track_llm_completion(
        self,
        input_text: str,
        output_text: str,
        model: str,
        provider: str,
        duration_ms: int,
        context_id: Optional[int] = None
    ):
        """Track LLM completion."""
        input_tokens = self.count_tokens(input_text)
        output_tokens = self.count_tokens(output_text)

        self.conn.execute('''
            INSERT INTO token_usage
            (timestamp, operation_type, model, provider,
             input_tokens, output_tokens, input_chars, output_chars,
             duration_ms, context_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            time.time(),
            'llm_completion',
            model,
            provider,
            input_tokens,
            output_tokens,
            len(input_text),
            len(output_text),
            duration_ms,
            context_id
        ))

        self.conn.commit()

    def get_usage_stats(
        self,
        days: int = 30,
        operation_type: Optional[str] = None
    ) -> Dict:
        """Get usage statistics for time period."""

        since = time.time() - (days * 86400)

        # Build query
        sql = '''
            SELECT
                operation_type,
                provider,
                model,
                COUNT(*) as operation_count,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(input_chars) as total_input_chars,
                SUM(output_chars) as total_output_chars,
                AVG(duration_ms) as avg_duration_ms,
                MIN(timestamp) as first_use,
                MAX(timestamp) as last_use
            FROM token_usage
            WHERE timestamp >= ?
        '''

        params = [since]

        if operation_type:
            sql += ' AND operation_type = ?'
            params.append(operation_type)

        sql += ' GROUP BY operation_type, provider, model'

        cursor = self.conn.execute(sql, params)

        stats = []
        for row in cursor.fetchall():
            stats.append(dict(row))

        return {
            'period_days': days,
            'stats': stats,
            'summary': self._calculate_summary(stats)
        }

    def _calculate_summary(self, stats: list) -> Dict:
        """Calculate summary statistics."""
        total_ops = sum(s['operation_count'] for s in stats)
        total_input_tokens = sum(s['total_input_tokens'] for s in stats)
        total_output_tokens = sum(s['total_output_tokens'] or 0 for s in stats)

        return {
            'total_operations': total_ops,
            'total_input_tokens': total_input_tokens,
            'total_output_tokens': total_output_tokens,
            'total_tokens': total_input_tokens + total_output_tokens
        }

    def calculate_costs(self, stats: Dict) -> Dict:
        """
        Calculate costs for different providers.

        Returns cost breakdown for local vs cloud alternatives.
        """
        costs = {
            'actual': {'provider': 'ollama', 'cost_usd': 0.00},
            'alternatives': {}
        }

        for stat in stats['stats']:
            op_type = stat['operation_type']
            input_tokens = stat['total_input_tokens']
            output_tokens = stat['total_output_tokens'] or 0

            if op_type == 'embedding':
                # Calculate OpenAI embedding costs
                cost_small = (input_tokens / 1_000_000) * self.PRICING['openai_embedding_small']
                cost_large = (input_tokens / 1_000_000) * self.PRICING['openai_embedding_large']

                # Calculate Voyage AI embedding costs
                cost_voyage_lite = (input_tokens / 1_000_000) * self.PRICING['voyage_3_5_lite']
                cost_voyage_35 = (input_tokens / 1_000_000) * self.PRICING['voyage_3_5']
                cost_voyage_large = (input_tokens / 1_000_000) * self.PRICING['voyage_3_large']

                if 'openai_embedding' not in costs['alternatives']:
                    costs['alternatives']['openai_embedding'] = {
                        'provider': 'OpenAI',
                        'model': 'text-embedding-3-small',
                        'cost_usd': 0.0
                    }

                if 'voyage_lite' not in costs['alternatives']:
                    costs['alternatives']['voyage_lite'] = {
                        'provider': 'Voyage AI',
                        'model': 'voyage-3.5-lite',
                        'cost_usd': 0.0,
                        'free_tier': '200M tokens/month'
                    }

                if 'voyage_standard' not in costs['alternatives']:
                    costs['alternatives']['voyage_standard'] = {
                        'provider': 'Voyage AI',
                        'model': 'voyage-3.5',
                        'cost_usd': 0.0,
                        'free_tier': '200M tokens/month'
                    }

                if 'voyage_large' not in costs['alternatives']:
                    costs['alternatives']['voyage_large'] = {
                        'provider': 'Voyage AI',
                        'model': 'voyage-3-large',
                        'cost_usd': 0.0,
                        'free_tier': '200M tokens/month'
                    }

                costs['alternatives']['openai_embedding']['cost_usd'] += cost_small
                costs['alternatives']['voyage_lite']['cost_usd'] += cost_voyage_lite
                costs['alternatives']['voyage_standard']['cost_usd'] += cost_voyage_35
                costs['alternatives']['voyage_large']['cost_usd'] += cost_voyage_large

            elif op_type == 'llm_completion':
                # Calculate OpenAI GPT costs
                gpt35_cost = (
                    (input_tokens / 1_000_000) * self.PRICING['openai_gpt35_input'] +
                    (output_tokens / 1_000_000) * self.PRICING['openai_gpt35_output']
                )

                gpt4_cost = (
                    (input_tokens / 1_000_000) * self.PRICING['openai_gpt4_input'] +
                    (output_tokens / 1_000_000) * self.PRICING['openai_gpt4_output']
                )

                if 'openai_gpt35' not in costs['alternatives']:
                    costs['alternatives']['openai_gpt35'] = {
                        'provider': 'OpenAI',
                        'model': 'GPT-3.5 Turbo',
                        'cost_usd': 0.0
                    }

                if 'openai_gpt4' not in costs['alternatives']:
                    costs['alternatives']['openai_gpt4'] = {
                        'provider': 'OpenAI',
                        'model': 'GPT-4 Turbo',
                        'cost_usd': 0.0
                    }

                costs['alternatives']['openai_gpt35']['cost_usd'] += gpt35_cost
                costs['alternatives']['openai_gpt4']['cost_usd'] += gpt4_cost

        # Calculate savings
        for alt_name, alt_data in costs['alternatives'].items():
            alt_data['savings_usd'] = alt_data['cost_usd'] - costs['actual']['cost_usd']
            alt_data['savings_percent'] = 100.0  # Always 100% with Ollama

        return costs

    def get_cost_comparison(self, days: int = 30) -> Dict:
        """Get comprehensive cost comparison."""
        stats = self.get_usage_stats(days)
        costs = self.calculate_costs(stats)

        return {
            'period_days': days,
            'usage_summary': stats['summary'],
            'detailed_usage': stats['stats'],
            'cost_comparison': costs,
            'pricing_reference': {
                'openai_embeddings': f"${self.PRICING['openai_embedding_small']:.2f}/M tokens",
                'openai_gpt35': f"${self.PRICING['openai_gpt35_input']:.2f}/M input, ${self.PRICING['openai_gpt35_output']:.2f}/M output",
                'openai_gpt4': f"${self.PRICING['openai_gpt4_input']:.2f}/M input, ${self.PRICING['openai_gpt4_output']:.2f}/M output",
                'voyage_lite': f"${self.PRICING['voyage_3_5_lite']:.2f}/M tokens (200M free)",
                'voyage_standard': f"${self.PRICING['voyage_3_5']:.2f}/M tokens (200M free)",
                'voyage_large': f"${self.PRICING['voyage_3_large']:.2f}/M tokens (200M free)",
                'ollama': 'FREE (unlimited)'
            }
        }

    def clear_old_records(self, days: int = 90):
        """Clear usage records older than specified days."""
        cutoff = time.time() - (days * 86400)

        cursor = self.conn.execute('''
            DELETE FROM token_usage WHERE timestamp < ?
        ''', (cutoff,))

        deleted = cursor.rowcount
        self.conn.commit()

        return deleted
