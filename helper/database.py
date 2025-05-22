import aiomysql
from typing import List, Dict, Tuple, Any
from helper.call_processor import CallProcessor
from helper.lead_scoring import LeadScoringService
from models.lead_score import LeadScore
from urllib.parse import urlparse, parse_qs
import re
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime

load_dotenv()

class Database:
    def __init__(self) -> None:
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT'))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.db = os.getenv('DB_NAME')
        self.processor = CallProcessor()
        self.scoring_service = LeadScoringService()


    async def connect(self):
        return await aiomysql.connect(host=self.host, port=self.port, user=self.user, password=self.password, db=self.db, cursorclass=aiomysql.DictCursor)


    async def execute(self, query: str, params: tuple = ()):
        async with await self.connect() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                await conn.commit()
                return cursor.lastrowid

    async def fetch(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = await self.connect()
        try:
            cursor = await conn.cursor()
            await cursor.execute(query, params)
            result = await cursor.fetchall()
            return result
        finally:
            await conn.ensure_closed()

    async def insert(self, table: str, data: Dict[str, Any]):
        keys = ', '.join([f"{dk}" for dk in data.keys()])
        values = tuple(data.values())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({keys}) VALUES ({placeholders})"
        return await self.execute(query, values)

    async def update(self, table: str, data: Dict[str, Any], conditions: Dict[str, Any]):
        set_clause = ', '.join([f"{key} = %s" for key in data])
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + tuple(conditions.values())
        await self.execute(query, params)

    async def delete(self, table: str, conditions: Dict[str, Any]):
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions])
        query = f"DELETE FROM {table} WHERE {where_clause}"
        params = tuple(conditions.values())
        await self.execute(query, params)

    async def all(self, table: str) -> List[Dict[str, Any]]:
        query = f"SELECT * FROM {table}"
        return await self.fetch(query)

    async def get(self, table: str, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions])
        params = tuple(conditions.values())
        query = f"SELECT * FROM {table} WHERE {where_clause}"
        return await self.fetch(query, params)

    async def first(self, table: str, conditions: Dict[str, Any]) -> Dict[str, Any]:
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions])
        params = tuple(conditions.values())
        query = f"SELECT * FROM {table} WHERE {where_clause} LIMIT 1"
        results = await self.fetch(query, params)
        return results[0] if results else None

    async def last(self, table: str, conditions: Dict[str, Any]) -> Dict[str, Any]:
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions])
        params = tuple(conditions.values())
        query = f"SELECT * FROM {table} WHERE {where_clause} ORDER BY id DESC LIMIT 1;"
        results = await self.fetch(query, params)
        return results[0] if results else None

    async def find(self, table: str, id: int) -> Dict[str, Any]:
        query = f"SELECT * FROM {table} WHERE id = %s LIMIT 1"
        results = await self.fetch(query, (id,))
        return results[0] if results else None

    async def with_relationships(self, base_table: str, relationships: List[Tuple[str, str, str, str]]) -> List[Dict[str, Any]]:
        joins = " ".join(
            f"JOIN {related_table} ON {base_table}.{base_column}={related_table}.{related_column}"
            for _, related_table, base_column, related_column in relationships
        )
        select_columns = f"{base_table}.*, " + ", ".join(
            [f"{rt}.id AS '{rt}.id', {rt}.name AS '{rt}.name'" for _, rt, _, _ in relationships])
        query = f"""
        SELECT {select_columns}
        FROM {base_table}
        {joins}
        """
        results = await self.fetch(query)
        return results
        # Manually reformat the results to nest related records
        # formatted_results = []
        # for row in results:
        #     base_record = {key: value for key, value in row.items() if not key.startswith(tuple([rt for _, rt, _, _ in relationships]))}
        #     for _, related_table, _, _ in relationships:
        #         base_record[related_table] = {key.split('.', 1)[1]: value for key, value in row.items() if key.startswith(related_table)}
        #     formatted_results.append(base_record)
        # return formatted_results

    async def insert_xml(self, filename: str, content: str):
        """
        Inserts an XML file's name and content into the export_xml table.
        """
        data = {
            'filename': filename,
            'xml_content': content
        }
        return await self.insert('export_xml', data)



    async def get_client_context_and_calls(self, client_id):
        # Get all calls for this client
        calls = await self.fetch("SELECT call_recording, state, city, first_call FROM callrails WHERE client_id = %s", (client_id,))
        # Get client type name
        client_type = None
        client_type_id = await self.fetch("SELECT client_type_id FROM clients WHERE id = %s", (client_id,))
        if client_type_id and client_type_id[0]['client_type_id']:
            ct = await self.fetch("SELECT name FROM client_types WHERE id = %s", (client_type_id[0]['client_type_id'],))
            if ct: client_type = ct[0]['name']
        # Get rota plan
        rota_plan = None
        rp = await self.fetch("SELECT plan FROM rota_plan WHERE client_id = %s", (client_id,))
        if rp: rota_plan = rp[0]['plan']
        # Get service name (try all sources)
        service = None
        s = await self.fetch("SELECT s.name FROM services s JOIN client_services cs ON s.id = cs.service_id WHERE cs.client_id = %s", (client_id,))
        if not s:
            # s = await self.fetch("SELECT s.name FROM services s JOIN lead_services ls ON s.id = ls.service_id WHERE ls.client_id = %s", (client_id,))
            if not s:
                s = await self.fetch("SELECT s.name FROM services s JOIN tasks t ON s.id = t.service_id WHERE t.client_id = %s", (client_id,))
        if s: service = s[0]['name']
        return {
            'calls': calls,
            'client_type': client_type,
            'rota_plan': rota_plan,
            'service': service
        }

    async def get_all_client_ids_with_calls(self) -> List[str]:
        """Fetches all unique client_ids from the callrails table."""
        query = "SELECT DISTINCT client_id FROM callrails WHERE client_id IS NOT NULL"
        results = await self.fetch(query)
        return [row['client_id'] for row in results if row and 'client_id' in row]
