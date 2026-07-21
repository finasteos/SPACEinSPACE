"""Charter Article 4.1 empirical guard test.

Article 4.1 in CHARTER.md:
    "Every BaseAgent subclass shall declare a non-empty capabilities list.
     A capabilities=[] agent is a ghost and shall not be allowed to run."

Status: this test makes the article empirical. Before the guard was added,
the constructor accepted [] silently. With this test passing, the
aspirational note in CHARTER.md Article 4.1 can be downgraded.
"""

from unittest.mock import MagicMock

import pytest

from agents.base_agent import BaseAgent, CharterViolationError


class _GhostProbe(BaseAgent):
    """Minimal subclass used only to exercise the Charter 4.1 guard.

    Pass-through constructor — no behaviour, just the inheritance
    point. By default registers with MagicMock stand-ins and does NOT
    subscribe to the bus.
    """

    def __init__(self, capabilities, agent_id="ghost-probe"):
        super().__init__(
            agent_id=agent_id,
            name="Ghost Probe",
            role="tester",
            capabilities=capabilities,
            db=MagicMock(),
            bus=MagicMock(),
            llm_client=MagicMock(),
            subscribe=False,
        )


def test_charter_4_1_empty_capabilities_raises():
    """Capabilities=[] declares a ghost. The constructor shall not allow it."""
    with pytest.raises(CharterViolationError) as exc:
        _GhostProbe(capabilities=[])
    assert "Charter Article 4.1" in str(exc.value)
    assert "ghost" in str(exc.value)


def test_charter_4_1_none_capabilities_raises():
    """Capabilities=None is the same ghost, by another name."""
    with pytest.raises(CharterViolationError) as exc:
        _GhostProbe(capabilities=None)
    assert "Charter Article 4.1" in str(exc.value)


def test_charter_4_1_nonempty_capabilities_succeeds():
    """Even a single capability makes a citizen, not a ghost."""
    agent = _GhostProbe(capabilities=["observe"])
    assert agent.capabilities == ("observe",)
    assert agent.agent_id == "ghost-probe"


def test_charter_4_1_capabilities_is_immutable_tuple():
    """A subclass cannot structurally clear capabilities post-construction."""
    agent = _GhostProbe(capabilities=["observe", "interject"])
    assert isinstance(agent.capabilities, tuple)
    with pytest.raises(AttributeError):
        agent.capabilities.clear()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        agent.capabilities.append("foo")  # type: ignore[attr-defined]


def test_charter_4_1_subclass_with_super_call_still_guarded():
    """A subclass that overrides __init__ but calls super().__init__ still triggers."""
    class MoreConcrete(BaseAgent):
        def __init__(self, capabilities):
            super().__init__(
                agent_id="concrete-1",
                name="Concrete",
                role="tester",
                capabilities=capabilities,
                db=MagicMock(),
                bus=MagicMock(),
                llm_client=MagicMock(),
            )

    with pytest.raises(CharterViolationError):
        MoreConcrete(capabilities=[])

    ok = MoreConcrete(capabilities=["x"])
    assert "x" in ok.capabilities


def test_charter_4_1_message_includes_agent_id_for_debuggability():
    """The exception message identifies the offending agent so operators can debug."""
    with pytest.raises(CharterViolationError) as exc:
        _GhostProbe(capabilities=[], agent_id="blender-pretender")
    assert "blender-pretender" in str(exc.value)
