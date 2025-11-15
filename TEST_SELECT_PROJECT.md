# Test Prompt for Claude Desktop

Copy and paste this into Claude Desktop to test the `select_project_for_session` fix:

---

Please test the Dementia MCP connection by doing the following steps:

1. Call `list_projects()` to see available projects
2. Call `select_project_for_session("linkedin")` to select the linkedin project
3. Let me know if you get any errors or if it succeeds

I need to verify that the recent bug fixes are working in production.

---

**Expected Result:**
- `list_projects()` should return a list including "linkedin"
- `select_project_for_session("linkedin")` should succeed with a message like "Selected project: linkedin"

**If you see an error:**
- Copy the full error message
- Let me know exactly what failed
