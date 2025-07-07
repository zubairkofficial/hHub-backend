from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` ADD `uploaded_file` VARCHAR(255);
        ALTER TABLE `post_settings` ADD `extracted_file_text` LONGTEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_settings` DROP COLUMN `uploaded_file`;
        ALTER TABLE `post_settings` DROP COLUMN `extracted_file_text`;"""
