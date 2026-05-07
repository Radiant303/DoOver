import asyncio
import json
from contextlib import asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from graph.graph import build_auth_app, build_guest_app
from graph.state import AgentState
from llm.client import create_provider_llm
from llm.config.provider import get_config_list
from user.update_name_pswd import update_username_and_password
from utils.load_config import load_json_config, save_json_config
from utils.logger import logger
from utils.session import (
    AUTH_COOKIE_KEY,
    create_login_token,
    load_user_conf,
    resolve_user_from_token,
    revoke_token,
)
from utils.websocket import (
    create_session,
    get_session_meta,
    get_session_subscriber_count,
    push_client_message,
    receive_session_event,
    reset_current_session,
    set_current_session,
    set_session_meta,
    subscribe_session,
    unsubscribe_session,
)

APPS = {
    "guest": build_guest_app(),
    "auth": build_auth_app(),
}
DEFAULT_APP_KEY = "guest"
_session_workers: dict[str, asyncio.Task[None]] = {}
DEFAULT_USER_NAME = "doover"
DEFAULT_USER_PASSWORD = "doover"
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


class LoginBody(BaseModel):
    username: str
    password: str


class ActivateLLMBody(BaseModel):
    provider: str
    model: str | None = None


class AddProviderBody(BaseModel):
    provider: str
    type: str = "openai"
    base_url: str
    api_key: str
    models: list[str]
    set_active: bool = False


class UpdateProviderBody(BaseModel):
    provider: str
    base_url: str
    api_key: str | None = None


class DiscoverProviderModelsBody(BaseModel):
    type: str = "openai"
    base_url: str
    api_key: str


class DiscoverSavedProviderBody(BaseModel):
    provider: str


class AddModelBody(BaseModel):
    provider: str
    model: str
    set_active: bool = False


class DeleteProviderBody(BaseModel):
    provider: str


class DeleteModelBody(BaseModel):
    provider: str
    model: str


class TestModelBody(BaseModel):
    provider: str | None = None
    type: str | None = "openai"
    base_url: str | None = None
    api_key: str | None = None
    model: str


def _normalize_app_key(app_key: str) -> str:
    key = str(app_key or "").strip().lower()
    if key not in APPS:
        raise ValueError(f"unsupported app graph: {app_key}")
    return key


def _parse_incoming_message(message: str) -> object:
    try:
        return json.loads(message)
    except json.JSONDecodeError:
        return {"type": "text", "text": message}


def _extract_request_token(request: Request) -> str | None:
    return request.cookies.get(AUTH_COOKIE_KEY)


def _is_default_user_conf() -> bool:
    conf = load_user_conf()
    return (
        str(conf.get("user_name") or "").strip() == DEFAULT_USER_NAME
        and str(conf.get("user_key") or "").strip() == DEFAULT_USER_PASSWORD
    )


async def _forward_messages_to_fastapi_websocket(
    websocket: WebSocket,
    queue: asyncio.Queue[str],
) -> None:
    while True:
        message = await queue.get()
        try:
            await websocket.send_text(message)
        except Exception:
            return


async def run_session(session_id: str) -> None:
    token = set_current_session(session_id)
    logger.info(f"session worker started: session_id={session_id}")
    try:
        while True:
            event = await receive_session_event("user_input", session_id=session_id)
            text = str(event.get("text") or "").strip()
            if not text:
                continue

            app_key = (
                str(get_session_meta(session_id, "app_key", DEFAULT_APP_KEY))
                .strip()
                .lower()
            )
            graph_app = APPS.get(app_key, APPS[DEFAULT_APP_KEY])
            logger.info(
                f"session worker handling user_input: session_id={session_id}, app={app_key}"
            )
            state: AgentState = {"raw_input": [text]}
            async for _ in graph_app.astream(state, stream_mode="values"):
                pass
            logger.info(
                f"session worker finished graph run: session_id={session_id}, app={app_key}"
            )
    except asyncio.CancelledError:
        logger.info(f"session worker cancelled: session_id={session_id}")
        raise
    except Exception:
        logger.exception(f"session worker crashed: session_id={session_id}")
        raise
    finally:
        reset_current_session(token)
        logger.info(f"session worker stopped: session_id={session_id}")


def _on_session_worker_done(session_id: str, task: asyncio.Task[None]) -> None:
    current = _session_workers.get(session_id)
    if current is task:
        _session_workers.pop(session_id, None)

    if task.cancelled():
        logger.info(f"session worker done(cancelled): session_id={session_id}")
        return

    exc = task.exception()
    if exc is None:
        logger.info(f"session worker done(clean): session_id={session_id}")
    else:
        logger.error(
            f"session worker done(error): session_id={session_id}, error={exc}"
        )


