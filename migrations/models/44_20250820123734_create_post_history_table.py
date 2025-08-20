from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `post_history` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `page_name` VARCHAR(255) NOT NULL,
    `page_type` VARCHAR(9) NOT NULL COMMENT 'FACEBOOK: facebook\nINSTAGRAM: instagram',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `post_draft_id` INT NOT NULL,
    CONSTRAINT `fk_post_his_post_dra_67d9e6ba` FOREIGN KEY (`post_draft_id`) REFERENCES `post_draft` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `post_history`;"""
