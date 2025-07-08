from datetime import datetime, timedelta
from helper.tortoise_config import TORTOISE_CONFIG
from tortoise import Tortoise
from helper.business_post_helper import BusinessPostHelper
from models.post_settings import PostSettings
from models.business_post import BusinessPost

async def run_business_post_job():
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    try:
        current_time = datetime.now()
        all_settings = await PostSettings.all()
        helper = BusinessPostHelper()
        for settings in all_settings:
            user_id = settings.user_id
            freq = (settings.frequency or 'daily').lower()
            num_posts = settings.posts_per_period or 1

            # Determine period start for uniqueness
            if freq == 'daily':
                period_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                should_generate = True
            elif freq == 'weekly':
                period_start = current_time - timedelta(days=current_time.weekday())
                period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
                today = current_time.strftime('%A')
                should_generate = settings.weekly_days and today in settings.weekly_days
            elif freq == 'monthly':
                period_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                today_str = current_time.strftime('%Y-%m-%d')
                should_generate = settings.monthly_dates and today_str in settings.monthly_dates
            else:
                period_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                should_generate = True

            if not should_generate:
                continue

            # Count all posts for this user in this period
            already_created = await BusinessPost.filter(
                user_id=user_id,
                created_at__gte=period_start
            ).count()

            if already_created >= num_posts:
                print(f"[Post Generation] {num_posts} posts already created for user {user_id} for this period. No new posts generated.")
            else:
                for i in range(num_posts - already_created):
                    # Generate post text
                    post_text = await helper.generate_post(
                        settings.business_idea,
                        settings.brand_guidelines,
                        getattr(settings, 'extracted_file_text', None)
                    )
                    
                    # Generate image if brand guidelines or extracted file text are provided
                    image_id = None
                    if settings.brand_guidelines or getattr(settings, 'extracted_file_text', None):
                        try:
                            image_id = await helper.generate_image(
                                settings.business_idea,
                                settings.brand_guidelines,
                                getattr(settings, 'extracted_file_text', None)
                            )
                            if image_id:
                                print(f"[Image Generation] Generated image for user {user_id}")
                                # BusinessPostHelper.display_image_helper(image_id)
                            else:
                                print(f"[Image Generation] No image generated for user {user_id}")
                        except Exception as e:
                            print(f"[Image Generation] Error generating image for user {user_id}: {str(e)}")
                    
                    # Create the post with image_id if available
                    await BusinessPost.create(
                        user_id=user_id,
                        post=post_text,
                        status='posted',
                        image_id=image_id
                    )
                    print(f"[Post Generation] Created new post for user {user_id} for period starting {period_start}.")
    finally:
        await Tortoise.close_connections()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_business_post_job()) 