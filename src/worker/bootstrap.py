import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from taskiq import Context, TaskiqDepends, TaskiqEvents, TaskiqState

from src.core.config import get_worker_settings
from src.core.db import build_engine, build_session_factory
from src.core.logging import setup_logging
from src.core.request_context import request_id_scope
from src.core.uow import UnitOfWork
from src.modules.auth.service import AuthService
from src.modules.mail.adapters import SmtpMailer
from src.modules.mail.service import MailService
from src.modules.users.service import UsersService
from src.worker.broker import TASK_LEASE_SECONDS, build_broker
from src.worker.queue import CONFIRMATION_TASK, PASSWORD_RESET_TASK
from src.worker.tasks.auth_mail import deliver_confirmation, deliver_password_reset


@dataclass(slots=True, frozen=True)
class WorkerDependencies:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    mailer: SmtpMailer


settings = get_worker_settings()
broker = build_broker(settings.redis)
task_context: Context = TaskiqDepends()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState) -> None:
    setup_logging(settings.logging.level)
    engine = build_engine(settings.db)
    state.dependencies = WorkerDependencies(
        engine, build_session_factory(engine), SmtpMailer(settings.smtp)
    )


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState) -> None:
    dependencies: WorkerDependencies = state.dependencies
    await dependencies.engine.dispose()


@broker.task(task_name=CONFIRMATION_TASK, ack_type="manual")
async def send_confirmation(
    confirmation_id: UUID, request_id: str | None, context: Context = task_context
) -> None:
    await _run_mail_task(confirmation_id, request_id, context, deliver_confirmation)


@broker.task(task_name=PASSWORD_RESET_TASK, ack_type="manual")
async def send_password_reset(
    reset_id: UUID, request_id: str | None, context: Context = task_context
) -> None:
    await _run_mail_task(reset_id, request_id, context, deliver_password_reset)


async def _run_mail_task(
    reservation_id: UUID,
    request_id: str | None,
    context: Context,
    deliver: Callable[[UUID, UnitOfWork, AuthService, MailService], Awaitable[None]],
) -> None:
    dependencies: WorkerDependencies = context.state.dependencies
    uow = UnitOfWork(dependencies.session_factory)
    auth = AuthService(uow, UsersService(uow), settings.auth)
    mail = MailService(dependencies.mailer, settings.smtp.max_retries)
    with request_id_scope(request_id):
        async with asyncio.timeout(TASK_LEASE_SECONDS - 5):
            await deliver(reservation_id, uow, auth, mail)
            await context.ack()
