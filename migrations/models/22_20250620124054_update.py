from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_prompts` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `system_prompt` LONGTEXT NOT NULL,
    `analytics_prompt` LONGTEXT NOT NULL,
    `summery_score` LONGTEXT NOT NULL,
    `hour` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `jobtracker` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `job_name` VARCHAR(255) NOT NULL,
    `last_run_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `jobtracker`;
        DROP TABLE IF EXISTS `system_prompts`;"""
