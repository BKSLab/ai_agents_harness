"""Bounded, TLS-verified GitLab REST v4 requests without credential-bearing diagnostics."""

import http.client
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from gitlab_config import ToolError

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LOG_BYTES = 512 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, config, *, transport=None, sleep=time.sleep):
        self.config = config
        self.sleep = sleep
        if transport is None:
            try:
                context = ssl.create_default_context(cafile=config.ca_bundle)
            except (OSError, ssl.SSLError):
                raise ToolError("TLS_CONFIG", "Cannot load the configured CA certificate bundle.") from None
            transport = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context), NoRedirect()).open
        self.transport = transport

    def request(self, method, path, *, params=None, payload=None, write=False, raw=False,
                not_found_ok=False, allow_null=False):
        if (method not in ("GET", "POST", "PUT") or write != (method != "GET")
                or (write and (raw or not_found_ok or allow_null))
                or (method == "GET" and payload is not None)):
            raise ToolError("INVALID_INPUT", "HTTP method and request capabilities do not match.")
        if not path.startswith("/") or "//" in path:
            raise ToolError("INVALID_INPUT", "API path must be absolute and well-formed.")
        cfg = self.config
        url = f"{cfg.host}/api/v4{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"PRIVATE-TOKEN": cfg.token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        attempts = 1 if write else cfg.read_retries + 1
        for attempt in range(attempts):
            try:
                with self.transport(request, timeout=cfg.timeout) as response:
                    limit = MAX_LOG_BYTES if raw else MAX_RESPONSE_BYTES
                    body = response.read(limit + 1)
                if raw:
                    truncated = len(body) > limit
                    if truncated:
                        body = body[:limit]
                    return {"text": body.decode("utf-8", errors="replace"), "truncated": truncated,
                            "segment": "prefix" if truncated else "complete"}
                if len(body) > limit:
                    raise ToolError("INVALID_RESPONSE", "Response exceeded the size limit.", uncertain=write)
                try:
                    parsed = json.loads(body)
                except (ValueError, UnicodeError):
                    raise ToolError("INVALID_RESPONSE", "API did not return valid JSON.", uncertain=write) from None
                if parsed is None and allow_null:
                    return None
                if not isinstance(parsed, (dict, list)):
                    raise ToolError("INVALID_RESPONSE", "API response must be an object or a list.", uncertain=write)
                return parsed
            except urllib.error.HTTPError as exc:
                exc.close()
                if not_found_ok and exc.code == 404:
                    return None
                transient = exc.code == 429 or exc.code >= 500
                if not write and transient and attempt + 1 < attempts:
                    self.sleep(min(2 ** attempt, 4))
                    continue
                if exc.code in (401, 403):
                    error = ToolError("ACCESS_DENIED", "GitLab denied access; check the token scopes and project permissions.")
                    error.status = exc.code
                    raise error from None
                if exc.code == 404:
                    raise ToolError("NOT_FOUND", "GitLab object was not found; check the project and object ID.") from None
                if write and exc.code in (400, 405, 406, 409, 422):
                    # A clean 4xx rejection means the write did not happen.
                    raise ToolError("API_REJECTED", "GitLab rejected the write; parameters or the current state do not allow it.") from None
                raise ToolError("HTTP_ERROR", "API returned an HTTP error.",
                                uncertain=write and (exc.code >= 500 or 300 <= exc.code < 400),
                                retryable=not write and transient) from None
            except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError, http.client.HTTPException):
                if not write and attempt + 1 < attempts:
                    self.sleep(min(2 ** attempt, 4))
                    continue
                raise ToolError("TRANSPORT_ERROR", "Request failed; check connectivity and trusted certificates.",
                                uncertain=write, retryable=not write) from None
        raise AssertionError("Unreachable retry state")
