from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` ADD `user_id` VARCHAR(100) NOT NULL;
        ALTER TABLE `post_settings` ADD `user_id` VARCHAR(100) NOT NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` DROP COLUMN `user_id`;
        ALTER TABLE `post_settings` DROP COLUMN `user_id`;"""
