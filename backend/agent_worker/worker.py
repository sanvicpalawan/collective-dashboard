# OpenCode worker will poll this queue and execute tasks here
# This is the execution engine for the AI Agency OS backend.
# When the dashboard queues a job (Lead Generation, Social Media, etc.),
# this worker picks it up, runs the corresponding script, saves data,
# and logs the result.