def ensure_session_worker(session_id: str, app_key: str) -> asyncio.Task[None]:
    normalized_session = create_session(session_id)
    normalized_app = _normalize_app_key(app_key)
    bound_app = get_session_meta(normalized_session, "app_key")
    if bound_app is None:
        set_session_meta(normalized_session, app_key=normalized_app)
    elif str(bound_app).strip().lower() != normalized_app:
        raise ValueError(
            f"session '{normalized_session}' already bound to app '{bound_app}', "
            f"cannot switch to '{normalized_app}'"
        )

    existing = _session_workers.get(normalized_session)
    if existing is not None and not existing.done():
        logger.info(
            f"session worker reuse: session_id={normalized_session}, app={normalized_app}"
        )
        return existing

    worker = asyncio.create_task(
        run_session(normalized_session),
        name=f"doover-session-{normalized_session}",
    )
    worker.add_done_callback(partial(_on_session_worker_done, normalized_session))
    _session_workers[normalized_session] = worker
    logger.info(
        f"session worker created: session_id={normalized_session}, app={normalized_app}"
    )
    return worker


async def stop_session_workers() -> None:
    workers = [task for task in _session_workers.values() if not task.done()]
    for task in workers:
        task.cancel()

    for task in workers:
        with suppress(asyncio.CancelledError):
            await task

    _session_workers.clear()


async def cancel_session_worker_if_no_subscribers(session_id: str) -> None:
    subscribers = get_session_subscriber_count(session_id)
    if subscribers > 0:
        logger.info(
            f"skip cancel session worker: session_id={session_id}, subscribers={subscribers}"
        )
        return

    worker = _session_workers.get(session_id)
    if worker is None:
        logger.info(
            f"skip cancel session worker: session_id={session_id}, reason=no_worker"
        )
        return

    if worker.done():
        logger.info(
            f"skip cancel session worker: session_id={session_id}, reason=already_done"
        )
        return

    logger.info(f"cancel session worker: session_id={session_id}, subscribers=0")
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
    logger.info(f"cancel session worker completed: session_id={session_id}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await stop_session_workers()


app = FastAPI(title="DoOver Graph Router", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
    token = _extract_request_token(request)
    user_name = await resolve_user_from_token(token)
    if not user_name:
        raise HTTPException(status_code=401, detail="not logged in")

    return {
        "ok": True,
        "user_name": user_name,
        "require_password_change": _is_default_user_conf(),
    }


@app.websocket("/ws/{app_key}")
async def ws_by_app(
    ws: WebSocket,
    app_key: str,
    session_id: str = Query(..., min_length=1),
) -> None:
    await ws.accept()
    try:
        normalized_app = _normalize_app_key(app_key)
        normalized_session = create_session(session_id)
        logger.info(
            f"ws connected: session_id={normalized_session}, app={normalized_app}"
        )
        if normalized_app == "auth":
            user_name = await resolve_user_from_token(ws.cookies.get(AUTH_COOKIE_KEY))
            if not user_name:
                raise ValueError("auth websocket requires login")
        ensure_session_worker(normalized_session, normalized_app)
    except (RuntimeError, ValueError) as exc:
        logger.warning(
            f"ws rejected: app={app_key}, session_id={session_id}, error={exc}"
        )
        await ws.close(code=1008, reason=str(exc))
        return

    outbound_queue = subscribe_session(normalized_session)
    forward_task = asyncio.create_task(
        _forward_messages_to_fastapi_websocket(ws, outbound_queue)
    )
    try:
        while True:
            message = await ws.receive_text()
            parsed = _parse_incoming_message(message)
            await push_client_message(parsed, session_id=normalized_session)
    except WebSocketDisconnect as exc:
        logger.info(
            f"ws disconnected: session_id={normalized_session}, app={normalized_app}, code={exc.code}"
        )
        return
    except Exception:
        logger.exception(
            f"ws receive loop failed: session_id={normalized_session}, app={normalized_app}"
        )
        return
    finally:
        logger.info(
            f"ws cleanup begin: session_id={normalized_session}, app={normalized_app}"
        )
        forward_task.cancel()
        with suppress(asyncio.CancelledError):
            await forward_task
        unsubscribe_session(outbound_queue, session_id=normalized_session)
        await cancel_session_worker_if_no_subscribers(normalized_session)
        logger.info(
            f"ws cleanup end: session_id={normalized_session}, app={normalized_app}"
        )


@app.websocket("/ws")
async def ws_default(
    ws: WebSocket,
    session_id: str = Query(..., min_length=1),
) -> None:
    user_name = await resolve_user_from_token(ws.cookies.get(AUTH_COOKIE_KEY))
    target_app = "auth" if user_name else "guest"
    await ws_by_app(ws, target_app, session_id)


@app.post("/login")
async def login(body: LoginBody, response: Response) -> dict[str, Any]:
    conf = load_user_conf()
    expected_user = conf["user_name"]
    expected_key = conf["user_key"]
    if not expected_user or not expected_key:
        raise HTTPException(status_code=500, detail="user config is invalid")
    if body.username != expected_user or body.password != expected_key:
        await asyncio.sleep(5)
        raise HTTPException(status_code=401, detail="bad credentials")
    token = await create_login_token(expected_user)
    response.set_cookie(
        key=AUTH_COOKIE_KEY,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {
        "ok": True,
        "user_name": expected_user,
        "require_password_change": _is_default_user_conf(),
    }


@app.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    await revoke_token(_extract_request_token(request))
    response.delete_cookie(key=AUTH_COOKIE_KEY, path="/")
    return {"ok": True}


# 修改用户名密码
@app.put("/update_user")
async def update_user(request: Request, user: LoginBody) -> dict[str, bool]:
    token = await _require_login_token(request)
    try:
        await update_username_and_password(token, user.username, user.password)
    except Exception as e:
        raise e
    return {"ok": True}


PROVIDER_CONFIG_PATH = Path("llm/config/provider.json")


def _build_openai_models_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise HTTPException(status_code=400, detail="base_url is required")

    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=400, detail="base_url must be a valid absolute URL"
        )

    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    elif not path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"{path}/models", parsed.query, parsed.fragment)
    )


