from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_history` ADD `message` VARCHAR(255);
        ALTER TABLE `post_history` ADD `status` VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_history` DROP COLUMN `message`;
        ALTER TABLE `post_history` DROP COLUMN `status`;"""
