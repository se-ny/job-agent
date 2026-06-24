from app.tasks import crawl_jobs_task

result = crawl_jobs_task.delay("saramin", "AI 에이전트", 2)
print("Task ID:", result.id)