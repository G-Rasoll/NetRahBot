import pyodbc
import asyncio
import logging
from typing import List, Dict, Any, Optional

from config import DB_CONNECTION_STRING

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.conn_str = DB_CONNECTION_STRING

    def _execute_query(self, query: str, params: tuple = (),
                       fetch_all: bool = False,
                       is_procedure: bool = False) -> Any:

        conn = None
        cursor = None
        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetch_all:
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

            if not fetch_all:
                conn.commit()
                try:
                    cursor.execute("SELECT @@IDENTITY AS id")
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        return int(row[0])
                except Exception:
                    pass
                return True

        except pyodbc.Error as e:
            logger.error(
                f"Database error occurred: {e} | Query: {query} | Params: {params}")
            if conn:
                conn.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    async def execute_non_query(self, query: str, params: tuple = ()) -> Any:

        return await asyncio.to_thread(self._execute_query, query, params,
                                       False)

    async def execute_query_all(self, query: str, params: tuple = ()) -> List[
        Dict[str, Any]]:

        return await asyncio.to_thread(self._execute_query, query, params, True)

    async def execute_query_single(self, query: str, params: tuple = ()) -> \
    Optional[Dict[str, Any]]:

        results = await asyncio.to_thread(self._execute_query, query, params,
                                          True)
        return results[0] if results else None


db = DatabaseManager()