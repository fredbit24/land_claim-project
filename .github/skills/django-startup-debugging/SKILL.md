---
name: django-startup-debugging
description: 'Debug Django startup and runserver failures in this project. Use when the app fails to start, Django raises ImportError or ModuleNotFoundError, or the command is being run from the wrong directory.'
---

# Django Startup Debugging

## When to Use
- The project fails to start with `python manage.py runserver` or `python3 manage.py runserver`
- Django reports missing modules, import errors, or path issues
- The command appears to be run from the wrong folder or with the wrong interpreter

## Goal
Restore a working local Django startup by identifying the real cause before changing code.

## Procedure
1. Confirm the working directory.
   - The Django project root should contain `manage.py`.
   - In this workspace, the correct folder is the one that contains [manage.py](../../manage.py).
2. Run the server from the correct folder.
   - Use `python manage.py runserver` or `python3 manage.py runserver` only after changing into the project root.
3. Read the full error output carefully.
   - Do not guess from a truncated stack trace.
   - Note the exact exception, module name, and file path.
4. Check whether the error is environmental or project-related.
   - Missing Python packages often cause `ModuleNotFoundError`.
   - Wrong working directory often causes `can't open file 'manage.py'`.
5. Verify dependencies.
   - Inspect [requirements.txt](../../requirements.txt) and install anything missing before retrying.
6. Verify the Django project path and settings.
   - Ensure the command is executed from the same directory that contains [manage.py](../../manage.py) and the [landclaim/settings.py](../../landclaim/settings.py) project package.
7. Re-run the server and confirm the startup message.
   - A successful run should show the development server address and no traceback.

## Completion Checklist
- The command is being run from the correct project root.
- The relevant dependency file has been checked.
- The startup error is understood before making code changes.
- The server starts without a traceback.
