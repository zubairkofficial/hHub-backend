from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_draft` ADD `title` VARCHAR(255);
        ALTER TABLE `post_draft` ADD `description` LONGTEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_draft` DROP COLUMN `title`;
        ALTER TABLE `post_draft` DROP COLUMN `description`;"""
