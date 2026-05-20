import asyncio
from app.services.scraper.mapper import _map_row_fields, _parse_datetime_fields
from app.services.scraper.single_sync import run_scraper_for_service, run_all_scrapers
from app.services.scraper.batch_sync import run_scraper_for_service_with_rows

__all__ = [
    "_map_row_fields",
    "_parse_datetime_fields",
    "run_scraper_for_service",
    "run_all_scrapers",
    "run_scraper_for_service_with_rows",
]

if __name__ == "__main__":
    asyncio.run(run_all_scrapers())
