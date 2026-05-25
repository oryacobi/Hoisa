# MongoDB Init Scripts

This directory is mounted read-only at `/docker-entrypoint-initdb.d` for future
local initialization scripts.

Do not add schema creation, index creation, application users, target-repo data,
or real credentials in this issue. MongoDB entrypoint init scripts run only
when the data directory is empty, so future scripts must document their own
first-run behavior and approval scope.
