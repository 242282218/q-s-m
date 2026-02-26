# API Contract (Step 1: Existing Backend)

## Scope
- Base URL: `/api`
- Source: `backend/app` current FastAPI routes
- This document describes **current** backend contracts before response unification.
- Time fields use `format: "date-time"` (ISO 8601 string).

## Endpoint List
1. `GET /health`
2. `GET /metrics`
3. `POST /metrics/reset`
4. `GET /tmdb/details`
5. `POST /settings/update`
6. `POST /collection/add`
7. `GET /collection/list`
8. `GET /collection/check/{tmdb_id}`
9. `DELETE /collection/{collection_id}`
10. `GET /collection/check-link`
11. `POST /collection/check-links`
12. `POST /collection/verify` (SSE)
13. `POST /collection/verify/{collection_id}`
14. `POST /transfer/validate`
15. `POST /transfer/exec`
16. `POST /transfer/rename` (SSE)
17. `GET /quark/search/tmdb/{tmdb_id}`
18. `GET /quark/search/title`
19. `POST /quark/transfer`

## Components (JSON Schema)
```json
{
  "$defs": {
    "HealthData": {
      "type": "object",
      "required": ["status", "service", "timestamp"],
      "properties": {
        "status": { "type": "string" },
        "service": { "type": "string" },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    "MetricsData": {
      "type": "object",
      "required": ["requests", "database", "timestamp"],
      "properties": {
        "requests": {
          "type": "object",
          "required": ["total", "avg_time", "slow_requests_count"],
          "properties": {
            "total": { "type": "integer" },
            "avg_time": { "type": "number" },
            "slow_requests_count": { "type": "integer" }
          }
        },
        "database": {
          "type": "object",
          "required": ["total_queries", "total_time", "avg_time", "slow_queries_count", "recent_slow_queries"],
          "properties": {
            "total_queries": { "type": "integer" },
            "total_time": { "type": "number" },
            "avg_time": { "type": "number" },
            "slow_queries_count": { "type": "integer" },
            "recent_slow_queries": {
              "type": "array",
              "items": {
                "type": "array",
                "prefixItems": [{ "type": "number" }, { "type": "string" }],
                "minItems": 2,
                "maxItems": 2
              }
            }
          }
        },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    "TmdbDetailsData": {
      "type": "object",
      "required": ["poster_path", "backdrop_path", "title", "year"],
      "properties": {
        "poster_path": { "type": ["string", "null"] },
        "backdrop_path": { "type": ["string", "null"] },
        "title": { "type": ["string", "null"] },
        "year": { "type": ["string", "null"] }
      }
    },
    "SettingsUpdateRequest": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "LOG_LEVEL": { "type": "string" },
        "TMDB_API_KEY": { "type": "string" },
        "HTTP_PROXY": { "type": "string" },
        "QUARK_TRANSFER_COOKIE": { "type": "string" },
        "TRANSFER_KEEP_EXTRAS": { "type": "boolean" },
        "TRANSFER_KEEP_SUBTITLES": { "type": "boolean" },
        "TRANSFER_DRY_RUN": { "type": "boolean" },
        "TRANSFER_CLEANUP_ENABLED": { "type": "boolean" },
        "TRANSFER_CLEANUP_DELETE_NON_VIDEO": { "type": "boolean" },
        "TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO": { "type": "boolean" },
        "TRANSFER_CLEANUP_DELETE_EMPTY_DIRS": { "type": "boolean" }
      }
    },
    "SettingsUpdateResponse": {
      "type": "object",
      "required": ["success", "message"],
      "properties": {
        "success": { "type": "boolean" },
        "message": { "type": "string" }
      }
    },
    "CollectionAddRequest": {
      "type": "object",
      "required": ["tmdb_id", "media_type", "title", "share_url"],
      "properties": {
        "tmdb_id": { "type": "integer" },
        "media_type": { "type": "string" },
        "title": { "type": "string" },
        "year": { "type": ["integer", "null"] },
        "poster_path": { "type": ["string", "null"] },
        "backdrop_path": { "type": ["string", "null"] },
        "share_url": { "type": "string" },
        "share_pwd": { "type": ["string", "null"] },
        "file_structure": {},
        "category": { "type": ["string", "null"] }
      }
    },
    "CollectionAddResponse": {
      "type": "object",
      "required": ["success", "message"],
      "properties": {
        "success": { "type": "boolean" },
        "id": { "type": ["integer", "null"] },
        "message": { "type": "string" }
      }
    },
    "CollectionItem": {
      "type": "object",
      "required": ["id", "tmdb_id", "media_type", "title", "quark_share_url", "status", "saved_at"],
      "properties": {
        "id": { "type": "integer" },
        "tmdb_id": { "type": "integer" },
        "media_type": { "type": "string" },
        "title": { "type": "string" },
        "year": { "type": ["integer", "null"] },
        "poster_path": { "type": ["string", "null"] },
        "backdrop_path": { "type": ["string", "null"] },
        "quark_share_url": { "type": "string" },
        "category": { "type": ["string", "null"] },
        "status": { "type": "integer" },
        "saved_at": { "type": "string", "format": "date-time" }
      }
    },
    "CollectionListResponse": {
      "type": "object",
      "required": ["total", "page", "limit", "items"],
      "properties": {
        "total": { "type": "integer" },
        "page": { "type": "integer" },
        "limit": { "type": "integer" },
        "items": { "type": "array", "items": { "$ref": "#/$defs/CollectionItem" } }
      }
    },
    "CollectionCheckResponse": {
      "type": "object",
      "required": ["collected"],
      "properties": {
        "collected": { "type": "boolean" },
        "id": { "type": ["integer", "null"] }
      }
    },
    "CollectionDeleteResponse": {
      "type": "object",
      "required": ["success", "message"],
      "properties": {
        "success": { "type": "boolean" },
        "message": { "type": "string" }
      }
    },
    "CollectionCheckLinkResponse": {
      "type": "object",
      "required": ["collected"],
      "properties": {
        "collected": { "type": "boolean" },
        "id": { "type": ["integer", "null"] },
        "status": { "type": ["integer", "null"] }
      }
    },
    "CollectionCheckLinksRequest": {
      "type": "object",
      "required": ["links"],
      "properties": {
        "links": { "type": "array", "items": { "type": "string" } }
      }
    },
    "CollectionCheckLinksResponse": {
      "type": "object",
      "required": ["results"],
      "properties": {
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["link", "collected"],
            "properties": {
              "link": { "type": "string" },
              "collected": { "type": "boolean" },
              "id": { "type": ["integer", "null"] },
              "status": { "type": ["integer", "null"] }
            }
          }
        }
      }
    },
    "CollectionVerifyRequest": {
      "type": "object",
      "properties": {
        "collection_ids": { "type": ["array", "null"], "items": { "type": "integer" } }
      }
    },
    "CollectionVerifyResult": {
      "type": "object",
      "required": ["collection_id", "title", "previous_status", "current_status", "exists", "checked_path", "path_source"],
      "properties": {
        "collection_id": { "type": "integer" },
        "title": { "type": "string" },
        "previous_status": { "type": "integer" },
        "current_status": { "type": "integer" },
        "exists": { "type": "boolean" },
        "checked_path": { "type": "string" },
        "path_source": { "type": "string" }
      }
    },
    "CollectionVerifySingleResponse": {
      "type": "object",
      "required": ["success", "result"],
      "properties": {
        "success": { "type": "boolean" },
        "result": { "$ref": "#/$defs/CollectionVerifyResult" }
      }
    },
    "SseEvent": {
      "type": "object",
      "required": ["type", "current", "total", "percentage", "message", "level"],
      "properties": {
        "type": { "type": "string" },
        "current": { "type": "integer" },
        "total": { "type": "integer" },
        "percentage": { "type": "integer" },
        "message": { "type": "string" },
        "level": { "type": "string" }
      },
      "additionalProperties": true
    },
    "TransferFile": {
      "type": "object",
      "required": ["fid", "name", "size", "is_dir"],
      "properties": {
        "fid": { "type": ["string", "null"] },
        "name": { "type": ["string", "null"] },
        "size": { "type": "integer" },
        "is_dir": { "type": "boolean" }
      }
    },
    "ValidateLinkRequest": {
      "type": "object",
      "required": ["share_url"],
      "properties": {
        "share_url": { "type": "string" }
      }
    },
    "ValidateLinkResponse": {
      "type": "object",
      "required": ["valid", "message", "files"],
      "properties": {
        "valid": { "type": "boolean" },
        "message": { "type": "string" },
        "files": { "type": "array", "items": { "$ref": "#/$defs/TransferFile" } }
      }
    },
    "TransferExecRequest": {
      "type": "object",
      "required": ["collection_id"],
      "properties": {
        "collection_id": { "type": "integer" },
        "target_folder": { "type": ["string", "null"] },
        "auto_rename": { "type": "boolean", "default": false }
      }
    },
    "TransferExecResponse": {
      "type": "object",
      "required": ["success", "message", "files"],
      "properties": {
        "success": { "type": "boolean" },
        "message": { "type": "string" },
        "files": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["fid", "name", "size", "path"],
            "properties": {
              "fid": { "type": ["string", "null"] },
              "name": { "type": ["string", "null"] },
              "size": { "type": ["integer", "null"] },
              "path": { "type": "string" }
            }
          }
        }
      }
    },
    "RenameRequest": {
      "type": "object",
      "required": ["collection_id"],
      "properties": {
        "collection_id": { "type": "integer" }
      }
    },
    "MediaDto": {
      "type": "object",
      "required": ["tmdb_id", "title", "original_title", "overview", "poster_path", "backdrop_path", "media_type"],
      "properties": {
        "tmdb_id": { "type": "integer" },
        "title": { "type": "string" },
        "original_title": { "type": "string" },
        "year": { "type": ["integer", "null"] },
        "rating": { "type": ["number", "null"] },
        "overview": { "type": "string" },
        "poster_path": { "type": "string" },
        "backdrop_path": { "type": "string" },
        "media_type": { "type": "string" }
      }
    },
    "ResourceDto": {
      "type": "object",
      "required": ["name", "link", "overall_score", "quality_level", "resolution", "codec", "is_best"],
      "properties": {
        "name": { "type": "string" },
        "link": { "type": "string" },
        "overall_score": { "type": "number" },
        "quality_level": { "type": "string" },
        "resolution": { "type": "string" },
        "codec": { "type": "string" },
        "is_best": { "type": "boolean" },
        "normalized_name": { "type": ["string", "null"] },
        "Conf": { "type": ["number", "null"] },
        "Qual": { "type": ["number", "null"] },
        "alpha": { "type": ["number", "null"] },
        "tags": { "type": ["array", "null"], "items": { "type": "string" } },
        "size_gb": { "type": ["number", "null"] },
        "C_text": { "type": ["number", "null"] },
        "C_intent": { "type": ["number", "null"] },
        "C_plaus": { "type": ["number", "null"] },
        "P": { "type": ["number", "null"] },
        "R": { "type": ["number", "null"] }
      }
    },
    "SearchResponse": {
      "type": "object",
      "required": ["success", "resources", "total"],
      "properties": {
        "success": { "type": "boolean" },
        "message": { "type": ["string", "null"] },
        "media": { "anyOf": [{ "$ref": "#/$defs/MediaDto" }, { "type": "null" }] },
        "resources": { "type": "array", "items": { "$ref": "#/$defs/ResourceDto" } },
        "total": { "type": "integer" },
        "query_time": { "type": ["number", "null"] }
      }
    },
    "TransferRequest": {
      "type": "object",
      "required": ["link"],
      "properties": {
        "link": { "type": "string" },
        "to_dir_fid": { "type": "string", "default": "0" },
        "to_dir_name": { "type": ["string", "null"] },
        "media_type": { "type": "string", "default": "movie" },
        "title": { "type": ["string", "null"] },
        "year": { "type": ["integer", "null"] },
        "tmdb_id": { "type": ["integer", "null"] },
        "poster_path": { "type": ["string", "null"] },
        "backdrop_path": { "type": ["string", "null"] },
        "resource_name": { "type": ["string", "null"] }
      }
    },
    "QuarkTransferResponse": {
      "type": "object",
      "required": ["success", "message", "saved_files", "task_id", "collection_id", "collection_created"],
      "properties": {
        "success": { "type": "boolean" },
        "message": { "type": "string" },
        "saved_files": { "type": "array", "items": { "type": "string" } },
        "task_id": { "type": "string" },
        "collection_id": { "type": ["integer", "null"] },
        "collection_created": { "type": "boolean" }
      }
    }
  }
}
```

