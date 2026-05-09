import pytest
from utils.redis_utils import get_lock_key, acquire_lock

def test_happy_path(mock_redis, mock_llm, mock_gitops):
    """Scenario: End-to-end successful pipeline run."""
    # Import inside to ensure they pick up mocks
    from worker import run_pipeline, resume_pipeline
    
    chat_id = 12345
    message = {
        "chat": {"id": chat_id},
        "text": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }

    # Simulate api.py behavior (set lock)
    acquire_lock(chat_id)
    assert mock_redis.exists(get_lock_key(chat_id))

    # 1. Start Pipeline
    print("\n--- STEP 1: START PIPELINE ---")
    run_pipeline(message)
    
    # Check if thread was created
    thread_id_bytes = mock_redis.get(f"thread_{chat_id}")
    assert thread_id_bytes is not None
    assert mock_redis.exists(get_lock_key(chat_id)) # Still locked

    # 2. Resume with Approval (References)
    print("\n--- STEP 2: APPROVE REFERENCES ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 1, "text": "References..."},
        "data": "approve",
        "id": "cb1"
    })

    # 3. Resume with Approval (Research)
    print("\n--- STEP 3: APPROVE RESEARCH ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 2, "text": "Research..."},
        "data": "approve",
        "id": "cb2"
    })

    # 4. Resume with Selection (Creative)
    print("\n--- STEP 4: SELECT STORYLINE ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 3, "text": "Storylines..."},
        "data": "0", # Select first story
        "id": "cb3"
    })

    # Verify final success
    assert not mock_redis.exists(get_lock_key(chat_id))
    print("\n[SUCCESS] Happy path completed successfully!")

def test_revise_path(mock_redis, mock_llm, mock_gitops):
    """Scenario: User requests revision of references before approving."""
    from worker import run_pipeline, resume_pipeline, resume_with_text
    
    chat_id = 12345
    message = {
        "chat": {"id": chat_id},
        "text": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }

    acquire_lock(chat_id)

    # 1. Start Pipeline
    print("\n--- STEP 1: START ---")
    run_pipeline(message)

    # 2. Click Revise Button
    print("\n--- STEP 2: CLICK REVISE ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 1},
        "data": "revise",
        "id": "cb1"
    })

    # 3. Send Revision Text
    print("\n--- STEP 3: SEND REVISION TEXT ---")
    resume_with_text({
        "chat": {"id": chat_id},
        "text": "Make it more focused on Python."
    })

    # 4. Approve revised references
    print("\n--- STEP 4: APPROVE REVISED ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 1},
        "data": "approve",
        "id": "cb2"
    })

    # 5. Approve Research
    print("\n--- STEP 5: APPROVE RESEARCH ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 2},
        "data": "approve",
        "id": "cb3"
    })

    # 6. Select Storyline
    print("\n--- STEP 6: SELECT STORYLINE ---")
    resume_pipeline({
        "message": {"chat": {"id": chat_id}, "message_id": 3},
        "data": "1",
        "id": "cb4"
    })

    print("\n[SUCCESS] Revise path completed successfully!")

def test_error_handling(mock_redis, mock_llm):
    """Scenario: Simulate a crash in a node and verify cleanup."""
    from worker import run_pipeline
    
    chat_id = 12345
    message = {
        "chat": {"id": chat_id},
        "text": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }

    acquire_lock(chat_id)

    # Force an error in LLM for this test
    mock_llm.side_effect = Exception("Simulated LLM Crash")

    print("\n--- STEP 1: START (EXPECTING CRASH) ---")
    with pytest.raises(Exception):
        run_pipeline(message)

    # Verify lock was released by the decorator
    assert not mock_redis.exists(get_lock_key(chat_id))
    print("\n[SUCCESS] Error handling and cleanup verified!")