async def _discover_openai_models(base_url: str, api_key: str) -> list[str]:
    request_url = _build_openai_models_url(base_url)
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                request_url, headers=headers, allow_redirects=True
            ) as response:
                if response.status >= 400:
                    detail = await response.text()
                    message = (
                        detail.strip()
                        or f"request failed with status {response.status}"
                    )
                    raise HTTPException(
                        status_code=400, detail=f"获取模型列表失败：{message}"
                    )

                try:
                    payload = await response.json()
                except aiohttp.ContentTypeError as error:
                    detail = await response.text()
                    raise HTTPException(
                        status_code=400,
                        detail=f"模型列表响应不是 JSON：{detail.strip() or error}",
                    ) from error
    except HTTPException:
        raise
    except aiohttp.ClientError as error:
        raise HTTPException(
            status_code=400, detail=f"获取模型列表失败：{error}"
        ) from error
    except asyncio.TimeoutError as error:
        raise HTTPException(status_code=400, detail="获取模型列表超时") from error

    items = payload.get("data")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="模型列表响应格式无效")

    models: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id and model_id not in models:
            models.append(model_id)

    if not models:
        raise HTTPException(status_code=400, detail="未获取到任何模型")

    return models


def _extract_model_response_text(response: Any) -> str:
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue

            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())

        return "\n".join(parts).strip()

    return str(content).strip()


def _resolve_test_model_config(
    payload: TestModelBody,
) -> tuple[str, str, str, str, str]:
    provider_name = str(payload.provider or "").strip()
    provider_type = str(payload.type or "").strip().lower()
    base_url = str(payload.base_url or "").strip()
    api_key = str(payload.api_key or "").strip()
    model_name = str(payload.model or "").strip()

    if not model_name:
        raise HTTPException(status_code=400, detail="model is required")

    if provider_name:
        data = load_json_config(PROVIDER_CONFIG_PATH)
        providers = data.get("llm_providers")
        if not isinstance(providers, dict) or provider_name not in providers:
            raise HTTPException(status_code=400, detail="provider not found")

        provider_conf = providers[provider_name]
        if not isinstance(provider_conf, dict):
            raise HTTPException(status_code=500, detail="invalid provider config")

        if not provider_type:
            provider_type = str(provider_conf.get("type") or "openai").strip().lower()
        if not base_url:
            base_url = str(provider_conf.get("base_url") or "").strip()
        if not api_key:
            api_key = str(provider_conf.get("api_key") or "").strip()
    else:
        provider_name = "临时配置"

    if not provider_type:
        provider_type = "openai"
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    return provider_name, provider_type, base_url, api_key, model_name


