import json
from typing import Any, cast

from langgraph.types import Send
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage,SystemMessage
from graph.prompts import background_prompt,refine_prompt,turn_prompt,create_agent_prompt,role_prompt_template,role_interaction_prompt,continue_next_prompt,continue_judge_prompt
from graph.state import AgentState
from graph.pydantic_models import AlternativeActionList,RoleplayList
from llm.service import get_model,get_nostream_model
from tools.registry import active_tools,interact_with_role
from tools.interaction import ask_user_choice_impl
from utils.ip_utils import get_country_by_ip
from utils.logger import logger
from utils.retry import run_async_with_retry, run_sync_with_retry
from utils.websocket import emit_ws_event, receive_websocket_event
from datetime import datetime
#登录成功节点
async def login_success_node(state: AgentState) -> AgentState:
    logger.info("login_success_node")
    logger.print("node:" + "login_success_node")
    return state

# 初始化世界参数节点
async def init_world_params(state: AgentState) -> AgentState:
    logger.print("role_node_msg:小妹妹 -> 早上好")
    logger.print("role_node_msg:小哥哥 -> 晚安")
    logger.info("init_world_params")
    logger.print("node:" + "init_world_params")
    time = datetime.now().strftime("%Y-%m-%d")
    country = await get_country_by_ip()
    return {
        "world_info": {
            "time": time,
            "country": country,
        }
    }


# 初次获取用户输入输入节点
async def intake_node(state: AgentState) -> AgentState:
    logger.info("intake_node")
    logger.print("node:" + "intake_node")
    raw_input = state.get("raw_input")
    if not raw_input:
        raise ValueError("raw_input is required")
    return {
        "raw_input": raw_input
    }

# 分析获取背景信息节点
async def background_node(state: AgentState) -> dict[str, Any]:
    logger.info("background_node")
    logger.print("node:" + "background_node")
    logger.print("background_node_msg:" + "总结背景信息中...")
    world_info = state.get("world_info", {})
    prompt_messages: list[BaseMessage] = [background_prompt]
    content = prompt_messages
    content.append(SystemMessage(
        "以下是 world_info（参考结局锚点信息）。"
        "它表示参考结局发生时的大致时间与地点，"
        "不是当前场景，不是新分支中的既定未来，不能直接作为后续剧情事实使用。\n\n"
        f"{json.dumps(world_info, ensure_ascii=False, indent=2)}"
    ))
    raw_input_parts = state.get("raw_input", [])
    raw_input_text = "\n".join(raw_input_parts)
    content.append(HumanMessage(raw_input_text))
    model = get_model()

    async def _stream_background() -> str:
        final_text = ""
        async for chunk in model.astream(content):
            chunk = cast(Any, chunk)
            text = chunk.content if isinstance(getattr(chunk, "content", None), str) else ""
            if text:
                logger.print("background_node_msg:" + text, end="")
                final_text += text
        return final_text

    final_text = await run_async_with_retry(
        "background_node.astream",
        _stream_background,
        fallback="",
    )
    return {
        "structured_scenario": final_text or ""
    }

# 等待用户补充信息节点
async def wait_user_node(state: AgentState) -> AgentState:
    logger.info("wait_user_node")
    logger.print("node:" + "wait_user_node")
    field = "follow_up"
    recent_tool_messages: list[ToolMessage] = []

    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage):
            recent_tool_messages.append(message)
        else:
            break
    recent_tool_messages.reverse()

    for message in reversed(recent_tool_messages):
        if getattr(message, "name", None) != "ask_user":
            continue
        payload = run_sync_with_retry(
            "wait_user_node.ask_user_payload",
            lambda: json.loads(cast(str, message.content)),
            retry_exceptions=(TypeError, json.JSONDecodeError),
            fallback={},
        )
        if isinstance(payload, dict):
            field = str(payload.get("field") or field)
        break

    event = await receive_websocket_event("user_answer")
    answer_field = str(event.get("field") or field)
    answer = str(event.get("answer") or "").strip()
    emit_ws_event("user_answer_received", field=answer_field, answer=answer)
    return {
        "raw_input": [answer]
    }

# 分析调用工具节点
async def agent_node(state: AgentState):
    logger.info("agent_node")
    logger.print("node:" + "agent_node")
    model = get_model().bind_tools(active_tools)
    structured_scenario = state.get("structured_scenario", "")
    recent_messages = state.get("messages", [])
    prompt: list[BaseMessage] = []
    prompt.append(refine_prompt)
    prompt.extend(recent_messages)
    if structured_scenario:
        prompt.append(HumanMessage(structured_scenario))
    response = await run_async_with_retry(
        "agent_node.ainvoke",
        lambda: model.ainvoke(prompt),
        fallback=None,
    )
    if response is None:
        return state
    return {"messages": [response]}



