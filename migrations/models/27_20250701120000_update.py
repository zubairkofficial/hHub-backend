from tortoise import BaseDBAsyncClient

async def upgrade(db: BaseDBAsyncClient) -> str:
    # Check if the column exists (this would need custom logic in Python)
    # Example: You could query information_schema.columns to check if the column exists first.
    return '''
        -- Drop the image_url column if it exists
        ALTER TABLE `business_post` DROP COLUMN `image_url`;
        -- Add the image_id column
        ALTER TABLE `business_post` ADD `image_id` LONGTEXT;
    '''

async def downgrade(db: BaseDBAsyncClient) -> str:
    return '''
        -- Drop the image_id column if it exists
        ALTER TABLE `business_post` DROP COLUMN `image_id`;
        -- Add the image_url column
        ALTER TABLE `business_post` ADD `image_url` LONGTEXT;
    '''