# 更换llm_model
@app.put("/update_llm")
async def update_llm(request: Request, payload: ActivateLLMBody) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    provider_conf = providers[provider]
    models = provider_conf.get("models")
    if not isinstance(models, list) or not models:
        raise HTTPException(status_code=400, detail="provider has no models")

    if payload.model and payload.model.strip():
        model = payload.model.strip()
    else:
        model = str(models[0])

    if model not in models:
        raise HTTPException(status_code=400, detail="model not in provider models")

    data["active_llm_provider"] = provider
    data["active_llm_model"] = model
    save_json_config(PROVIDER_CONFIG_PATH, data)

    return {"provider": provider, "model": model}


async def _require_login_token(request: Request) -> str:
    token = _extract_request_token(request)
    if not token or not await resolve_user_from_token(token):
        raise HTTPException(status_code=401, detail="not logged in")
    return token


@app.get("/llm_config")
async def llm_config(request: Request) -> dict[str, Any]:
    await _require_login_token(request)

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict):
        raise HTTPException(status_code=500, detail="invalid provider config")

    safe_providers: dict[str, dict[str, Any]] = {}
    for provider_name, provider_conf in providers.items():
        if not isinstance(provider_name, str):
            continue
        conf = provider_conf if isinstance(provider_conf, dict) else {}
        models = conf.get("models")
        safe_models = [str(m) for m in models] if isinstance(models, list) else []
        safe_providers[provider_name] = {
            "type": str(conf.get("type") or "openai"),
            "base_url": str(conf.get("base_url") or ""),
            "models": safe_models,
        }

    return {
        "active_provider": str(data.get("active_llm_provider") or ""),
        "active_model": str(data.get("active_llm_model") or ""),
        "providers": safe_providers,
    }


@app.get("/llm_provider_types")
async def llm_provider_types(request: Request) -> dict[str, Any]:
    await _require_login_token(request)

    return {
        "items": [item.to_dict() for item in get_config_list()],
    }


@app.post("/test_model")
async def test_model(request: Request, payload: TestModelBody) -> dict[str, Any]:
    await _require_login_token(request)

    provider_name, provider_type, base_url, api_key, model_name = (
        _resolve_test_model_config(payload)
    )
    logger.info(
        f"test_model start: provider={provider_name}, type={provider_type}, model={model_name}, base_url={base_url}"
    )

    try:
        model = create_provider_llm(
            model_name=model_name,
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url,
            stream_usage=False,
        )
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    HumanMessage(
                        "这是一条模型连通性测试消息。"
                        "请用简短中文回复“连接成功”，并附带当前模型名称。"
                    )
                ]
            ),
            timeout=30,
        )
    except asyncio.TimeoutError as error:
        logger.info(
            f"test_model timeout: provider={provider_name}, type={provider_type}, model={model_name}"
        )
        raise HTTPException(status_code=400, detail="模型测试超时") from error
    except Exception as error:
        logger.info(
            f"test_model failed: provider={provider_name}, type={provider_type}, model={model_name}, error={error}"
        )
        raise HTTPException(status_code=400, detail=f"模型测试失败：{error}") from error

    result = _extract_model_response_text(response)
    if not result:
        result = "模型已响应，但未返回可显示的文本结果"

    logger.info(
        f"test_model success: provider={provider_name}, type={provider_type}, model={model_name}, result={result}"
    )
    return {
        "provider": provider_name,
        "type": provider_type,
        "model": model_name,
        "result": result,
    }


@app.post("/discover_llm_models")
async def discover_llm_models(
    request: Request,
    payload: DiscoverProviderModelsBody,
) -> dict[str, Any]:
    await _require_login_token(request)

    provider_type = payload.type.strip().lower() or "openai"
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    if provider_type == "openai":
        models = await _discover_openai_models(payload.base_url, api_key)
        return {"type": provider_type, "models": models}

    raise HTTPException(
        status_code=400, detail=f"unsupported provider type: {provider_type}"
    )


