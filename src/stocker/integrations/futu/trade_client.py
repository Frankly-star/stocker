"""FutuTradeClient: wraps ``futu.OpenSecTradeContext`` for Stocker.

Responsibilities:
- Connect / close the trade context
- Account discovery (get_acc_list)
- Trade unlock
- Place / modify / cancel orders
- Query orders, deals, positions, account info
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from stocker.integrations.futu.config import FutuConfig

logger = logging.getLogger(__name__)


class FutuTradeClient:
    """Thin wrapper around ``futu.OpenSecTradeContext``."""

    def __init__(self, config: FutuConfig) -> None:
        self._config = config
        self._ctx: Any = None  # futu.OpenSecTradeContext
        self._connected = False
        self._unlocked = False
        self._acc_id: int | None = None
        self._acc_list: list[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Create and start the OpenSecTradeContext."""
        from futu import OpenSecTradeContext

        self._ctx = OpenSecTradeContext(
            filter_trdmarket=self._config.to_futu_market(),
            host=self._config.host,
            port=self._config.port,
        )
        self._connected = True
        logger.info(
            "FutuTradeClient connected to %s:%d (market=%s)",
            self._config.host,
            self._config.port,
            self._config.market,
        )

    def close(self) -> None:
        """Close the trade context."""
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception as e:
                logger.warning("Error closing trade context: %s", e)
            finally:
                self._ctx = None
                self._connected = False
                self._unlocked = False

    @property
    def connected(self) -> bool:
        return self._connected and self._ctx is not None

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    @property
    def acc_id(self) -> int | None:
        return self._acc_id

    @property
    def ctx(self):
        return self._ctx

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def discover_accounts(self) -> list[dict]:
        """Fetch account list and auto-select the first matching account."""
        if not self._ctx:
            return []

        ret, df = self._ctx.get_acc_list()
        if ret != 0 or df is None or df.empty:
            logger.warning("get_acc_list failed: ret=%s", ret)
            return []

        self._acc_list = df.to_dict("records")

        # Auto-select: pick the first account matching trd_env
        trd_env = self._config.to_futu_trd_env()
        for acc in self._acc_list:
            if str(acc.get("trd_env", "")) == str(trd_env):
                self._acc_id = int(acc.get("acc_id", 0))
                break
        else:
            # Fallback: first account
            if self._acc_list:
                self._acc_id = int(self._acc_list[0].get("acc_id", 0))

        logger.info("Discovered %d accounts, selected acc_id=%s", len(self._acc_list), self._acc_id)
        return self._acc_list

    def unlock_trade(self, password: str = "") -> bool:
        """Unlock trading.  Password can be empty for simulate env.

        Note: GUI version of OpenD blocks API unlock — user must click
        the unlock button in OpenD's top-right corner manually.
        For simulate env, unlock failure is non-fatal (most operations still work).
        """
        if not self._ctx:
            return False

        pwd = password or self._config.trade_password
        if not pwd and self._config.trd_env.lower() == "real":
            logger.warning("unlock_trade: no password provided for REAL env")
            return False

        ret, data = self._ctx.unlock_trade(password=pwd, is_unlock=True)
        if ret != 0:
            data_str = str(data) if data else ""

            # GUI version of OpenD blocks API unlock
            if "GUI" in data_str or "解锁按钮" in data_str or "屏蔽解锁" in data_str:
                logger.info(
                    "unlock_trade: GUI 版 OpenD 不支持 API 解锁。"
                    "请在 OpenD 界面右上角手动点击解锁按钮。"
                    "模拟盘下大部分功能仍可正常使用。"
                )
                # For simulate env, treat as soft-unlocked (most queries work)
                if self._config.trd_env.lower() == "simulate":
                    self._unlocked = True
                    return True
            else:
                logger.warning("unlock_trade failed: ret=%s data=%s", ret, data)

            self._unlocked = False
            return False

        self._unlocked = True
        logger.info("Trade unlocked successfully")
        return True

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    def place_order(
        self,
        code: str,
        price: float,
        qty: int,
        trd_side,
        order_type=None,
        adjust_limit: float = 0,
    ) -> tuple[int, Any]:
        """Place an order. Returns ``(ret_code, data)``."""
        if not self._ctx:
            return -1, "Trade context not connected"

        from futu import OrderType as FutuOrderType

        trd_env = self._config.to_futu_trd_env()
        otype = order_type if order_type is not None else FutuOrderType.MARKET

        ret, data = self._ctx.place_order(
            price=price,
            qty=qty,
            code=code,
            trd_side=trd_side,
            order_type=otype,
            trd_env=trd_env,
            acc_id=self._acc_id or 0,
            adjust_limit=adjust_limit,
        )
        if ret != 0:
            logger.warning("place_order failed: ret=%s data=%s code=%s", ret, data, code)
        return ret, data

    def modify_order(self, order_id: str, price: float = 0, qty: int = 0, modify_type=None) -> tuple[int, Any]:
        """Modify an existing order."""
        if not self._ctx:
            return -1, "Trade context not connected"

        from futu import ModifyOrderOp

        op = modify_type if modify_type is not None else ModifyOrderOp.NORMAL
        trd_env = self._config.to_futu_trd_env()

        ret, data = self._ctx.modify_order(
            modify_order_op=op,
            order_id=order_id,
            price=price,
            qty=qty,
            trd_env=trd_env,
            acc_id=self._acc_id or 0,
        )
        return ret, data

    def cancel_order(self, order_id: str) -> tuple[int, Any]:
        """Cancel an order by setting modify_order_op to CANCEL."""
        if not self._ctx:
            return -1, "Trade context not connected"

        from futu import ModifyOrderOp

        trd_env = self._config.to_futu_trd_env()

        ret, data = self._ctx.modify_order(
            modify_order_op=ModifyOrderOp.CANCEL,
            order_id=order_id,
            qty=0,
            price=0,
            trd_env=trd_env,
            acc_id=self._acc_id or 0,
        )
        return ret, data

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def query_orders(self, status_filter: list | None = None) -> pd.DataFrame | None:
        """Query today's order list."""
        if not self._ctx:
            return None

        trd_env = self._config.to_futu_trd_env()
        kwargs: dict[str, Any] = {"trd_env": trd_env, "acc_id": self._acc_id or 0}
        if status_filter:
            kwargs["status_filter_list"] = status_filter

        ret, df = self._ctx.order_list_query(**kwargs)
        if ret != 0:
            logger.debug("order_list_query: ret=%s", ret)
            return None
        return df

    def query_deals(self) -> pd.DataFrame | None:
        """Query today's deal (execution) list."""
        if not self._ctx:
            return None

        trd_env = self._config.to_futu_trd_env()
        ret, df = self._ctx.deal_list_query(trd_env=trd_env, acc_id=self._acc_id or 0)
        if ret != 0:
            return None
        return df

    def query_positions(self) -> pd.DataFrame | None:
        """Query current positions."""
        if not self._ctx:
            return None

        trd_env = self._config.to_futu_trd_env()
        ret, df = self._ctx.position_list_query(trd_env=trd_env, acc_id=self._acc_id or 0)
        if ret != 0:
            logger.debug("position_list_query: ret=%s", ret)
            return None
        return df

    def query_account_info(self) -> pd.DataFrame | None:
        """Query account information (balance, buying power, etc.)."""
        if not self._ctx:
            return None

        trd_env = self._config.to_futu_trd_env()
        ret, df = self._ctx.accinfo_query(trd_env=trd_env, acc_id=self._acc_id or 0)
        if ret != 0:
            logger.debug("accinfo_query: ret=%s", ret)
            return None
        return df
