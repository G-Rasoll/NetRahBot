import pyodbc
import asyncio
import logging
from typing import List, Dict, Any, Optional
from config import DB_CONNECTION_STRING

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.conn_str = DB_CONNECTION_STRING

    def _execute_query(
            self, query: str, params: tuple = (), fetch_all: bool = False,
            is_procedure: bool = False
    ) -> Any:
        conn = None
        cursor = None
        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()
            cursor.execute(query, params)
            if fetch_all:
                all_results = []
                while True:
                    if cursor.description:
                        columns = [column[0] for column in cursor.description]
                        rows = cursor.fetchall()
                        result_set = [
                            dict(zip(columns, row)) for row in rows
                        ]
                        if result_set:
                            all_results = result_set
                    if not cursor.nextset():
                        break
                conn.commit()
                return all_results
            else:
                inserted_id = None
                try:
                    cursor.execute("SELECT SCOPE_IDENTITY()")
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        inserted_id = int(row[0])
                except Exception:
                    pass

                conn.commit()

                if inserted_id is not None:
                    return inserted_id
                return True
        except Exception as e:
            logger.exception(
                f"Database error | Query={query} | Params={params}"
            )
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


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

    async def execute_insert_return_id(
            self,
            query: str,
            params: tuple = ()
    ):
        return await asyncio.to_thread(
            self._execute_insert_return_id,
            query,
            params
        )

    def _execute_insert_return_id(
            self,
            query: str,
            params: tuple = ()
    ):
        conn = None
        cursor = None

        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()

            cursor.execute(query, params)

            row = cursor.fetchone()

            conn.commit()

            if not row:
                raise Exception(
                    "Insert executed but no identity returned."
                )

            return int(row[0])

        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass

            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

db = DatabaseManager()