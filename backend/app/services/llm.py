"""Прокладка к нейросети GigaChat.

Остальной код вызывает только get_llm().complete(...). Что за этим стоит
(настоящий GigaChat или подставной в тестах), ему знать не нужно.
Любой сбой нейросети превращается в LLMUnavailable.
"""

import ssl
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings, settings

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
TOKEN_RESERVE_S = 60  # берём новый токен за минуту до истечения старого


class LLMUnavailable(Exception):
    """Нейросеть недоступна или ответила ошибкой."""


class LLM(Protocol):
    """Всё, что умеет «нейросеть» для остального кода."""

    def complete(
        self,
        user: str, # сам вопрос
        system: str = "", # роль нейросети в системе и правила
        *, # все параметры после звёздочки передаются только по имени, а не по порядку
        temperature: float = 0.2, # температура фантазии - ближе к 0 ответы сухие, ближе к 1 разнообразные
        max_tokens: int = 1000,
    ) -> str: ...


class GigaChatClient:
    def __init__(
        self,
        cfg: Settings = settings,
        transport: httpx.BaseTransport | None = None,
    ):
        self._cfg = cfg
        self._token = ""
        self._expires_at = 0.0  # когда токен протухнет (секунды, как time.time())
        self._lock = threading.Lock()  # чтобы два запроса разом не брали токен дважды

        ca = cfg.gigachat_ca_bundle
        verify = (
            ssl.create_default_context(cafile=ca) if ca and Path(ca).is_file() else True
        )
        # transport нужен только тестам: через него подсовывается «ненастоящий сервер»
        self._http = httpx.Client(
            timeout=cfg.gigachat_timeout, verify=verify, transport=transport
        )

    def _get_token(self, force: bool = False) -> str:
        with self._lock:
            fresh = time.time() < self._expires_at - TOKEN_RESERVE_S
            if self._token and fresh and not force:
                return self._token
            if not self._cfg.gigachat_credentials:
                raise LLMUnavailable("не задан GIGACHAT_CREDENTIALS")
            try:
                response = self._http.post(
                    OAUTH_URL,
                    data={"scope": self._cfg.gigachat_scope},
                    headers={
                        "Authorization": f"Basic {self._cfg.gigachat_credentials}",
                        "RqUID": str(uuid.uuid4()),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                self._token = data["access_token"]
                self._expires_at = data["expires_at"] / 1000  # в ответе миллисекунды
            except (httpx.HTTPError, ValueError, KeyError) as error:
                raise LLMUnavailable(
                    f"не удалось получить токен GigaChat: {error}"
                ) from error
            return self._token

    def complete(
        self,
        user: str,
        system: str = "",
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        body = {
            "model": self._cfg.gigachat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt in (1, 2):
            token = self._get_token(force=(attempt == 2))
            try:
                response = self._http.post(
                    CHAT_URL, json=body, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.HTTPError as error:
                raise LLMUnavailable(f"GigaChat не отвечает: {error}") from error
            if response.status_code == 401 and attempt == 1:
                continue  # токен мог протухнуть раньше срока: берём новый и пробуем ещё раз
            break

        if response.status_code != 200:
            raise LLMUnavailable(f"GigaChat вернул ошибку {response.status_code}")
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMUnavailable("GigaChat вернул ответ в неожиданном формате") from error


# ---------- активный клиент: сюда подставляется заглушка в тестах ----------

_client: LLM | None = None


def get_llm() -> LLM:
    global _client
    if _client is None:
        _client = GigaChatClient()
    return _client


def set_llm(client: LLM | None) -> None:
    global _client
    _client = client