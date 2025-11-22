"""
Integration tests for async tool workflows.

Tests complete workflows using multiple tools in sequence.
"""

import pytest
import json


@pytest.mark.asyncio
async def test_context_lifecycle_async():
    """Test complete context lifecycle: lock -> recall -> search -> unlock."""
    from claude_mcp_async_sessions import (
        lock_context, recall_context, search_contexts, unlock_context
    )

    project = "test_workflow"
    topic = "api_spec_async"

    # 1. Lock context
    lock_result = await lock_context(
        content="API specification for async endpoints",
        topic=topic,
        tags="api,async,test",
        project=project
    )
    lock_data = json.loads(lock_result[0].text)
    assert lock_data['status'] == 'success'

    # 2. Recall context
    recall_result = await recall_context(topic=topic, project=project)
    recalled = json.loads(recall_result[0].text)
    assert recalled['topic'] == topic
    assert 'async endpoints' in recalled['content']

    # 3. Search for context
    search_result = await search_contexts(
        query="async endpoints",
        project=project
    )
    search_data = json.loads(search_result[0].text)
    assert len(search_data['results']) > 0

    # 4. Unlock context
    unlock_result = await unlock_context(topic=topic, project=project)
    unlock_data = json.loads(unlock_result[0].text)
    assert unlock_data['deleted_count'] >= 1


@pytest.mark.asyncio
async def test_project_management_workflow():
    """Test project creation and switching."""
    from claude_mcp_async_sessions import (
        create_project, list_projects, get_project_info
    )

    test_project_name = "test_async_project"

    # 1. Create project
    create_result = await create_project(name=test_project_name)
    create_data = json.loads(create_result[0].text)
    assert create_data['status'] == 'success'

    # 2. List projects
    list_result = await list_projects()
    list_data = json.loads(list_result[0].text)
    assert len(list_data['projects']) > 0
    assert any(p['project_name'] == test_project_name for p in list_data['projects'])

    # 3. Get project info
    info_result = await get_project_info(name=test_project_name)
    info_data = json.loads(info_result[0].text)
    assert info_data['project_name'] == test_project_name


@pytest.mark.asyncio
async def test_batch_operations():
    """Test batch lock and recall operations."""
    from claude_mcp_async_sessions import (
        batch_lock_contexts, batch_recall_contexts
    )

    project = "test_batch"

    # 1. Batch lock
    contexts = [
        {"topic": f"batch_test_{i}", "content": f"Content {i}", "tags": "batch,test"}
        for i in range(3)
    ]

    lock_result = await batch_lock_contexts(contexts=contexts, project=project)
    lock_data = json.loads(lock_result[0].text)
    assert lock_data['successful'] == 3

    # 2. Batch recall (preview mode)
    topics = [f"batch_test_{i}" for i in range(3)]
    recall_result = await batch_recall_contexts(topics=topics, preview_only=True, project=project)
    recall_data = json.loads(recall_result[0].text)
    assert len(recall_data['results']) == 3
