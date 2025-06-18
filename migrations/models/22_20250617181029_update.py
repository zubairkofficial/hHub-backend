from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` ADD `name` VARCHAR(255);
        ALTER TABLE `lead_score` ADD `phone` VARCHAR(15);
        CREATE TABLE IF NOT EXISTS `system_prompts` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `system_prompt` LONGTEXT NOT NULL,
    `analytics_prompt` LONGTEXT NOT NULL,
    `summery_score` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` DROP COLUMN `name`;
        ALTER TABLE `lead_score` DROP COLUMN `phone`;
        DROP TABLE IF EXISTS `system_prompts`;"""
