from __future__ import annotations

import asyncio
from collections.abc import Mapping
from http.cookies import SimpleCookie
from typing import Any

import httpx

from aiteamos_workspace import load_workspace


class TestClient:
    """Thread-free ASGI test client for sandboxed unittest runs.

    Starlette's TestClient drives the app through an AnyIO portal thread. The
    local sandbox used by these implementation rounds can leave that portal
    waiting forever, so API tests use httpx.ASGITransport directly instead.
    """

    def __init__(
        self,
        app: Any,
        base_url: str = "http://testserver",
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | httpx.Cookies | None = None,
        follow_redirects: bool = True,
        raise_server_exceptions: bool = True,
        **_: Any,
    ) -> None:
        self.app = app
        self.base_url = base_url
        self.headers = dict(headers or {})
        self.cookies = httpx.Cookies(cookies)
        self.follow_redirects = follow_redirects
        self.raise_server_exceptions = raise_server_exceptions
        self.workspace_id = self._workspace_id()

    def __enter__(self) -> "TestClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=self.raise_server_exceptions)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                follow_redirects=self.follow_redirects,
            ) as client:
                response = await client.request(method, self._canonical_url(url), **kwargs)
                self.cookies.update(client.cookies)
                self._drop_deleted_response_cookies(response)
                return response

        return asyncio.run(send())

    def _drop_deleted_response_cookies(self, response: httpx.Response) -> None:
        for header in response.headers.get_list("set-cookie"):
            parsed = SimpleCookie()
            parsed.load(header)
            for name, morsel in parsed.items():
                if morsel.value or morsel["max-age"] not in {"0", "-1"}:
                    continue
                self.cookies.delete(name)

    def _workspace_id(self) -> str | None:
        workspace_path = getattr(getattr(self.app, "state", None), "workspace_path", None)
        if workspace_path is None:
            return None
        try:
            return load_workspace(workspace_path).workspace.object_id
        except Exception:
            return None

    def _canonical_url(self, url: str) -> str:
        if not isinstance(url, str) or not url.startswith("/"):
            return url
        path, separator, query = url.partition("?")
        if path in {"/openapi.json", "/docs", "/redoc"}:
            return url
        if path == "/workspaces" or path.startswith("/workspaces/") or path.startswith("/session"):
            return url
        if path.startswith("/workspace/"):
            path = path.removeprefix("/workspace")
        if self.workspace_id and not path.startswith("/workspaces/"):
            path = f"/workspaces/{self.workspace_id}{path}"
        return f"{path}{separator}{query}" if separator else path

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)
