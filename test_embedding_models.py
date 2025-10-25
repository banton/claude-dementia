#!/usr/bin/env python3
"""Compare all three embedding models for quality and performance."""

import sys
import time
sys.path.insert(0, '.')
from src.services.ollama_embedding_service import OllamaEmbeddingService

# Test cases with expected similarities
test_cases = [
    {
        "name": "Authentication (similar concepts)",
        "text1": "JWT authentication with OAuth2 required",
        "text2": "OAuth authentication using JSON Web Tokens",
        "expected": "high"  # Should be >0.7
    },
    {
        "name": "Database vs Auth (different domains)",
        "text1": "JWT authentication with OAuth2 required",
        "text2": "Database connection pooling configuration",
        "expected": "low"  # Should be <0.4
    },
    {
        "name": "Code similarity (Python vs JavaScript)",
        "text1": "def calculate_total(items): return sum(item.price for item in items)",
        "text2": "function calculateTotal(items) { return items.reduce((sum, item) => sum + item.price, 0); }",
        "expected": "high"  # Same logic, different language
    },
    {
        "name": "Context relevance",
        "text1": "User authentication system with JWT tokens and OAuth2 integration for secure API access",
        "text2": "How do we handle user login and API authentication?",
        "expected": "medium"  # Should be 0.5-0.7
    }
]

models = [
    {"name": "nomic-embed-text", "dimensions": 768},
    {"name": "embeddinggemma:300m", "dimensions": None},  # Will detect
    {"name": "qwen3-embedding:8b", "dimensions": None}
]

print("=" * 80)
print("EMBEDDING MODEL COMPARISON")
print("=" * 80)
print()

results = {}

for model_info in models:
    model_name = model_info["name"]
    print(f"\n{'=' * 80}")
    print(f"Testing: {model_name}")
    print(f"{'=' * 80}\n")

    service = OllamaEmbeddingService(model=model_name)

    if not service.enabled:
        print(f"✗ Model {model_name} not available")
        continue

    print(f"✓ Model loaded")
    print(f"  Dimensions: {service.dimensions}")

    model_results = {
        "dimensions": service.dimensions,
        "tests": [],
        "avg_time": 0
    }

    total_time = 0
    test_count = 0

    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"  Expected: {test['expected']} similarity")

        # Measure time for first embedding
        start = time.time()
        emb1 = service.generate_embedding(test['text1'])
        time1 = time.time() - start

        # Measure time for second embedding
        start = time.time()
        emb2 = service.generate_embedding(test['text2'])
        time2 = time.time() - start

        avg_time = (time1 + time2) / 2
        total_time += avg_time
        test_count += 1

        if emb1 and emb2:
            similarity = service.cosine_similarity(emb1, emb2)

            # Check if result matches expectation
            result = "✓"
            if test['expected'] == "high" and similarity > 0.7:
                result = "✓"
            elif test['expected'] == "medium" and 0.5 <= similarity <= 0.7:
                result = "✓"
            elif test['expected'] == "low" and similarity < 0.4:
                result = "✓"
            else:
                result = "?"  # Unexpected but not necessarily wrong

            print(f"  {result} Similarity: {similarity:.3f} (avg time: {avg_time*1000:.0f}ms)")

            model_results['tests'].append({
                "name": test['name'],
                "similarity": similarity,
                "time_ms": avg_time * 1000,
                "matches_expectation": result == "✓"
            })
        else:
            print(f"  ✗ Failed to generate embeddings")

    if test_count > 0:
        model_results['avg_time'] = total_time / test_count
        print(f"\nAverage embedding time: {model_results['avg_time']*1000:.0f}ms")

    results[model_name] = model_results

# Summary comparison
print("\n" + "=" * 80)
print("SUMMARY COMPARISON")
print("=" * 80)
print()

print(f"{'Model':<30} {'Dimensions':<12} {'Avg Time':<12} {'Quality Score'}")
print("-" * 80)

for model_name, data in results.items():
    if not data.get('tests'):
        continue

    # Calculate quality score (% of tests matching expectations)
    quality = sum(1 for t in data['tests'] if t['matches_expectation']) / len(data['tests']) * 100

    print(f"{model_name:<30} {data['dimensions']:<12} {data['avg_time']*1000:>8.0f}ms    {quality:>5.0f}%")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print()

# Find best by speed and quality
if results:
    fastest = min(results.items(), key=lambda x: x[1].get('avg_time', float('inf')))
    print(f"⚡ Fastest: {fastest[0]} ({fastest[1]['avg_time']*1000:.0f}ms avg)")

    # Best quality (most tests matching expectations)
    best_quality = max(
        results.items(),
        key=lambda x: sum(1 for t in x[1].get('tests', []) if t['matches_expectation'])
    )
    quality_pct = sum(1 for t in best_quality[1]['tests'] if t['matches_expectation']) / len(best_quality[1]['tests']) * 100
    print(f"🎯 Best Quality: {best_quality[0]} ({quality_pct:.0f}% accuracy)")

    # Recommended (balance of speed and quality)
    print()
    print("💡 Recommendation:")
    print("   - For speed: Use smallest/fastest model")
    print("   - For quality: Use model with best accuracy on test cases")
    print("   - For production: Balance size, speed, and accuracy")

print()
