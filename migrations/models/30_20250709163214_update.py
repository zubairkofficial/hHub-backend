from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` ADD `content` LONGTEXT;
        ALTER TABLE `business_post` ADD `is_draft` BOOL NOT NULL DEFAULT 1;
        ALTER TABLE `business_post` ADD `keywords` JSON;
        ALTER TABLE `business_post` ADD `current_step` INT NOT NULL DEFAULT 1;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `business_post` DROP COLUMN `content`;
        ALTER TABLE `business_post` DROP COLUMN `is_draft`;
        ALTER TABLE `business_post` DROP COLUMN `keywords`;
        ALTER TABLE `business_post` DROP COLUMN `current_step`;"""
