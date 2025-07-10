from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` ADD `source` VARCHAR(32) NOT NULL DEFAULT 'auto';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` DROP COLUMN `source`;"""
