"""BW-Trader data-source layer.

Split out from `service.server.price_fetcher` to keep market-specific
clients isolated (twstock for TW realtime/historical, twse_openapi for
extra TWSE OpenAPI endpoints, etc.). The primary price routing still
lives in `price_fetcher.py`.
"""
