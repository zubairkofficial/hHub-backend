from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` MODIFY COLUMN `callrail_id` VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` MODIFY COLUMN `callrail_id` VARCHAR(255) NOT NULL;"""
