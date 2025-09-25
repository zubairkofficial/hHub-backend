from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_prompt_settings` ADD `gemini_api_key` LONGTEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_prompt_settings` DROP COLUMN `gemini_api_key`;"""
