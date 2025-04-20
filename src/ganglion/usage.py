from datetime import datetime, timedelta
from sqlalchemy import select

from .db import db_session
from .models import Account, UsageBucket


async def add_usage(
    account: Account,
    start_time: datetime,
    end_time: datetime,
    minimum_seconds: int = 2,
) -> list[UsageBucket]:
    """Record usage information for an account.

    Args:
        account: Account to associate with usage.
        start_time: Start of session.
        end_time: End of session.
        minimum_seconds: Minimum number of seconds before recording usage.

    Returns:
        A list of usage objects.
    """
    if account.temporary:
        return []
    HOUR = timedelta(seconds=60 * 60)
    start_hour = datetime(
        start_time.year,
        start_time.month,
        start_time.day,
        start_time.hour,
    )
    end_hour = datetime(
        end_time.year,
        end_time.month,
        end_time.day,
        end_time.hour,
    )

    usage_seconds = (end_time - start_time).seconds
    if usage_seconds < minimum_seconds:
        return []

    bucket_time = start_hour

    buckets: list[UsageBucket] = []
    async with db_session() as session:
        async with session.begin() as transaction:
            while bucket_time <= end_hour:
                usage = (
                    await session.execute(
                        select(UsageBucket).where(
                            UsageBucket.account_id == account.id,
                            UsageBucket.start_date == bucket_time,
                        )
                    )
                ).scalar()
                if usage is None:
                    usage = UsageBucket(
                        account_id=account.id, start_date=bucket_time, seconds=0
                    )
                    session.add(usage)
                buckets.append(usage)
                usage.seconds += usage_seconds
                bucket_time += HOUR
            await transaction.commit()
    return buckets
