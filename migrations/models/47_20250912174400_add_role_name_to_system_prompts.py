from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_prompts` ADD `role_name` VARCHAR(255);
        ALTER TABLE `system_prompts` ADD `client_id` INT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_prompts` DROP COLUMN `role_name`;
        ALTER TABLE `system_prompts` DROP COLUMN `client_id`;"""
