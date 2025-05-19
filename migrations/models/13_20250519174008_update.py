from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` DROP COLUMN `date`;
        ALTER TABLE `lead_score` DROP COLUMN `state`;
        ALTER TABLE `lead_score` DROP COLUMN `name`;
        ALTER TABLE `lead_score` DROP COLUMN `city`;
        ALTER TABLE `lead_score` DROP COLUMN `first_call`;
        ALTER TABLE `lead_score` DROP COLUMN `call_recording`;
        ALTER TABLE `lead_score` DROP COLUMN `duration`;
        ALTER TABLE `lead_score` DROP COLUMN `source_type`;
        ALTER TABLE `lead_score` DROP COLUMN `answer`;
        ALTER TABLE `lead_score` DROP COLUMN `country`;
        ALTER TABLE `lead_score` DROP COLUMN `lead_status`;
        ALTER TABLE `lead_score` DROP COLUMN `call_highlight`;
        ALTER TABLE `lead_score` DROP COLUMN `phone_number`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `lead_score` ADD `date` DATETIME(6);
        ALTER TABLE `lead_score` ADD `state` VARCHAR(10);
        ALTER TABLE `lead_score` ADD `name` VARCHAR(255);
        ALTER TABLE `lead_score` ADD `city` VARCHAR(100);
        ALTER TABLE `lead_score` ADD `first_call` INT;
        ALTER TABLE `lead_score` ADD `call_recording` LONGTEXT;
        ALTER TABLE `lead_score` ADD `duration` INT;
        ALTER TABLE `lead_score` ADD `source_type` VARCHAR(255);
        ALTER TABLE `lead_score` ADD `answer` INT;
        ALTER TABLE `lead_score` ADD `country` VARCHAR(10);
        ALTER TABLE `lead_score` ADD `lead_status` INT;
        ALTER TABLE `lead_score` ADD `call_highlight` INT;
        ALTER TABLE `lead_score` ADD `phone_number` VARCHAR(50);"""
