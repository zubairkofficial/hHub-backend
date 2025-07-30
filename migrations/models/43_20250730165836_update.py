from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_prompt_settings` ADD `fal_ai_api_key` LONGTEXT;
        ALTER TABLE `post_prompt_settings` ADD `openai_api_key` LONGTEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `post_prompt_settings` DROP COLUMN `fal_ai_api_key`;
        ALTER TABLE `post_prompt_settings` DROP COLUMN `openai_api_key`;"""
