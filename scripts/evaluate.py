import asyncio
from collections import defaultdict

from bot.config import get_settings
from bot.services.data_loader import load_dataset
from bot.services.llm import create_providers
from bot.services.search import HybridSearch


async def main() -> None:
    settings = get_settings()
    dataset = load_dataset(settings.data_path)
    embedding_provider, _ = create_providers(settings)
    search = HybridSearch(dataset, settings.cache_dir, embedding_provider)
    await search.build()
    cases = [
        (variant, record.id)
        for record in dataset.records
        for variant in record.variants
        if variant.strip()
    ][:50]
    if not 40 <= len(cases) <= 60:
        raise RuntimeError(f"Evaluation requires 40–60 variant questions; found {len(cases)}")
    evaluated = []
    for query, expected_id in cases:
        results = await search.search(query, limit=5)
        rank = next((index + 1 for index, item in enumerate(results) if item.record.id == expected_id), None)
        score = results[0].score if results else 0
        evaluated.append((rank, score))
    print(f"Evaluation questions: {len(evaluated)}")
    print(f"Top-1 accuracy: {sum(rank == 1 for rank, _ in evaluated) / len(evaluated):.1%}")
    print(f"Top-3 accuracy: {sum(rank is not None and rank <= 3 for rank, _ in evaluated) / len(evaluated):.1%}")
    print("Threshold | answered | precision")
    for threshold in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        accepted = [(rank, score) for rank, score in evaluated if score >= threshold]
        precision = sum(rank == 1 for rank, _ in accepted) / len(accepted) if accepted else 0
        print(f"{threshold:>9.2f} | {len(accepted):>8} | {precision:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
