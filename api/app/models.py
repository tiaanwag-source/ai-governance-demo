# api/app/models.py
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer, Text, String, TIMESTAMP, func, UniqueConstraint

Base = declarative_base()

class EventCanonical(Base):
    __tablename__ = "events_canonical"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=True)
    location: Mapped[str] = mapped_column(String(64), nullable=True)
    owner_email: Mapped[str] = mapped_column(String(256), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("event_id", name="uq_event_id"),)

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=True)
    location: Mapped[str] = mapped_column(String(64), nullable=True)
    owner_email: Mapped[str] = mapped_column(String(256), nullable=True)
    data_class: Mapped[str] = mapped_column(String(32), nullable=True)
    output_scope: Mapped[str] = mapped_column(Text, nullable=True)
    autonomy: Mapped[str] = mapped_column(String(32), nullable=True)
    dlp_template: Mapped[str] = mapped_column(String(128), nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class ClassificationMap(Base):
    __tablename__ = "classification_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    selector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    selector_value: Mapped[str] = mapped_column(String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(String(32), nullable=False)
    default_output_scope: Mapped[str] = mapped_column(Text, nullable=False)
    required_dlp_template: Mapped[str] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("selector_type", "selector_value", name="uq_class_selector"),
    )

class AgentSignal(Base):
    __tablename__ = "agent_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    data_class: Mapped[str] = mapped_column(String(32))
    output_scope: Mapped[str] = mapped_column(Text)
    reach: Mapped[str] = mapped_column(String(32))
    autonomy: Mapped[str] = mapped_column(String(32))
    external_tools: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    band: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    )

class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64))
    risk_band: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[str] = mapped_column(String(256))
    requested_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    )
    decided_by: Mapped[str] = mapped_column(String(256), nullable=True)
    decided_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True)

class PolicySetting(Base):
    __tablename__ = "policy_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class ActionPolicy(Base):
    __tablename__ = "action_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="needs_review")
    allow_green: Mapped[bool] = mapped_column(Integer, default=1)
    allow_amber: Mapped[bool] = mapped_column(Integer, default=1)
    allow_red: Mapped[bool] = mapped_column(Integer, default=0)
    approve_green: Mapped[bool] = mapped_column(Integer, default=0)
    approve_amber: Mapped[bool] = mapped_column(Integer, default=1)
    approve_red: Mapped[bool] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class WatchdogRun(Base):
    __tablename__ = "watchdog_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rescored: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[int] = mapped_column(Integer, default=0)
