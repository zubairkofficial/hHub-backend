from tortoise import BaseDBAsyncClient

async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_prompts` 
        ADD COLUMN `message_prompt` LONGTEXT NULL;
    """
