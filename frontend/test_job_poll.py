from job_poll import poll_decision


def test_poll_decision_done_on_success():
    assert poll_decision("SUCCESS", 1, 10) == "done"


def test_poll_decision_failed_on_failure():
    assert poll_decision("FAILURE", 1, 10) == "failed"


def test_poll_decision_continue_while_pending_under_cap():
    assert poll_decision("PENDING", 1, 10) == "continue"
    assert poll_decision("STARTED", 5, 10) == "continue"


def test_poll_decision_giveup_at_cap():
    assert poll_decision("PENDING", 10, 10) == "giveup"
    assert poll_decision("STARTED", 11, 10) == "giveup"
