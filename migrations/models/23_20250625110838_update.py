from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `business_post` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `post` LONGTEXT,
    `scheduled_time` DATETIME(6),
    `status` VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `post_settings` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `business_idea` LONGTEXT NOT NULL,
    `brand_guidelines` LONGTEXT,
    `frequency` VARCHAR(32) NOT NULL DEFAULT 'daily',
    `posts_per_period` INT NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `business_post`;
        DROP TABLE IF EXISTS `post_settings`;"""
