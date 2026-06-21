import logging
from src.infrastructure.database import db
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PackageService:

    async def get_active_commercial_packages(self) -> List[Dict[str, Any]]:
        """
            Get Active Packages as Database
        """
        try:
            query = (
                "SELECT id, title, volume_mb, volume_gb, price_rial "
                "FROM packages "
                "WHERE is_active = 1 AND is_test_package = 0 AND is_gift_package = 0"
            )
            return await db.execute_query_all(query)
        except Exception as e:
            logger.error(f"Error fetching active commercial packages: {e}")
            raise e

    async def get_package_by_id(self, package_id: int) -> Optional[
        Dict[str, Any]]:
        """
            Get Package By Id
        """
        try:
            query = "SELECT id, title, volume_mb, volume_gb, price_rial, is_test_package, is_active FROM packages WHERE id = ?"
            return await db.execute_query_single(query, (package_id,))
        except Exception as e:
            logger.error(f"Error fetching package by id {package_id}: {e}")
            raise e