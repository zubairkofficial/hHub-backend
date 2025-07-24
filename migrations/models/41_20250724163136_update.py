from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `image_settings` ADD `image_mood` VARCHAR(32);
        ALTER TABLE `image_settings` ADD `focus_area` VARCHAR(32);
        ALTER TABLE `image_settings` ADD `lighting_effects` VARCHAR(32);
        ALTER TABLE `image_settings` ADD `background_type` VARCHAR(32);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `image_settings` DROP COLUMN `image_mood`;
        ALTER TABLE `image_settings` DROP COLUMN `focus_area`;
        ALTER TABLE `image_settings` DROP COLUMN `lighting_effects`;
        ALTER TABLE `image_settings` DROP COLUMN `background_type`;"""
