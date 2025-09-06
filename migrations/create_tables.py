import asyncio
import logging
import os
import sys

from psycopg import AsyncConnection, Error

from app.infrastructure.database.connection import get_pg_connection
from config.config import Config, load_config

config: Config = load_config()

logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)

logger = logging.getLogger(__name__)

if sys.platform.startswith("win") or os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main():
    connection: AsyncConnection | None = None

    try:
        connection = await get_pg_connection(
            db_name=config.db.db,
            host=config.db.host,
            port=config.db.port,
            user=config.db.user,
            password=config.db.password,
        )
        async with connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        query="""
                            CREATE TABLE IF NOT EXISTS users(
                                id SERIAL PRIMARY KEY,
                                user_id BIGINT NOT NULL UNIQUE,
                                username VARCHAR(50),
                                name VARCHAR(50),
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                role VARCHAR(30) NOT NULL,
                                is_alive BOOLEAN NOT NULL,
                                banned BOOLEAN NOT NULL,
                                active_car_count INTEGER NOT NULL
                            ); 
                        """
                    )
                    await cursor.execute(
                        query="""
                            CREATE TABLE IF NOT EXISTS self_selection_requests(
                                id SERIAL PRIMARY KEY,
                                user_id BIGINT REFERENCES users(user_id),
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                brand VARCHAR(50),
                                model VARCHAR(50),
                                year VARCHAR(50),
                                odometer VARCHAR(50),
                                auction_status VARCHAR(50),
                                subscription BOOLEAN NOT NULL DEFAULT FALSE
                            );
                            CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_user_day
                            ON self_selection_requests (user_id, created_at);
                        """
                    )
                    await cursor.execute(
                        query="""
                            CREATE TABLE IF NOT EXISTS assisted_selection_requests(
                                id SERIAL PRIMARY KEY,
                                user_id BIGINT REFERENCES users(user_id),
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                body_style VARCHAR(50),
                                budget VARCHAR(50),
                                subscription BOOLEAN NOT NULL DEFAULT FALSE
                            );
                            CREATE UNIQUE INDEX IF NOT EXISTS idx_assisted_activity_user_day
                            ON assisted_selection_requests (user_id, created_at);
                        """
                    )
                    await cursor.execute(
                        query="""
                            CREATE TABLE IF NOT EXISTS chat_history(
                                id SERIAL PRIMARY KEY,
                                user_id BIGINT NOT NULL,
                                role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
                                content TEXT NOT NULL,
                                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                            );
                        """
                    )
                    await cursor.execute(
                        query="""
                            CREATE INDEX IF NOT EXISTS idx_chat_history_user_id 
                            ON chat_history(user_id);
                        """
                    )
                    await cursor.execute(
                        query="""
                            CREATE INDEX IF NOT EXISTS idx_chat_history_created_at 
                            ON chat_history(created_at);
                        """
                    )
                logger.info("All tables were successfully created")
    except Error as db_error:
        logger.exception("Database-specific error: %s", db_error)
    except Exception as e:
        logger.exception("Unhandled error: %s", e)
    finally:
        if connection:
            await connection.close()
            logger.info("Connection to Postgres closed")


asyncio.run(main())
