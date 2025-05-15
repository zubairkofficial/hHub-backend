from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `lead_score` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `call_id` VARCHAR(255) NOT NULL,
    `call_recording` LONGTEXT,
    `name` VARCHAR(255),
    `date` DATETIME(6),
    `source_type` VARCHAR(255),
    `phone_number` VARCHAR(50),
    `duration` INT,
    `country` VARCHAR(10),
    `state` VARCHAR(10),
    `city` VARCHAR(100),
    `answer` INT,
    `first_call` INT,
    `lead_status` INT,
    `call_highlight` INT,
    `transcription` LONGTEXT,
    `note` LONGTEXT,
    `created_at` DATETIME(6),
    `updated_at` DATETIME(6),
    `deleted_at` DATETIME(6),
    `tone_score` DOUBLE,
    `intent_score` DOUBLE,
    `urgency_score` DOUBLE,
    `overall_score` DOUBLE,
    `priority` VARCHAR(50),
    `priority_level` INT
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `lead_score`;"""
