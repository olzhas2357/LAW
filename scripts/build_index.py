import asyncio

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
    mode = "semantic + lexical" if search.document_vectors is not None else "lexical fallback"
    print(f"Loaded {len(dataset.records)} records, {len(dataset.topics)} topics; search mode: {mode}")


if __name__ == "__main__":
    asyncio.run(main())
