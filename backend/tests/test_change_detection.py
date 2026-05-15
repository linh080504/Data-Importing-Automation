from types import SimpleNamespace


def decide_should_process_ai(changed: bool) -> bool:
    return changed


def test_no_change_skips_ai() -> None:
    result = SimpleNamespace(action="NO_CHANGE", changed=False)

    assert decide_should_process_ai(result.changed) is False


def test_changed_record_continues_to_ai() -> None:
    result = SimpleNamespace(action="UPDATED", changed=True)

    assert decide_should_process_ai(result.changed) is True