# 判断是否继续
def should_continue(state: AgentState):
    logger.info("should_continue")
    logger.print("node:" + "should_continue")
    messages = state.get("messages", [])
    if not messages:
        logger.info("should_continue -> end (no messages)")
        return "end"

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        logger.info(f"should_continue -> end (last={type(last_message).__name__})")
        return "end"

    route = "continue" if last_message.tool_calls else "end"
    logger.info(f"should_continue -> {route}; tool_calls={last_message.tool_calls}")
    return route


# 判断是否等待用户
def should_wait_for_user(state: AgentState):
    logger.info("should_wait_for_user")
    logger.print("node:" + "should_wait_for_user")
    recent_tool_messages: list[ToolMessage] = []

    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage):
            recent_tool_messages.append(message)
        else:
            break
    recent_tool_messages.reverse()

    for message in recent_tool_messages:
        if getattr(message, "name", None) == "ask_user":
            return "wait"
    return "continue"

#输出转机的节点
async def turn_node(state: AgentState) -> AgentState:
    logger.info("turn_node")
    logger.print("node:" + "turn_node")
    structured_scenario = state.get("structured_scenario")
    model = get_nostream_model().with_structured_output(AlternativeActionList,method="json_mode")
    prompt = []
    prompt.append(turn_prompt)
    prompt.append(SystemMessage("Please output valid JSON only."))
    prompt.append(HumanMessage(structured_scenario))
    raw_response = await run_async_with_retry(
        "turn_node.ainvoke",
        lambda: model.ainvoke(prompt),
        fallback=None,
    )
    if raw_response is None:
        return state
    logger.info(f"turn_node -> {raw_response}")
    response = AlternativeActionList.model_validate(raw_response)
    return {
        "turning_event": response.items
    }

#用户选择节点
async def user_choice_node(state: AgentState) -> AgentState:
    logger.info("user_choice_node")
    logger.print("node:" + "user_choice_node")
    turning_event = state.get("turning_event")
    field = "choose"
    if turning_event is None:
        raise ValueError("turning_event 缺失")
    if not isinstance(turning_event, list):
        raise TypeError(f"turning_event 类型错误: {type(turning_event)}")
    await ask_user_choice_impl(
        AlternativeActionList(items=turning_event)
    )
    event = await receive_websocket_event("user_choice")
    answer_field = str(event.get("field") or field)
    answer = str(event.get("user_choice") or "").strip()
    logger.info(f"用户选择: {answer_field}: {answer}")
    emit_ws_event("user_answer_received", field=answer_field, answer=answer)
    return {
        "chosen_action": answer,
        "messages": [HumanMessage(f"用户选择信息（{answer_field}）：{answer}")],
    }
# 创建角色节点
async def create_role_node(state: AgentState) -> AgentState:
    logger.info("create_role_node")
    logger.print("node:"+"create_role_node")
    chosen_action = state.get("chosen_action")
    if not chosen_action:
        raise ValueError("chosen_action 缺失")
    sysmsg = create_agent_prompt
    structured_scenario = state.get("structured_scenario")
    prompt = []
    prompt.append(sysmsg)
    prompt.append(SystemMessage("Please output valid JSON only."))
    prompt.append(HumanMessage(structured_scenario))
    prompt.append(HumanMessage(chosen_action))
    model = get_nostream_model().with_structured_output(RoleplayList,method="json_mode")
    raw_roles_info = await run_async_with_retry(
        "create_role_node.ainvoke",
        lambda: model.ainvoke(prompt),
        fallback=None,
    )
    if raw_roles_info is None:
        return state
    logger.info(raw_roles_info)
    roles_info = RoleplayList.model_validate(raw_roles_info)
    logger.info(roles_info)
    return {
        "roles_info": roles_info.roles
    }
def continue_to_roles(state: AgentState) -> list[Send]:
    return [Send("role_node", {"role": role}) for role in state.get("roles_info",[])]

# 角色节点
async def role_node(state: AgentState) -> AgentState:
    logger.info("role_node")
    logger.print("node:" + "role_node")
    role_info = state.get("role")
    if role_info is None:
        logger.error("role_info is None in role_node")
        return state
    role_prompt = role_prompt_template.format_messages(
        name=role_info.name,
        social_role=role_info.social_role,
        relation_to_user=role_info.relation_to_user,
        summary=role_info.summary,
        observed_actions=role_info.observed_actions,
        observed_attitudes=role_info.observed_attitudes,
        shared_events=role_info.shared_events,
        speech_style=role_info.communication_style,
        personality_traits=role_info.inferred_traits,
        knowledge_scope=role_info.knowledge_scope,
        boundaries=role_info.roleplay_rules,
        scene = state.get("structured_scenario"),
        user_message = state.get("chosen_action")
    )
    model = get_model()

    final_text = ""
    response: Any = None

    async for chunk in model.astream(role_prompt):
        chunk = cast(Any, chunk)
        text = chunk.content if isinstance(getattr(chunk, "content", None), str) else ""
        if text:
            final_text += text
        if response is None:
            response = chunk
        else: 
            response = response + chunk
    logger.print(f"role_node_msg:{role_info.name} -> {final_text}")
    role_outputs = role_info.name + "说:" +final_text
    return {
        "messages": [AIMessage(role_outputs)]
    }

