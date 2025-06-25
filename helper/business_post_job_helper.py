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
        settings = await PostSettings.filter().first()
        if not settings:
            print("No post settings found.")
            return
        helper = BusinessPostHelper()
        freq = (settings.frequency or 'daily').lower()
        num_posts = settings.posts_per_period or 1

        # Determine period start for uniqueness
        if freq == 'daily':
            period_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        elif freq == 'weekly':
            period_start = current_time - timedelta(days=current_time.weekday())
            period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count all posts created in this period (regardless of status)
        already_created = await BusinessPost.filter(
            created_at__gte=period_start
        ).count()

        if already_created >= num_posts:
            print(f"[Post Generation] {num_posts} posts already created for this period. No new posts generated.")
        else:
            for i in range(num_posts - already_created):
                post_text = await helper.generate_post(settings.business_idea, settings.brand_guidelines)
                await BusinessPost.create(
                    post=post_text,
                    status='created'
                )
                print(f"[Post Generation] Created new post for period starting {period_start}.")
    finally:
        await Tortoise.close_connections()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_business_post_job()) 