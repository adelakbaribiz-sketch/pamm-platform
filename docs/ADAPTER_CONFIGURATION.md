# Broker Adapter Configuration

This document describes how to configure each broker adapter for production use.

## Overview

The platform supports 4 broker adapters:

| Adapter    | Status          | SDK Required                          | Credentials Required                          |
|------------|-----------------|---------------------------------------|-----------------------------------------------|
| simulated  | READY           | None (built-in)                       | None                                          |
| mt5        | BLOCKED → LIVE  | `MetaTrader5` (Windows-only PyPI)     | MT5_LOGIN, MT5_PASSWORD, MT5_SERVER           |
| ctrader    | BLOCKED → LIVE  | `ctrader-open-api` (PyPI)             | CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET       |
| crypto     | BLOCKED → LIVE  | `ccxt` (PyPI)                         | CRYPTO_EXCHANGE, CRYPTO_API_KEY, CRYPTO_API_SECRET |

Each adapter auto-detects whether its SDK is installed and credentials are
provided. When both are available, the adapter operates in LIVE mode
(`is_live=True`). When either is missing, it operates in BLOCKED mode
(`is_live=False`, raises `NotImplementedError_` on every operation).

## Secrets Management

**NEVER commit credentials to source control.** Use one of these methods:

### Method 1: Environment Variables (Development)

```bash
# MT5
export MT5_LOGIN=12345
export MT5_PASSWORD=your_password
export MT5_SERVER=YourBroker-Server

# cTrader
export CTRADER_CLIENT_ID=your_app_id
export CTRADER_CLIENT_SECRET=your_app_secret
export CTRADER_HOST=cid-{client_id}.openapi.ctrader.com
export CTRADER_PORT=5030  # 5030=prod, 5035=demo

# Crypto
export CRYPTO_EXCHANGE=binance
export CRYPTO_API_KEY=your_api_key
export CRYPTO_API_SECRET=your_api_secret
```

### Method 2: Kubernetes Secrets (Production)

```bash
kubectl create secret generic mt5-creds \
  --from-literal=MT5_LOGIN=12345 \
  --from-literal=MT5_PASSWORD=your_password \
  --from-literal=MT5_SERVER=YourBroker-Server \
  -n pamm-platform
```

### Method 3: HashiCorp Vault (Enterprise)

```python
import hvac
client = hvac.Client(url='https://vault.example.com')
secret = client.secrets.kv.v2.read_secret_version(path='mt5/production')
config = secret['data']['data']
adapter = MT5Adapter(config)
```

## Unblocking Each Adapter

### MT5 (MetaTrader 5)

**Requirements:**
1. Windows host (the `MetaTrader5` package wraps the MT5 terminal's DLL).
2. MT5 terminal installed (32-bit or 64-bit per broker).
3. Broker account with API access enabled.
4. Python package: `pip install MetaTrader5`.

**How the adapter detects readiness:**
- `_MT5_AVAILABLE = True` (MetaTrader5 package importable).
- `_login`, `_password`, `_server` all set (via config or env vars).
- `mt5.initialize(...)` returns True.
- `mt5.account_info()` returns non-None.

If any step fails, the adapter remains BLOCKED with a clear reason.

### cTrader (Open API)

**Requirements:**
1. cTrader Open API access (apply via your broker).
2. `ctrader-open-api` Python package.
3. client_id + client_secret.
4. TLS WebSocket to `cid-{client_id}.openapi.ctrader.com:5030`.

### Crypto (via CCXT)

**Requirements:**
1. Exchange account (Binance, Kraken, OKX, Coinbase, etc.).
2. API key with READ + TRADE permissions. **DISABLE WITHDRAWALS.**
3. IP allow-list the API key to your server's egress IP.
4. `ccxt` Python package.

**Critical safety:**
- API key MUST NOT have withdrawal permissions.
- Use testnet for all development.

## Capability Matrix

| Capability               | Simulated | MT5  | cTrader | Crypto |
|--------------------------|-----------|------|---------|--------|
| supports_market_orders   | yes       | yes  | yes     | yes    |
| supports_limit_orders    | yes       | yes  | yes     | yes    |
| supports_stop_orders     | yes       | yes  | yes     | no     |
| supports_modify          | yes       | yes  | yes     | yes    |
| supports_cancel          | yes       | yes  | yes     | yes    |
| supports_partial_fills   | yes       | yes  | yes     | yes    |
| supports_reconciliation  | yes       | yes  | yes     | yes    |
| lot_step                 | 0.01      | 0.01 | 0.01    | 1E-8   |

## Error Normalization

| Canonical Code         | MT5 retcode              | cTrader ErrorCode       | ccxt Exception            |
|------------------------|--------------------------|-------------------------|----------------------------|
| AUTH_FAILED            | invalid_account          | AUTH_FAILED             | InvalidApiKey              |
| ORDER_REJECTED         | 10013, 10014, 10015      | WRONG_STOPS, BAD_VOLUME | InvalidOrder               |
| INSUFFICIENT_MARGIN    | 10019 (NO_MONEY)         | NOT_ENOUGH_MONEY        | InsufficientFunds          |
| MARKET_CLOSED          | 10018                    | MARKET_CLOSED           | -                          |
| RATE_LIMITED           | -                        | RATE_LIMIT_EXCEEDED     | RateLimitExceeded          |
| CONNECTION_LOST        | initialize() failure     | WS disconnect           | NetworkError               |

## Testing

### Unit tests (mocked SDK)

The adapter tests in `tests/test_adapters.py` use `unittest.mock` to simulate
the SDK without requiring the real package. This verifies:
- The correct SDK methods are called with the right arguments.
- Error codes are mapped correctly.
- The BLOCKED fallback works when SDK/creds are unavailable.

### Integration tests (live SDK)

To run against a real broker, set the credentials via env vars and run:

```bash
# MT5 (on a Windows host with MetaTrader5 package installed)
pytest tests/test_mt5_live.py -v

# cTrader
pytest tests/test_ctrader_live.py -v

# Crypto (with testnet credentials)
pytest tests/test_crypto_live.py -v
```

These tests are skipped if the SDK is not installed or credentials are missing.