# 判断角色和用户之间是否还缺失互动信息
async def analyze_interaction_node(state: AgentState) -> AgentState:
    logger.info("analyze_interaction_node")
    logger.print("node: analyze_interaction_node")
    model = get_model().bind_tools([interact_with_role])
    structured_scenario = state.get("structured_scenario")
    messages: list[BaseMessage] = []
    messages.append(role_interaction_prompt)
    messages.append(HumanMessage(structured_scenario))
    messages.extend(state.get("messages", []))

    response = await model.ainvoke(messages)
    logger.info(f"analyze_interaction_node -> {response}")
    return {"messages": [response]}

# 等待用户和角色交互
async def wait_for_interaction_node(state: AgentState) -> AgentState:
    logger.info("wait_for_interaction_node")
    logger.print("node: wait_for_interaction_node")
    field = "follow_up"
    recent_tool_messages: list[ToolMessage] = []

    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage):
            recent_tool_messages.append(message)
        else:
            break
    recent_tool_messages.reverse()

    for message in reversed(recent_tool_messages):
        if getattr(message, "name", None) != "interact_with_role":
            continue
        payload = run_sync_with_retry(
            "wait_for_interaction_node.interact_payload",
            lambda: json.loads(cast(str, message.content)),
            retry_exceptions=(TypeError, json.JSONDecodeError),
            fallback={},
        )
        if isinstance(payload, dict):
            field = str(payload.get("field") or field)
        break

    event = await receive_websocket_event("interact_with_role")
    answer_field = str(event.get("field") or field)
    target_role = str(event.get("role_name") or "")
    answer = str(event.get("answer") or "").strip()
    emit_ws_event("user_answer_received", field=answer_field, answer=answer)
    logger.info(HumanMessage(f"用户对{target_role}说：{answer}"))
    return {
        "messages": [HumanMessage(f"用户对{target_role}说：{answer}")],
    }

# 判断是否等待角色和用户交互
def should_wait_for_role_interaction(state: AgentState):
    logger.info("should_wait_for_role_interaction")
    logger.print("node:" + "should_wait_for_role_interaction")
    recent_tool_messages: list[ToolMessage] = []

    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage):
            recent_tool_messages.append(message)
        else:
            break
    recent_tool_messages.reverse()

    for message in recent_tool_messages:
        if getattr(message, "name", None) == "interact_with_role":
            return "wait"
    return "continue"

# 继续推理节点
async def continue_next_node(state: AgentState) -> AgentState:
    logger.info("continue_next_node")
    logger.print("node:" + "continue_next_node")
    model = get_model().bind_tools([interact_with_role], parallel_tool_calls=False)
    structured_scenario = state.get("structured_scenario")
    messages = state.get("messages", [])
    world_info = state.get("world_info", {})
    prompt: list[BaseMessage] = []
    prompt.append(continue_next_prompt)
    prompt.append(SystemMessage(json.dumps(world_info)))
    prompt.append(HumanMessage(structured_scenario))
    prompt.extend(messages)   # 这里必须用 extend，不是 append
    final_text = ""
    response: Any = None
    async for chunk in model.astream(prompt):
        chunk = cast(Any, chunk)
        text = chunk.content if isinstance(getattr(chunk, "content", None), str) else ""
        if text:
            logger.print("continue_next_msg:" + text, end="")
            final_text += text
        if response is None:
            response = chunk
        else:
            response = response + chunk
    return {"messages": [response]}


async def judge_continue_node(state: AgentState) -> AgentState:
    logger.info("judge_continue_node")
    logger.print("node:" + "judge_continue_node")

    model = get_nostream_model()
    structured_scenario = state.get("structured_scenario", "")
    messages = state.get("messages", [])

    prompt: list[BaseMessage] = []
    prompt.append(continue_judge_prompt)

    if structured_scenario:
        prompt.append(HumanMessage(structured_scenario))

    prompt.extend(messages)

    text = "continue"
    response = await run_async_with_retry(
        "judge_continue_node.ainvoke",
        lambda: model.ainvoke(prompt),
        fallback=None,
    )
    if response is not None:
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                text = content.strip().lower()
            else:
                text = str(content).strip().lower()
        else:
            text = str(response).strip().lower()
    else:
        text = "continue"

    if text not in {"continue", "end"}:
        text = "continue"

    logger.info(f"judge_continue_node -> {text}")
    return {
        "continue_status": text
    }

def should_continue_storyline(state: AgentState):
    logger.info("should_continue_storyline")
    logger.print("node:" + "should_continue_storyline")
    status = state.get("continue_status", "continue")
    logger.info(f"should_continue_storyline -> {status}")
    return status
