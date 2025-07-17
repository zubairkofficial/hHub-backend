import asyncio
from helper.job_helper import run_job  # Ensure this imports correctly from your module
# from helper.business_post_job_helper import run_business_post_job

if __name__ == "__main__":
    asyncio.run(run_job())  # Running the async job
    # asyncio.run(run_business_post_job())  # Running the business post job
