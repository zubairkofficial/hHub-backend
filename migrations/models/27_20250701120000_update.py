from tortoise import BaseDBAsyncClient

async def upgrade(db: BaseDBAsyncClient) -> str:
    return '''
        ALTER TABLE `business_post` DROP COLUMN IF EXISTS `image_url`;
        ALTER TABLE `business_post` ADD `image_id` LONGTEXT;
    '''

async def downgrade(db: BaseDBAsyncClient) -> str:
    return '''
        ALTER TABLE `business_post` DROP COLUMN IF EXISTS `image_id`;
        ALTER TABLE `business_post` ADD `image_url` LONGTEXT;
    ''' 