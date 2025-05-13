from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `leadscore`;
        DROP TABLE IF EXISTS `calltranscription`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
