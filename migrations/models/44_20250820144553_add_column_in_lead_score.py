from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` ADD `type` VARCHAR(50);
        ALTER TABLE `lead_score` ADD `potential_score` DOUBLE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` DROP COLUMN `type`;
        ALTER TABLE `lead_score` DROP COLUMN `potential_score`;"""
