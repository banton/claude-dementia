#!/usr/bin/env python3
"""Test cloud API services (Voyage AI + OpenRouter)."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from src.config import config
from src.services.voyage_ai_embedding_service import VoyageAIEmbeddingService
from src.services.openrouter_llm_service import OpenRouterLLMService


def test_voyage_ai():
    """Test Voyage AI embedding service."""
    print("\n" + "="*60)
    print("Testing Voyage AI Embedding Service")
    print("="*60)

    api_key = os.getenv('VOYAGEAI_API_KEY')
    if not api_key:
        print("❌ VOYAGEAI_API_KEY not found in environment")
        return False

    print(f"✓ API key loaded: {api_key[:20]}...")

    service = VoyageAIEmbeddingService(
        api_key=api_key,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions
    )

    print(f"✓ Service initialized")
    print(f"  - Model: {service.model}")
    print(f"  - Dimensions: {service.dimensions}")
    print(f"  - Enabled: {service.enabled}")

    if not service.enabled:
        print("❌ Service is not enabled (API check failed)")
        return False

    # Test embedding generation
    test_text = "This is a test document about machine learning and artificial intelligence."
    print(f"\nGenerating embedding for: '{test_text[:50]}...'")

    embedding = service.generate_embedding(test_text)

    if embedding is None:
        print("❌ Embedding generation failed")
        return False

    print(f"✓ Embedding generated successfully")
    print(f"  - Dimensions: {len(embedding)}")
    print(f"  - First 5 values: {embedding[:5]}")

    # Test cosine similarity
    embedding2 = service.generate_embedding("Machine learning is a subset of AI.")
    similarity = service.cosine_similarity(embedding, embedding2)
    print(f"\n✓ Cosine similarity test: {similarity:.4f}")

    # Get stats
    stats = service.get_stats()
    print(f"\nService stats:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")

    return True


def test_openrouter():
    """Test OpenRouter LLM service."""
    print("\n" + "="*60)
    print("Testing OpenRouter LLM Service")
    print("="*60)

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment")
        return False

    print(f"✓ API key loaded: {api_key[:20]}...")

    service = OpenRouterLLMService(
        api_key=api_key,
        default_model=config.llm_model
    )

    print(f"✓ Service initialized")
    print(f"  - Model: {service.default_model}")
    print(f"  - Enabled: {service.enabled}")

    if not service.enabled:
        print("❌ Service is not enabled (API check failed)")
        return False

    # Test chat completion
    prompt = "What is 2+2? Answer in one word."
    print(f"\nTest prompt: '{prompt}'")

    response = service.chat_completion(
        prompt=prompt,
        temperature=0.1,
        max_tokens=10
    )

    if response is None:
        print("❌ Chat completion failed")
        return False

    print(f"✓ Response: {response}")

    # Test summarization
    context = """
    This is a test context about machine learning.
    Machine learning is a subset of artificial intelligence.
    It uses algorithms to learn patterns from data.
    Deep learning is a type of machine learning using neural networks.
    """

    print(f"\nTesting context summarization...")
    summary = service.summarize_context(context, max_length=100)

    if summary:
        print(f"✓ Summary: {summary}")
    else:
        print("⚠ Summarization returned None (non-critical)")

    # Test priority classification
    print(f"\nTesting priority classification...")
    priority = service.classify_context_priority(
        "ALWAYS use TypeScript interfaces. NEVER use any type. MUST validate all inputs."
    )

    if priority:
        print(f"✓ Priority: {priority}")
    else:
        print("⚠ Priority classification returned None (non-critical)")

    # Get stats
    stats = service.get_stats()
    print(f"\nService stats:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")

    return True


def test_config():
    """Test configuration."""
    print("\n" + "="*60)
    print("Testing Configuration")
    print("="*60)

    print(f"Embedding provider: {config.embedding_provider}")
    print(f"Embedding model: {config.embedding_model}")
    print(f"Embedding dimensions: {config.embedding_dimensions}")
    print(f"LLM provider: {config.llm_provider}")
    print(f"LLM model: {config.llm_model}")
    print(f"Semantic search enabled: {config.enable_semantic_search}")
    print(f"AI summarization enabled: {config.enable_ai_summarization}")

    config_dict = config.to_dict()
    print(f"\nVoyage AI config:")
    print(f"  - Has API key: {config_dict['voyage_ai']['has_api_key']}")
    print(f"\nOpenRouter config:")
    print(f"  - Has API key: {config_dict['openrouter']['has_api_key']}")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Cloud API Service Integration Tests")
    print("="*60)

    results = []

    # Test configuration
    results.append(("Configuration", test_config()))

    # Test Voyage AI
    results.append(("Voyage AI", test_voyage_ai()))

    # Test OpenRouter
    results.append(("OpenRouter", test_openrouter()))

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    for name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(result[1] for result in results)

    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
