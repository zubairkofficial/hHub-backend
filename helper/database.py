import aiomysql
from typing import List, Dict, Tuple, Any
from helper.call_processor import CallProcessor
from models.lead_score import LeadScore
from urllib.parse import urlparse, parse_qs
import re
from fastapi import HTTPException
import os
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self) -> None:
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT'))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.db = os.getenv('DB_NAME')

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


    async def create_lead_score_table(self):
        """
        Create the lead_score table with all required fields
        """
        create_table_query = """
        CREATE TABLE IF NOT EXISTS lead_score (
            id INT AUTO_INCREMENT PRIMARY KEY,
            call_id VARCHAR(255) NOT NULL,
            name VARCHAR(255),
            date DATETIME,
            source_type VARCHAR(255),
            phone_number VARCHAR(50),
            duration INT,
            country VARCHAR(10),
            state VARCHAR(10),
            city VARCHAR(100),
            answer TINYINT,
            first_call TINYINT,
            lead_status TINYINT,
            call_highlight TINYINT,
            transcription TEXT,
            note TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            deleted_at DATETIME,
            tone_score FLOAT,
            intent_score FLOAT,
            urgency_score FLOAT,
            overall_score FLOAT,
        )
        """
        await self.execute(create_table_query)

    async def sync_callrail_to_lead_score(self):
        """
        Sync all data from callrails to lead_score table (using ORM, including call_recording links).
        Returns the count of new rows inserted.
        """
        callrail_data = await self.fetch("SELECT * FROM callrails LIMIT 7")
        print(f"Call rail data  == {callrail_data}")
        inserted_count = 0
        for record in callrail_data:
            callrail_record_id = record.get('id')  # Use the unique PK from callrails
            callrail_id = record.get('callrail_id')  # Use the string ID from callrails
            if not callrail_record_id or not callrail_id:
                continue
            exists = await LeadScore.filter(callrail_record_id=callrail_record_id).first()
            if exists:
                continue
            await LeadScore.create(
                callrail_record_id=callrail_record_id,
                callrail_id=callrail_id,
                call_recording=record.get('call_recording'),
                name=record.get('name'),
                date=record.get('date'),
                source_type=record.get('source_type'),
                phone_number=record.get('phone_number'),
                duration=record.get('duration'),
                country=record.get('country'),
                state=record.get('state'),
                city=record.get('city'),
                answer=record.get('answer'),
                first_call=record.get('first_call'),
                lead_status=record.get('lead_status'),
                call_highlight=record.get('call_highlight'),
                transcription=None,
                note=record.get('note'),
                created_at=record.get('created_at'),
                updated_at=record.get('updated_at'),
                deleted_at=record.get('deleted_at'),
                tone_score=None,
                intent_score=None,
                urgency_score=None,
                overall_score=None
            )
            inserted_count += 1
        return inserted_count

    def extract_call_id_from_url(self, url: str):
        match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
        if match:
            return match.group(1)
        return None

    async def batch_transcribe_lead_score(self):
        """
        For each row in lead_score with no transcription, use the process_calling logic:
        - Use the call_id and fixed account_id to get the real recording URL from the CallRail API (with Bearer token from .env)
        - Download and transcribe the audio
        - Save the transcription in lead_score.transcription
        Returns the count of new transcriptions made.
        """
        processor = CallProcessor()
        FIXED_ACCOUNT_ID = "562206937"
        rows = await LeadScore.filter(transcription__isnull=True).all()
        transcribed_count = 0
        for row in rows:
            recording_url = row.call_recording
            if not recording_url:
                print(f"[batch_transcribe] Skipping row {row.id}: no call_recording URL")
                continue
            call_id = self.extract_call_id_from_url(recording_url)
            if not call_id:
                print(f"[batch_transcribe] Skipping row {row.id}: could not extract call_id from URL")
                continue
            print(f"[batch_transcribe] Processing row {row.id} with call_id: {call_id}")
            try:
                result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
                if result.get('status') == 'error' or 'error' in result:
                    print(f"[batch_transcribe] Failed to process call for row {row.id}: {result.get('error')}")
                    continue
                await LeadScore.filter(id=row.id).update(transcription=result['transcription'])
                print(f"[batch_transcribe] Transcription saved for row {row.id}")
                transcribed_count += 1
            except HTTPException as e:
                if getattr(e, 'status_code', None) == 404:
                    print(f"[batch_transcribe] Row {row.id}: Lead score not found (404), skipping.")
                    continue
                else:
                    print(f"[batch_transcribe] Row {row.id}: HTTPException: {e.detail}")
                    continue
            except Exception as e:
                print(f"[batch_transcribe] Row {row.id}: Unexpected error: {e}")
                continue
        return transcribed_count
