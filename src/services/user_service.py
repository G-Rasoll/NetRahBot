import logging
from src.infrastructure.database import db


logger = logging.getLogger(__name__)


class UserService:

    async def register_or_update_user(self, telegram_id: int, username: str,
                                      first_name: str) -> int:

        try:
            query_check = "SELECT id, is_banned FROM users WHERE telegram_id = ?"
            user = await db.execute_query_single(query_check, (telegram_id,))

            if user:
                if user['is_banned']:
                    return -1

                query_update = "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?"
                await db.execute_non_query(query_update,
                                           (username, first_name, telegram_id))
                return user['id']


            query_insert = (
                "INSERT INTO users (telegram_id, username, first_name, balance, has_used_test_package, is_banned) "
                "VALUES (?, ?, ?, 0.0, 0, 0)"
            )
            internal_id = await db.execute_non_query(query_insert, (
            telegram_id, username, first_name))
            logger.info(
                f"New user registered: {telegram_id} with internal ID: {internal_id}")
            return internal_id

        except Exception as e:
            logger.error(f"Error in registering user {telegram_id}: {e}")
            raise e

    async def check_test_package_status(self, user_id: int) -> bool:

        query = "SELECT has_used_test_package FROM users WHERE id = ?"
        result = await db.execute_query_single(query, (user_id,))
        return result['has_used_test_package'] if result else True