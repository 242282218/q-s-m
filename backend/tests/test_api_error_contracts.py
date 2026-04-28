from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.error_codes import ErrorCode, ErrorContext
from app.core.exceptions import QSMException


@pytest.mark.asyncio
async def test_liveness_endpoint_echoes_request_id_in_payload_and_header(
    async_client: AsyncClient,
):
    response = await async_client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "req-health-live"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-health-live"
    assert payload["code"] == 0
    assert payload["message"] == "Service alive"
    assert payload["request_id"] == "req-health-live"
    assert payload["timestamp"]


@pytest.mark.asyncio
async def test_unknown_route_returns_uniform_http_error_contract(
    async_client: AsyncClient,
):
    response = await async_client.get(
        "/api/v1/does-not-exist",
        headers={"X-Request-ID": "req-404"},
    )

    payload = response.json()
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req-404"
    assert set(payload) == {"code", "message", "data", "error", "request_id", "timestamp"}
    assert payload["code"] == 404
    assert payload["message"] == "Not Found"
    assert payload["data"] is None
    assert payload["error"] == {
        "field": None,
        "value": None,
        "reason": "Not Found",
        "context": None,
    }
    assert payload["request_id"] == "req-404"
    assert payload["timestamp"]


@pytest.mark.asyncio
async def test_validation_error_returns_uniform_contract_and_request_id(
    async_client: AsyncClient,
):
    response = await async_client.get(
        "/api/v1/quark/searches/tmdb/7",
        params={"max_results": 0},
        headers={"X-Request-ID": "req-422"},
    )

    payload = response.json()
    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "req-422"
    assert set(payload) == {"code", "message", "data", "error", "request_id", "timestamp"}
    assert payload["code"] == 422
    assert payload["message"] == "Validation Error"
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["loc"][-1] == "max_results"
    assert payload["error"]["field"] == "max_results"
    assert payload["error"]["value"] == "0"
    assert payload["error"]["reason"]
    assert payload["error"]["context"]["errors"][0]["loc"][-1] == "max_results"
    assert payload["request_id"] == "req-422"
    assert payload["timestamp"]


@pytest.mark.asyncio
async def test_qsm_exception_handler_returns_uniform_business_error_contract():
    from app.main import qsm_exception_handler

    request = SimpleNamespace(state=SimpleNamespace(request_id="req-qsm"))
    exception = QSMException(
        "转存失败",
        code=ErrorCode.TRANSFER_FAILED,
        context=ErrorContext(field="collection_id", value=7, reason="quota exceeded"),
        details={"task_id": "task-1"},
        data={"partial": True},
    )

    response = await qsm_exception_handler(request, exception)
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["code"] == ErrorCode.TRANSFER_FAILED
    assert payload["message"] == "转存失败"
    assert payload["data"] == {"partial": True}
    assert payload["error"] == {
        "field": "collection_id",
        "value": 7,
        "reason": "quota exceeded",
        "context": {"task_id": "task-1"},
    }
    assert payload["request_id"] == "req-qsm"
    assert payload["timestamp"]
