from datetime import datetime, timedelta
from helper.transcription_helper import process_unprocessed_callrails
from models.system_prompt import SystemPrompts
from models.job_tracker import JobTracker
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG

# Make the run_job function asynchronous
async def run_job():
    # Initialize Tortoise ORM
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    try:
        # Fetch the system settings from the SystemPrompts table
        system_settings = await SystemPrompts.filter().first()
        job_tracker = await JobTracker.filter(job_name="callrails_job").first()
        if not system_settings or not job_tracker:
            print("System settings or job tracker entry not found.")
            return
        current_time = datetime.now()
        last_run_time = job_tracker.last_run_time
        # Make both datetimes naive (remove timezone info if present)
        if last_run_time and last_run_time.tzinfo is not None:
            last_run_time = last_run_time.replace(tzinfo=None)
        time_difference = current_time - last_run_time
        # Convert hour to int for timedelta
        if time_difference >= timedelta(hours=int(system_settings.hour)):
            # Run the job if enough time has passed
            await process_unprocessed_callrails()

            # Update the last run time in the job tracker table
            if job_tracker:
                job_tracker.last_run_time = current_time
                await job_tracker.save()
            else:
                # If no job entry exists, create one
                await JobTracker.create(job_name="callrails_job", last_run_time=current_time)
        else:
            print(f"Job cannot be run. Time remaining: {int(system_settings.hour) - time_difference.total_seconds() // 3600} hours")
    finally:
        await Tortoise.close_connections()

# Main execution logic (to run the job)
if __name__ == "__main__":
    import asyncio
    asyncio.run(run_job())  # Running the async job
