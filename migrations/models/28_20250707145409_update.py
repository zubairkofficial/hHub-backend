from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` ADD `monthly_dates` JSON;
        ALTER TABLE `post_settings` ADD `weekly_days` JSON;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` DROP COLUMN `monthly_dates`;
        ALTER TABLE `post_settings` DROP COLUMN `weekly_days`;"""