@app.post("/discover_provider_models")
async def discover_provider_models(
    request: Request,
    payload: DiscoverSavedProviderBody,
) -> dict[str, Any]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    provider_conf = providers[provider]
    if not isinstance(provider_conf, dict):
        raise HTTPException(status_code=500, detail="invalid provider config")

    provider_type = str(provider_conf.get("type") or "openai").strip().lower()
    base_url = str(provider_conf.get("base_url") or "").strip()
    api_key = str(provider_conf.get("api_key") or "").strip()
    configured_models = provider_conf.get("models")
    safe_configured_models = (
        [str(m).strip() for m in configured_models]
        if isinstance(configured_models, list)
        else []
    )

    if not api_key:
        raise HTTPException(status_code=400, detail="provider api_key is missing")

    if provider_type == "openai":
        models = await _discover_openai_models(base_url, api_key)
        return {
            "provider": provider,
            "type": provider_type,
            "models": models,
            "configured_models": [m for m in safe_configured_models if m],
        }

    raise HTTPException(
        status_code=400, detail=f"unsupported provider type: {provider_type}"
    )


@app.put("/add_llm_provider")
async def add_llm_provider(
    request: Request, payload: AddProviderBody
) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")

    models = [m.strip() for m in payload.models if str(m).strip()]
    if not models:
        raise HTTPException(status_code=400, detail="models is required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict):
        raise HTTPException(status_code=500, detail="invalid provider config")

    if provider in providers:
        raise HTTPException(status_code=400, detail="provider already exists")

    providers[provider] = {
        "type": payload.type.strip() or "openai",
        "base_url": payload.base_url.strip(),
        "api_key": payload.api_key.strip(),
        "models": models,
    }

    if payload.set_active:
        data["active_llm_provider"] = provider
        data["active_llm_model"] = models[0]

    save_json_config(PROVIDER_CONFIG_PATH, data)
    return {"provider": provider, "model": models[0]}


@app.put("/update_llm_provider")
async def update_llm_provider(
    request: Request, payload: UpdateProviderBody
) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")

    base_url = payload.base_url.strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    provider_conf = providers[provider]
    if not isinstance(provider_conf, dict):
        raise HTTPException(status_code=500, detail="invalid provider config")

    provider_conf["base_url"] = base_url
    if payload.api_key is not None and payload.api_key.strip():
        provider_conf["api_key"] = payload.api_key.strip()

    save_json_config(PROVIDER_CONFIG_PATH, data)
    return {"provider": provider}


@app.put("/add_llm_model")
async def add_llm_model(request: Request, payload: AddModelBody) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    model = payload.model.strip()
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model are required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    provider_conf = providers[provider]
    models = provider_conf.get("models")
    if not isinstance(models, list):
        raise HTTPException(status_code=500, detail="invalid provider models")

    if model not in models:
        models.append(model)

    if payload.set_active:
        data["active_llm_provider"] = provider
        data["active_llm_model"] = model

    save_json_config(PROVIDER_CONFIG_PATH, data)
    return {"provider": provider, "model": model}


@app.delete("/delete_llm_provider")
async def delete_llm_provider(
    request: Request, payload: DeleteProviderBody
) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    if len(providers) <= 1:
        raise HTTPException(status_code=400, detail="cannot delete last provider")

    active_provider = str(data.get("active_llm_provider") or "").strip()
    if active_provider == provider:
        raise HTTPException(status_code=400, detail="provider is currently active")

    del providers[provider]
    save_json_config(PROVIDER_CONFIG_PATH, data)
    return {"deleted_provider": provider}


@app.delete("/delete_llm_model")
async def delete_llm_model(
    request: Request, payload: DeleteModelBody
) -> dict[str, str]:
    await _require_login_token(request)

    provider = payload.provider.strip()
    model = payload.model.strip()
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model are required")

    data = load_json_config(PROVIDER_CONFIG_PATH)
    providers = data.get("llm_providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise HTTPException(status_code=400, detail="provider not found")

    provider_conf = providers[provider]
    models = provider_conf.get("models")
    if not isinstance(models, list) or model not in models:
        raise HTTPException(status_code=400, detail="model not found")

    if len(models) <= 1:
        raise HTTPException(
            status_code=400, detail="cannot delete last model in provider"
        )

    active_provider = str(data.get("active_llm_provider") or "").strip()
    active_model = str(data.get("active_llm_model") or "").strip()
    if active_provider == provider and active_model == model:
        logger.print(f"reject delete active model: provider={provider}, model={model}")
        raise HTTPException(status_code=400, detail="model is currently active")

    models.remove(model)
    save_json_config(PROVIDER_CONFIG_PATH, data)
    return {"provider": provider, "deleted_model": model}


if __name__ == "__main__":
    uvicorn.run("test:app", host="0.0.0.0", port=8000, reload=False)
    # 使用uv命令运行：uv test:app --host
