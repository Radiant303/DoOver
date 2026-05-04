from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from graph.nodes import (
    background_node,
    init_world_params,
    intake_node,
    login_success_node,
    should_continue,
    should_wait_for_user,
    wait_user_node,
    agent_node,
    turn_node,
    user_choice_node,
    create_role_node,
    continue_to_roles,
    role_node,
    analyze_interaction_node,
    wait_for_interaction_node,
    should_wait_for_role_interaction,
    continue_next_node,
    judge_continue_node,
    should_continue_storyline
)
from graph.state import AgentState
from tools.registry import active_tools,interact_with_role

def build_guest_app():
    guest = StateGraph(AgentState)

    guest.add_node("init_world_params", init_world_params)
    guest.add_node("intake_node", intake_node)
    guest.add_node("background_node", background_node)
    guest.add_node("tool_node", ToolNode(tools=active_tools))
    guest.add_node("wait_user_node", wait_user_node)
    guest.add_node("agent_node", agent_node)
    guest.add_node("turn_node",turn_node)
    guest.add_node("user_choice_node", user_choice_node)
    guest.add_node("role_node", role_node)
    guest.add_node("create_role_node", create_role_node)
    guest.add_node("analyze_interaction_node",analyze_interaction_node)
    guest.add_node("tool_node2", ToolNode(tools=[interact_with_role]))
    guest.add_node("wait_for_interaction_node", wait_for_interaction_node)
    guest.add_node("continue_next_node", continue_next_node)
    guest.set_entry_point("init_world_params")

    guest.add_edge("init_world_params", "intake_node")
    guest.add_edge("intake_node", "background_node")
    guest.add_edge("background_node", "agent_node")
    guest.add_node("tool_node3", ToolNode(tools=[interact_with_role]))
    guest.add_node("wait_for_interaction_from_continue", wait_for_interaction_node)
    guest.add_node("judge_continue_node", judge_continue_node)
    guest.add_conditional_edges(
        "agent_node",
        should_continue,
        {
            "continue": "tool_node",
            "end": "turn_node",
        },
    )
    guest.add_conditional_edges(
        "tool_node",
        should_wait_for_user,
        {
            "wait": "wait_user_node",
            "continue": "background_node",
        },
    )
    guest.add_edge("wait_user_node", "background_node")
    guest.add_edge("turn_node", "user_choice_node")
    guest.add_edge("user_choice_node", "create_role_node")
    guest.add_conditional_edges("create_role_node", continue_to_roles, ["role_node"])
    guest.add_edge("role_node", "analyze_interaction_node")
    guest.add_conditional_edges(
        "analyze_interaction_node",
        should_continue,
        {
            "continue": "tool_node2",
            "end": "continue_next_node",
        },
    )
    guest.add_conditional_edges(
        "tool_node2",
        should_wait_for_role_interaction,
        {
            "wait": "wait_for_interaction_node",
            "continue": "analyze_interaction_node",
        },
    )
    guest.add_edge("wait_for_interaction_node", "analyze_interaction_node")
    guest.add_conditional_edges(
        "continue_next_node",
        should_continue,
        {
            "continue": "tool_node3",
            "end": "judge_continue_node",
        },
    )
    guest.add_conditional_edges(
        "tool_node3",
        should_wait_for_role_interaction,
        {
            "wait": "wait_for_interaction_from_continue",
            "continue": "continue_next_node",
        },
    )
    guest.add_conditional_edges(
    "judge_continue_node",
    should_continue_storyline,
    {
        "continue": "continue_next_node",
        "end": END,
    },
    )
    guest.add_edge("wait_for_interaction_from_continue", "continue_next_node")
    return guest.compile()



def build_auth_app():

    auth = StateGraph(AgentState)
    auth.add_node("login_success_node", login_success_node)
    auth.add_node("init_world_params", init_world_params)
    auth.add_node("intake_node", intake_node)
    auth.add_node("background_node", background_node)
    auth.add_node("tool_node", ToolNode(tools=active_tools))
    auth.add_node("wait_user_node", wait_user_node)
    auth.add_node("agent_node", agent_node)
    auth.add_node("turn_node",turn_node)
    auth.add_node("user_choice_node", user_choice_node)
    auth.add_node("role_node", role_node)
    auth.add_node("create_role_node", create_role_node)
    auth.add_node("analyze_interaction_node",analyze_interaction_node)
    auth.add_node("tool_node2", ToolNode(tools=[interact_with_role]))
    auth.add_node("wait_for_interaction_node", wait_for_interaction_node)
    auth.add_node("continue_next_node", continue_next_node)
    auth.add_node("tool_node3", ToolNode(tools=[interact_with_role]))
    auth.add_node("wait_for_interaction_from_continue", wait_for_interaction_node)
    auth.add_node("judge_continue_node", judge_continue_node)
    auth.set_entry_point("login_success_node")
    auth.add_edge("login_success_node", "init_world_params")

    auth.add_edge("init_world_params", "intake_node")
    auth.add_edge("intake_node", "background_node")
    auth.add_edge("background_node", "agent_node")

    auth.add_conditional_edges(
        "agent_node",
        should_continue,
        {
            "continue": "tool_node",
            "end": "turn_node",
        },
    )
    auth.add_conditional_edges(
        "tool_node",
        should_wait_for_user,
        {
            "wait": "wait_user_node",
            "continue": "background_node",
        },
    )
    auth.add_edge("wait_user_node", "background_node")
    auth.add_edge("turn_node", "user_choice_node")
    auth.add_edge("user_choice_node", "create_role_node")
    auth.add_conditional_edges("create_role_node", continue_to_roles, ["role_node"])
    auth.add_edge("role_node", "analyze_interaction_node")
    auth.add_conditional_edges(
        "analyze_interaction_node",
        should_continue,
        {
            "continue": "tool_node2",
            "end": "continue_next_node",
        },
    )
    auth.add_conditional_edges(
        "tool_node2",
        should_wait_for_role_interaction,
        {
            "wait": "wait_for_interaction_node",
            "continue": "analyze_interaction_node",
        },
    )
    auth.add_edge("wait_for_interaction_node", "analyze_interaction_node")
    auth.add_conditional_edges(
        "continue_next_node",
        should_continue,
        {
            "continue": "tool_node3",
            "end": "judge_continue_node",
        },
    )
    auth.add_conditional_edges(
        "tool_node3",
        should_wait_for_role_interaction,
        {
            "wait": "wait_for_interaction_from_continue",
            "continue": "continue_next_node",
        },
    )
    auth.add_conditional_edges(
        "judge_continue_node",
        should_continue_storyline,
        {
            "continue": "continue_next_node",
            "end": END,
        },
    )
    auth.add_edge("wait_for_interaction_from_continue", "continue_next_node")
    return auth.compile()


__all__ = [
    "build_guest_app",
    "build_auth_app"
]
