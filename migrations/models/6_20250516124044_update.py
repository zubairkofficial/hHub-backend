from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` DROP COLUMN `priority`;
        ALTER TABLE `lead_score` DROP COLUMN `priority_level`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` ADD `priority` VARCHAR(50);
        ALTER TABLE `lead_score` ADD `priority_level` INT;"""
