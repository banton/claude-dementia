# Custom Connector Test Prompt for Claude.ai

Copy and paste this into Claude.ai to test the dementia MCP Custom Connector:

---

## Test Prompt

```
Hi! I'd like to test my dementia MCP custom connector. Please help me verify it's working by doing the following:

1. List all my projects using the dementia tools

2. Switch to or create a project called "test-connector"

3. Lock a simple context in this project with:
   - Topic: "test_context"
   - Content: "This is a test context to verify the Custom Connector is working properly. Current time: [insert current time]"
   - Tags: "test,connector,verification"

4. Recall the context you just locked to verify it was stored correctly

5. Show me the context dashboard for this project

6. Finally, tell me what you learned about how the dementia memory system works

Please use the dementia MCP tools for all of these steps and show me the results of each operation.
```

---

## What This Tests

✅ **Tool Discovery** - Verifies Claude can see and access dementia tools
✅ **Project Management** - Tests list_projects, switch_project, create_project
✅ **Context Operations** - Tests lock_context and recall_context
✅ **Dashboard Access** - Tests context_dashboard
✅ **Error Handling** - Shows if any tools fail or return errors

## Expected Results

If working correctly, you should see:
- Claude using dementia tools (look for tool use blocks)
- Successful responses from each tool
- The locked context being recalled accurately
- A dashboard summary of the test project

## Troubleshooting

If tools don't appear or fail:
- Check Custom Connector is still connected (green checkmark)
- Verify deployment is ACTIVE: `doctl apps get-deployment 20c874aa-0ed2-44e3-a433-699f17d88a44 e882b7ba-06f5-4e25-89c7-9a3f9f87d054 --format Phase,Progress`
- Check recent logs for errors: `doctl apps logs 20c874aa-0ed2-44e3-a433-699f17d88a44 --type run --tail 50`
