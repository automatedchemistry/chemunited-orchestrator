from __future__ import annotations

import time
from typing import Any

import requests
from loguru import logger
from pydantic import AnyHttpUrl

from .models import CommandSignature

_FEEDBACK_MAX_ATTEMPTS = 10
_FEEDBACK_POLL_INTERVAL_S = 0.5


class BaseClient:
    def __init__(self, url: str | AnyHttpUrl):
        self.base_url = str(url).rstrip("/")
        self._session = requests.Session()

    @property
    def url(self) -> str:
        return self.base_url

    def _build_url(self, url: str) -> str:
        return f"{self.base_url}/{str(url).lstrip('/')}"

    @staticmethod
    def _normalize_params(
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if params is None:
            return None

        return {
            key: str(value) if isinstance(value, list) else value
            for key, value in params.items()
        }

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Send a GET request."""
        kwargs["params"] = self._normalize_params(kwargs.get("params"))
        return self._session.get(self._build_url(url), **kwargs)

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send a POST request."""
        kwargs["params"] = self._normalize_params(kwargs.get("params"))
        return self._session.post(
            self._build_url(url),
            data=data,
            json=json,
            **kwargs,
        )

    def put(
        self,
        url: str,
        data: Any = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send a PUT request."""
        kwargs["params"] = self._normalize_params(kwargs.get("params"))
        return self._session.put(self._build_url(url), data=data, **kwargs)


class ComponentClient(BaseClient):
    """Client for component communication."""

    def _request(
        self,
        method: str,
        command: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json: Any = None,
        **request_kwargs: Any,
    ) -> requests.Response:
        if method == "GET":
            return super().get(command, params=params, **request_kwargs)
        if method == "PUT":
            return super().put(command, data=data, params=params, **request_kwargs)
        if method == "POST":
            return super().post(
                command,
                data=data,
                json=json,
                params=params,
                **request_kwargs,
            )
        raise ValueError(f"Unsupported HTTP method: {method}")

    def _wait_for_feedback(
        self,
        command: CommandSignature,
        **request_kwargs: Any,
    ) -> None:
        for _attempt in range(_FEEDBACK_MAX_ATTEMPTS):
            feedback = super().get(command.feedback_status_command, **request_kwargs)
            if feedback.status_code == 200 and command.validate_feedback_answer(
                feedback.json()
            ):
                return

            time.sleep(_FEEDBACK_POLL_INTERVAL_S)

        logger.warning(
            "The command {} had an unexpected behavior. "
            "The device did not send the expected feedback status. "
            "Expected: {} - got {}!",
            command.command,
            command.feedback_answer,
            feedback.json(),
        )

    def _send(
        self,
        *,
        method: str,
        command: str,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json: Any = None,
        wait_time: float = 0.0,
        feedback_status_command: str = "",
        feedback_answer: Any = "true",
        **request_kwargs: Any,
    ) -> requests.Response:
        result = self._request(
            method,
            command,
            params=params,
            data=data,
            json=json,
            **request_kwargs,
        )

        if wait_time > 0:
            time.sleep(wait_time)

        if feedback_status_command:
            feedback_command = CommandSignature(
                component=self.url,
                command=command,
                method="GET",
                feedback_status_command=feedback_status_command,
                feedback_answer=feedback_answer,
            )
            self._wait_for_feedback(feedback_command, **request_kwargs)

        return result

    def send_command(
        self,
        command: CommandSignature,
        **request_kwargs: Any,
    ) -> requests.Response:
        return self._send(
            method=command.method,
            command=command.command,
            params=command.parameters,
            wait_time=command.wait_time,
            feedback_status_command=command.feedback_status_command,
            feedback_answer=command.feedback_answer,
            **request_kwargs,
        )

    def sent_command(
        self,
        command: CommandSignature,
        **request_kwargs: Any,
    ) -> requests.Response:
        return self.send_command(command, **request_kwargs)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        wait_time: float = 0.0,
        feedback_status_command: str = "",
        feedback_answer: Any = "true",
        **request_kwargs: Any,
    ) -> requests.Response:
        return self._send(
            method="GET",
            command=url,
            params=params,
            wait_time=wait_time,
            feedback_status_command=feedback_status_command,
            feedback_answer=feedback_answer,
            **request_kwargs,
        )

    def put(
        self,
        url: str,
        data: Any = None,
        *,
        params: dict[str, Any] | None = None,
        wait_time: float = 0.0,
        feedback_status_command: str = "",
        feedback_answer: Any = "true",
        **request_kwargs: Any,
    ) -> requests.Response:
        return self._send(
            method="PUT",
            command=url,
            params=params,
            data=data,
            wait_time=wait_time,
            feedback_status_command=feedback_status_command,
            feedback_answer=feedback_answer,
            **request_kwargs,
        )

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        *,
        params: dict[str, Any] | None = None,
        wait_time: float = 0.0,
        feedback_status_command: str = "",
        feedback_answer: Any = "true",
        **request_kwargs: Any,
    ) -> requests.Response:
        return self._send(
            method="POST",
            command=url,
            params=params,
            data=data,
            json=json,
            wait_time=wait_time,
            feedback_status_command=feedback_status_command,
            feedback_answer=feedback_answer,
            **request_kwargs,
        )
