from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` ADD `reference_images` JSON;
        ALTER TABLE `post_draft` DROP COLUMN `reference_images`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` DROP COLUMN `reference_images`;
        ALTER TABLE `post_draft` ADD `reference_images` JSON;"""
