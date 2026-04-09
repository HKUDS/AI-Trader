from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


class AgentLogin(BaseModel):
    name: str
    password: str


class AgentRegister(BaseModel):
    name: str
    password: str
    wallet_address: Optional[str] = None
    initial_balance: float = 100000.0
    positions: Optional[List[dict]] = None


class RealtimeSignalRequest(BaseModel):
    market: str
    action: str
    symbol: str
    price: float
    quantity: float
    content: Optional[str] = None
    executed_at: str
    token_id: Optional[str] = None
    outcome: Optional[str] = None


class StrategyRequest(BaseModel):
    market: str
    title: str
    content: str
    symbols: Optional[str] = None
    tags: Optional[str] = None


class DiscussionRequest(BaseModel):
    market: str
    symbol: Optional[str] = None
    title: str
    content: str


class ReplyRequest(BaseModel):
    signal_id: int
    content: str


class AgentMessageCreate(BaseModel):
    agent_id: int
    type: str
    content: str
    data: Optional[Dict[str, Any]] = None


class AgentMessagesMarkReadRequest(BaseModel):
    categories: List[str]


class AgentTaskCreate(BaseModel):
    agent_id: int
    type: str
    input_data: Optional[Dict[str, Any]] = None


class FollowRequest(BaseModel):
    leader_id: int


class UserSendCodeRequest(BaseModel):
    email: EmailStr


class UserRegisterRequest(BaseModel):
    email: EmailStr
    code: str
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PointsTransferRequest(BaseModel):
    to_user_id: int
    amount: int


class PointsExchangeRequest(BaseModel):
    amount: int