## Paths (Method + Params + Request/Response)
```json
{
  "GET /health": {
    "query": {},
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/HealthData" }
  },
  "GET /metrics": {
    "query": {},
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/MetricsData" }
  },
  "POST /metrics/reset": {
    "query": {},
    "path": {},
    "requestBody": null,
    "response": {
      "type": "object",
      "required": ["message"],
      "properties": { "message": { "type": "string" } }
    }
  },
  "GET /tmdb/details": {
    "query": { "media_type": "string", "tmdb_id": "integer" },
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/TmdbDetailsData" }
  },
  "POST /settings/update": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/SettingsUpdateRequest" },
    "response": { "$ref": "#/$defs/SettingsUpdateResponse" }
  },
  "POST /collection/add": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/CollectionAddRequest" },
    "response": { "$ref": "#/$defs/CollectionAddResponse" }
  },
  "GET /collection/list": {
    "query": {
      "page": "integer",
      "limit": "integer",
      "sort_by": "string",
      "order": "string",
      "category": "string|null",
      "status": "integer|null"
    },
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/CollectionListResponse" }
  },
  "GET /collection/check/{tmdb_id}": {
    "query": { "media_type": "string" },
    "path": { "tmdb_id": "integer" },
    "requestBody": null,
    "response": { "$ref": "#/$defs/CollectionCheckResponse" }
  },
  "DELETE /collection/{collection_id}": {
    "query": {},
    "path": { "collection_id": "integer" },
    "requestBody": null,
    "response": { "$ref": "#/$defs/CollectionDeleteResponse" }
  },
  "GET /collection/check-link": {
    "query": { "link": "string" },
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/CollectionCheckLinkResponse" }
  },
  "POST /collection/check-links": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/CollectionCheckLinksRequest" },
    "response": { "$ref": "#/$defs/CollectionCheckLinksResponse" }
  },
  "POST /collection/verify": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/CollectionVerifyRequest" },
    "response": {
      "contentType": "text/event-stream",
      "eventData": { "$ref": "#/$defs/SseEvent" }
    }
  },
  "POST /collection/verify/{collection_id}": {
    "query": {},
    "path": { "collection_id": "integer" },
    "requestBody": null,
    "response": { "$ref": "#/$defs/CollectionVerifySingleResponse" }
  },
  "POST /transfer/validate": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/ValidateLinkRequest" },
    "response": { "$ref": "#/$defs/ValidateLinkResponse" }
  },
  "POST /transfer/exec": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/TransferExecRequest" },
    "response": { "$ref": "#/$defs/TransferExecResponse" }
  },
  "POST /transfer/rename": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/RenameRequest" },
    "response": {
      "contentType": "text/event-stream",
      "eventData": { "$ref": "#/$defs/SseEvent" }
    }
  },
  "GET /quark/search/tmdb/{tmdb_id}": {
    "query": {
      "media_type": "string",
      "max_results": "integer"
    },
    "path": { "tmdb_id": "integer" },
    "requestBody": null,
    "response": { "$ref": "#/$defs/SearchResponse" }
  },
  "GET /quark/search/title": {
    "query": {
      "title": "string",
      "year": "integer|null",
      "max_results": "integer"
    },
    "path": {},
    "requestBody": null,
    "response": { "$ref": "#/$defs/SearchResponse" }
  },
  "POST /quark/transfer": {
    "query": {},
    "path": {},
    "requestBody": { "$ref": "#/$defs/TransferRequest" },
    "response": { "$ref": "#/$defs/QuarkTransferResponse" }
  }
}
```
