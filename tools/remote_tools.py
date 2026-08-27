"""比赛远程 API 工具：信用卡 / 汇率 / 水电煤 / 资产 / 支付订单。"""

from __future__ import annotations

from langchain_core.tools import tool

from tools.remote_api import remote_get


@tool("credit_card_monthly_bill")
def credit_card_monthly_bill(card_number: str, month: str) -> str:
    """查询指定信用卡的月度账单。month 格式 YYYY-MM。"""
    print(f"\033[33m→ credit_card_monthly_bill({card_number!r}, {month!r})\033[0m")
    out = remote_get(
        "/api/credit-card/monthly-bill",
        {"cardNumber": card_number, "month": month},
    )
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("exchange_rate")
def exchange_rate(
    from_currency: str,
    to_currency: str,
    amount: float = 1.0,
) -> str:
    """实时汇率查询与货币转换。货币代码如 USD/CNY/EUR/JPY/GBP/KRW。"""
    print(
        f"\033[33m→ exchange_rate({from_currency!r}->{to_currency!r}, amount={amount})\033[0m"
    )
    out = remote_get(
        "/api/exchange-rate",
        {
            "fromCurrency": from_currency.upper(),
            "toCurrency": to_currency.upper(),
            "amount": amount,
        },
    )
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("utility_monthly_bill")
def utility_monthly_bill(
    household_id: str,
    month: str,
    utility_type: str = "electricity",
) -> str:
    """查询户号的月度水电煤账单。utility_type: electricity|water|gas；month 为 YYYY-MM。"""
    print(
        f"\033[33m→ utility_monthly_bill({household_id!r}, {month!r}, {utility_type!r})\033[0m"
    )
    out = remote_get(
        "/api/utility-bill/monthly-bill",
        {
            "householdId": household_id,
            "month": month,
            "utilityType": utility_type,
        },
    )
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("user_assets")
def user_assets(customer_id: str, asset_type: str = "card") -> str:
    """按用户身份证号查资产。asset_type: card（信用卡，默认）| household（房产）。"""
    print(f"\033[33m→ user_assets({customer_id!r}, {asset_type!r})\033[0m")
    out = remote_get(
        "/api/user/assets",
        {"customerId": customer_id, "assetType": asset_type},
    )
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


@tool("create_payment_order")
def create_payment_order(
    merchant_id: str,
    order_id: str,
    amount: float | None = None,
) -> str:
    """创建支付订单（商户号 + 订单号；amount 可选，单位元）。"""
    print(
        f"\033[33m→ create_payment_order({merchant_id!r}, {order_id!r}, amount={amount})\033[0m"
    )
    params: dict = {"merchantId": merchant_id, "orderId": order_id}
    if amount is not None:
        params["amount"] = amount
    out = remote_get("/api/qr/create-payment-order", params)
    print(out[:300] + ("..." if len(out) > 300 else ""))
    return out


REMOTE_TOOLS = [
    credit_card_monthly_bill,
    exchange_rate,
    utility_monthly_bill,
    user_assets,
    create_payment_order,
]
